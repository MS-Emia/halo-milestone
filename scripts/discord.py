"""Discord Webhook への通知(Embed形式)。"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone

import net
from milestones import label

# サイトの主色(style.css の --primary)と揃える
EMBED_COLOR = 0x8EC9F0
JST = timezone(timedelta(hours=9))
TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096
# 動画タイトルはリンク文字列に入るので、説明文全体よりかなり短く切る
VIDEO_TITLE_LIMIT = 200
MAX_RATE_LIMIT_RETRIES = 3
_MARKDOWN_CHARS = re.compile(r"([\\*_~`|>\[\]()#<:-])")


class DiscordError(Exception):
    pass


def escape_markdown(text: str) -> str:
    return _MARKDOWN_CHARS.sub(r"\\\1", text)


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _video_link(video: dict) -> str:
    title = escape_markdown(truncate(video["title"] or video["id"], VIDEO_TITLE_LIMIT))
    return f"[{title}](https://www.youtube.com/watch?v={video['id']})"


def _jst(dt: datetime) -> str:
    return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")


def _embed(title: str, description: str, video: dict, fields: list[dict]) -> dict:
    embed = {
        "title": truncate(title, TITLE_LIMIT),
        "description": truncate(description, DESCRIPTION_LIMIT),
        "color": EMBED_COLOR,
        "fields": fields,
    }
    if video.get("thumbnail_url"):
        embed["thumbnail"] = {"url": video["thumbnail_url"]}
    return embed


def _payload(embed: dict) -> dict:
    # 動画タイトルに @everyone 等が含まれても誰にもメンションしない
    return {"embeds": [embed], "allowed_mentions": {"parse": []}}


def build_reach_payload(video: dict, prev: int, now: int, step: int, detected_at: datetime) -> dict:
    description = _video_link(video)
    if now - prev > 1:
        description += f"\n\n前回確認から複数の節目を通過しました({label(prev, step)}→{label(now, step)})"
    fields = [
        {"name": "現在の再生数", "value": f"{video['views']:,}回", "inline": True},
        {"name": "検知時刻", "value": _jst(detected_at), "inline": True},
    ]
    return _payload(_embed(f"🎉 {label(now, step)}再生突破！", description, video, fields))


def build_approach_payload(video: dict, next_milestone: int, remaining: int, step: int) -> dict:
    description = f"{_video_link(video)}\n\nあと約{remaining:,}回"
    fields = [{"name": "現在の再生数", "value": f"{video['views']:,}回", "inline": True}]
    return _payload(_embed(f"✨ もうすぐ{label(next_milestone, step)}再生！", description, video, fields))


def build_test_payload(now: datetime) -> dict:
    embed = {
        "title": "🔔 テスト通知",
        "description": f"再生数マイルストーン通知の接続テストです({_jst(now)})",
        "color": EMBED_COLOR,
    }
    return _payload(embed)


def post_webhook(webhook_url: str, payload: dict, sleep=time.sleep) -> None:
    """送信する。成功しなければ DiscordError。429はRetry-After秒待って最大3回再試行する。"""
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        res = net.request("POST", webhook_url, payload, sleep=sleep)
        if 200 <= res.status < 300:
            return
        if res.status == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
            sleep(_retry_after_seconds(res))
            continue
        # Webhook URL はトークンを含むので、エラーメッセージには出さない
        raise DiscordError(f"Discord Webhook がHTTP {res.status}を返しました: {_error_summary(res)}")
    raise DiscordError("Discord のレート制限が続いたため送信を諦めました")


def _retry_after_seconds(res: net.Response) -> float:
    headers = {k.lower(): v for k, v in res.headers.items()}
    for source in (headers.get("retry-after"), _json_field(res, "retry_after")):
        try:
            return min(max(float(source), 0.5), 60.0)
        except (TypeError, ValueError):
            continue
    return 2.0


def _json_field(res: net.Response, key: str):
    try:
        body = res.json()
        return body.get(key) if isinstance(body, dict) else None
    except ValueError:
        return None


def _error_summary(res: net.Response) -> str:
    message = _json_field(res, "message")
    if isinstance(message, str):
        return truncate(message, 200)
    return truncate(res.body.decode("utf-8", "replace"), 200) or "(本文なし)"


class Notifier:
    """送信間隔(0.5秒以上)を守り、DRY_RUN時は標準出力に出すだけにする。"""

    MIN_INTERVAL = 0.5

    def __init__(self, webhook_url: str | None, dry_run: bool, sleep=time.sleep, clock=time.monotonic):
        self.webhook_url = webhook_url
        self.dry_run = dry_run
        self._sleep = sleep
        self._clock = clock
        self._last_sent: float | None = None

    def send(self, payload: dict) -> None:
        if self.dry_run:
            print("[DRY_RUN] Discord送信内容:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return
        if self._last_sent is not None:
            wait = self.MIN_INTERVAL - (self._clock() - self._last_sent)
            if wait > 0:
                self._sleep(wait)
        try:
            post_webhook(self.webhook_url, payload, sleep=self._sleep)
        finally:
            self._last_sent = self._clock()
