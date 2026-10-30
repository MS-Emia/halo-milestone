"""エントリポイント: 再生数を取得し、節目の通知と site/data.json の生成を行う。

終了コード: 0=正常、1=実行時エラー、2=設定エラー
環境変数: YOUTUBE_API_KEY, DISCORD_WEBHOOK_URL, DRY_RUN=1(Discordへ送らず表示のみ・state保存なし)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import discord
import youtube
from milestones import Decision, decide_notifications, label
from net import NetworkError
from site_data import build_site_data
from state import StateError, dump_json, load_state, save_state, write_atomic

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "state.json"
SITE_DATA_PATH = ROOT / "site" / "data.json"

EXIT_OK, EXIT_RUNTIME_ERROR, EXIT_CONFIG_ERROR = 0, 1, 2

# 動画タイトルには絵文字等が入るため、Windows(cp932)のコンソールでも落ちないようにする
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class ConfigError(Exception):
    pass


def log(message: str) -> None:
    print(message, flush=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(path: Path) -> tuple[dict, list[str]]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"config.json を読めません: {e}") from e

    urls = config.get("playlist_urls")
    if not isinstance(urls, list) or not urls or any(not isinstance(u, str) or "TODO" in u for u in urls):
        raise ConfigError("config.json の playlist_urls に再生リストのURL(list= を含むもの)を追記してください")
    for key in ("milestone_step", "site_approach_remaining", "discord_approach_remaining"):
        value = config.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ConfigError(f"config.json の {key} は正の整数にしてください")

    try:
        playlist_ids = list(dict.fromkeys(youtube.parse_playlist_id(u) for u in urls))
    except ValueError as e:
        raise ConfigError(str(e)) from e
    return config, playlist_ids


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"環境変数 {name} が設定されていません(GitHub Secrets を確認してください)")
    return value


def fetch_videos(api_key: str, playlist_ids: list[str]) -> list[dict]:
    video_ids: list[str] = []
    for playlist_id in playlist_ids:
        ids = youtube.fetch_video_ids(api_key, playlist_id)
        log(f"再生リスト {playlist_id}: {len(ids)}件")
        video_ids.extend(ids)
    unique_ids = list(dict.fromkeys(video_ids))
    return youtube.fetch_video_stats(api_key, unique_ids, log=log)


def describe(video: dict, decision: Decision, step: int) -> str:
    parts = [f"{video['id']} {video['views']:,}回", f"次={label(decision.next_milestone, step)}(あと{decision.remaining:,})"]
    if decision.is_new:
        parts.append("新規(基準化)")
    if decision.reached:
        parts.append(f"到達 {label(decision.reached_from, step) if decision.reached_from else '0'}→{label(decision.current_milestone, step)}")
    if decision.approach_notify:
        parts.append("事前通知")
    return " / ".join(parts) + f" — {video['title']}"


def process_video(video: dict, state: dict, config: dict, notifier: discord.Notifier, now: datetime) -> bool:
    """1動画分を判定・通知し、送信成功分だけ state に反映する。失敗があれば False。"""
    step = config["milestone_step"]
    entries = state["videos"]
    entry = entries.get(video["id"])
    decision = decide_notifications(entry, video["views"], step, config["discord_approach_remaining"])
    log(describe(video, decision, step))

    if entry is None:
        # 初回観測時点で既に越えている節目は「到達」として扱わない
        entry = {"title": video["title"], "last_milestone": decision.current_milestone, "approach_notified_for": None, "history": []}
        entries[video["id"]] = entry
    entry["title"] = video["title"]

    if decision.reached:
        payload = discord.build_reach_payload(video, decision.reached_from, decision.current_milestone, step, now)
        if not send(notifier, payload, video):
            # 到達通知が未送信のまま事前通知だけ進めると順序が崩れるので、この動画は次回にまとめて再送する
            return False
        entry["last_milestone"] = decision.current_milestone
        entry.setdefault("history", []).append(
            {"milestone": decision.current_milestone, "reached_at": iso_utc(now), "views_at_detection": video["views"]}
        )

    if decision.approach_notify:
        payload = discord.build_approach_payload(video, decision.next_milestone, decision.remaining, step)
        if not send(notifier, payload, video):
            return False
        entry["approach_notified_for"] = decision.next_milestone
    return True


def send(notifier: discord.Notifier, payload: dict, video: dict) -> bool:
    try:
        notifier.send(payload)
        return True
    except (discord.DiscordError, NetworkError) as e:
        log(f"error: {video['id']} の通知に失敗しました。次回再送します: {e}")
        return False


def run_check(dry_run: bool) -> int:
    config, playlist_ids = load_config(CONFIG_PATH)
    api_key = require_env("YOUTUBE_API_KEY")
    webhook_url = None if dry_run else require_env("DISCORD_WEBHOOK_URL")

    try:
        state = load_state(STATE_PATH)
    except StateError as e:
        log(f"error: {e}。state.json を確認・修復してから再実行してください(自動初期化はしません)")
        return EXIT_RUNTIME_ERROR

    try:
        videos = fetch_videos(api_key, playlist_ids)
    except (youtube.YouTubeError, NetworkError) as e:
        log(f"error: {e}")
        return EXIT_RUNTIME_ERROR
    log(f"再生数を取得した動画: {len(videos)}件")

    now = utc_now()
    notifier = discord.Notifier(webhook_url, dry_run=dry_run)
    failures = sum(not process_video(v, state, config, notifier, now) for v in videos)

    if dry_run:
        log("[DRY_RUN] state.json は保存しません")
    elif save_state(STATE_PATH, state):
        log("state.json を更新しました")

    write_atomic(SITE_DATA_PATH, dump_json(build_site_data(videos, state, config, iso_utc(now))))
    log(f"{SITE_DATA_PATH.relative_to(ROOT)} を生成しました")

    if failures:
        log(f"error: {failures}件の動画で通知に失敗しました")
        return EXIT_RUNTIME_ERROR
    return EXIT_OK


def run_test_webhook() -> int:
    webhook_url = require_env("DISCORD_WEBHOOK_URL")
    try:
        discord.post_webhook(webhook_url, discord.build_test_payload(utc_now()))
    except (discord.DiscordError, NetworkError) as e:
        log(f"error: テスト通知に失敗しました: {e}")
        return EXIT_RUNTIME_ERROR
    log("テスト通知を送信しました。Discordを確認してください")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="天音かなた 歌ってみた 再生数マイルストーン通知")
    parser.add_argument("--test-webhook", action="store_true", help="テスト通知を1通送って終了する")
    args = parser.parse_args(argv)
    dry_run = os.environ.get("DRY_RUN", "") == "1"

    try:
        return run_test_webhook() if args.test_webhook else run_check(dry_run)
    except ConfigError as e:
        log(f"config error: {e}")
        return EXIT_CONFIG_ERROR


if __name__ == "__main__":
    sys.exit(main())
