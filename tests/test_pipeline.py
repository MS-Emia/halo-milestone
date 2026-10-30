"""API・Discord を差し替えて、入力解析・通知・state 更新のつながりを確認する。"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check  # noqa: E402
import discord  # noqa: E402
import net  # noqa: E402
import youtube  # noqa: E402
from site_data import build_site_data  # noqa: E402
from state import StateError, load_state, save_state  # noqa: E402

CONFIG = {
    "milestone_step": 1_000_000,
    "site_approach_remaining": 100_000,
    "discord_approach_remaining": 50_000,
}
NOW = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)


def video(views, video_id="dQw4w9WgXcQ", title="テスト *曲* @everyone"):
    return {"id": video_id, "title": title, "thumbnail_url": "https://i.ytimg.com/x.jpg", "published_at": "", "views": views}


class FakeNotifier:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def send(self, payload):
        if self.fail:
            raise discord.DiscordError("boom")
        self.sent.append(payload)


class ParsePlaylistIdTest(unittest.TestCase):
    def test_url_and_raw_id(self):
        pid = "PL1234567890abcdefXYZ_-"
        self.assertEqual(youtube.parse_playlist_id(f"https://www.youtube.com/playlist?list={pid}"), pid)
        self.assertEqual(youtube.parse_playlist_id(f"https://www.youtube.com/watch?v=dQw4w9WgXcQ&list={pid}&index=2"), pid)
        self.assertEqual(youtube.parse_playlist_id(pid), pid)

    def test_invalid(self):
        for bad in ["short", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "PL<script>alert(1)</script>"]:
            with self.assertRaises(ValueError):
                youtube.parse_playlist_id(bad)


class ParseVideoItemTest(unittest.TestCase):
    def test_missing_view_count_is_skipped(self):
        self.assertIsNone(youtube.parse_video_item({"id": "dQw4w9WgXcQ", "snippet": {}, "statistics": {}}))

    def test_non_numeric_view_count_is_skipped(self):
        self.assertIsNone(youtube.parse_video_item({"id": "dQw4w9WgXcQ", "statistics": {"viewCount": "abc"}}))

    def test_invalid_video_id_is_skipped(self):
        self.assertIsNone(youtube.parse_video_item({"id": "../../etc", "statistics": {"viewCount": "1"}}))

    def test_valid(self):
        item = {
            "id": "dQw4w9WgXcQ",
            "snippet": {"title": "曲", "publishedAt": "2020-01-01T00:00:00Z",
                        "thumbnails": {"medium": {"url": "https://i.ytimg.com/m.jpg"}}},
            "statistics": {"viewCount": "2003412"},
        }
        v = youtube.parse_video_item(item)
        self.assertEqual(v["views"], 2_003_412)
        self.assertEqual(v["thumbnail_url"], "https://i.ytimg.com/m.jpg")


class ProcessVideoTest(unittest.TestCase):
    def test_new_video_baselined_silently(self):
        state, n = {"videos": {}}, FakeNotifier()
        self.assertTrue(check.process_video(video(2_300_000), state, CONFIG, n, NOW))
        self.assertEqual(n.sent, [])
        entry = state["videos"]["dQw4w9WgXcQ"]
        self.assertEqual(entry["last_milestone"], 2)
        self.assertEqual(entry["history"], [])

    def test_reach_updates_state_and_history(self):
        state = {"videos": {"dQw4w9WgXcQ": {"title": "", "last_milestone": 2, "approach_notified_for": 3, "history": []}}}
        n = FakeNotifier()
        self.assertTrue(check.process_video(video(3_000_000), state, CONFIG, n, NOW))
        self.assertEqual(len(n.sent), 1)
        self.assertEqual(n.sent[0]["embeds"][0]["title"], "🎉 300万再生突破！")
        entry = state["videos"]["dQw4w9WgXcQ"]
        self.assertEqual(entry["last_milestone"], 3)
        self.assertEqual(entry["history"], [{"milestone": 3, "reached_at": "2026-10-30T03:00:00Z", "views_at_detection": 3_000_000}])

    def test_failed_send_keeps_state_for_retry(self):
        state = {"videos": {"dQw4w9WgXcQ": {"title": "", "last_milestone": 2, "approach_notified_for": None, "history": []}}}
        self.assertFalse(check.process_video(video(3_960_000), state, CONFIG, FakeNotifier(fail=True), NOW))
        entry = state["videos"]["dQw4w9WgXcQ"]
        self.assertEqual(entry["last_milestone"], 2)
        self.assertIsNone(entry["approach_notified_for"])

    def test_reach_and_approach_in_same_run(self):
        state = {"videos": {"dQw4w9WgXcQ": {"title": "", "last_milestone": 2, "approach_notified_for": 3, "history": []}}}
        n = FakeNotifier()
        check.process_video(video(3_960_000), state, CONFIG, n, NOW)
        self.assertEqual([p["embeds"][0]["title"] for p in n.sent], ["🎉 300万再生突破！", "✨ もうすぐ400万再生！"])
        self.assertEqual(state["videos"]["dQw4w9WgXcQ"]["approach_notified_for"], 4)


class DiscordPayloadTest(unittest.TestCase):
    def test_reach_payload(self):
        p = discord.build_reach_payload(video(4_100_000), 2, 4, 1_000_000, NOW)
        embed = p["embeds"][0]
        self.assertEqual(p["allowed_mentions"], {"parse": []})
        self.assertEqual(embed["title"], "🎉 400万再生突破！")
        self.assertIn("(200万→400万)", embed["description"])
        self.assertIn(r"テスト \*曲\* @everyone", embed["description"])
        self.assertIn("https://www.youtube.com/watch?v=dQw4w9WgXcQ", embed["description"])
        self.assertEqual(embed["fields"][0]["value"], "4,100,000回")
        self.assertEqual(embed["fields"][1]["value"], "2026-10-30 12:00 JST")

    def test_long_title_is_truncated(self):
        p = discord.build_approach_payload(video(960_000, title="あ" * 5000), 1, 40_000, 1_000_000)
        embed = p["embeds"][0]
        self.assertLessEqual(len(embed["description"]), 4096)
        self.assertIn("あと約40,000回", embed["description"])

    def test_rate_limit_retry(self):
        responses = [net.Response(429, {"Retry-After": "1.5"}, b"{}"), net.Response(204, {}, b"")]
        sleeps = []
        with mock.patch.object(net, "request", side_effect=responses):
            discord.post_webhook("https://discord.invalid/x", {}, sleep=sleeps.append)
        self.assertEqual(sleeps, [1.5])

    def test_rate_limit_gives_up_after_three_retries(self):
        with mock.patch.object(net, "request", return_value=net.Response(429, {"Retry-After": "1"}, b"{}")) as req:
            with self.assertRaises(discord.DiscordError):
                discord.post_webhook("https://discord.invalid/x", {}, sleep=lambda s: None)
        self.assertEqual(req.call_count, 4)


class NetRetryTest(unittest.TestCase):
    def test_backoff_on_network_error(self):
        sleeps = []
        with mock.patch("urllib.request.urlopen", side_effect=net.urllib.error.URLError("down")):
            with self.assertRaises(net.NetworkError):
                net.request("GET", "https://example.invalid/?key=SECRET", sleep=sleeps.append)
        self.assertEqual(sleeps, [1, 2, 4])


class StateFileTest(unittest.TestCase):
    def test_missing_file_is_empty_state(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_state(Path(d) / "state.json"), {"version": 1, "videos": {}})

    def test_broken_file_raises_and_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(StateError):
                load_state(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_save_roundtrip_and_no_rewrite_when_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            state = {"version": 1, "videos": {"dQw4w9WgXcQ": {"title": "曲", "last_milestone": 1, "approach_notified_for": None, "history": []}}}
            self.assertTrue(save_state(path, state))
            self.assertFalse(save_state(path, state))
            self.assertEqual(load_state(path), state)
            self.assertEqual(list(Path(d).iterdir()), [path])


class ConfigTest(unittest.TestCase):
    def write_config(self, d, urls):
        path = Path(d) / "config.json"
        path.write_text(json.dumps({**CONFIG, "playlist_urls": urls}), encoding="utf-8")
        return path

    def test_todo_and_empty_are_config_errors(self):
        with tempfile.TemporaryDirectory() as d:
            for urls in [[], ["TODO: 利用者が追記"]]:
                with self.assertRaises(check.ConfigError):
                    check.load_config(self.write_config(d, urls))

    def test_duplicate_playlists_deduped(self):
        with tempfile.TemporaryDirectory() as d:
            pid = "PL1234567890abcdef"
            _, ids = check.load_config(self.write_config(d, [pid, f"https://www.youtube.com/playlist?list={pid}"]))
            self.assertEqual(ids, [pid])

    def test_main_returns_2_for_todo_config(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write_config(d, ["TODO"])
            with mock.patch.object(check, "CONFIG_PATH", path), mock.patch("builtins.print"):
                self.assertEqual(check.main([]), 2)


class SiteDataTest(unittest.TestCase):
    def test_sorted_by_remaining_and_flags(self):
        state = {"videos": {
            "aaaaaaaaaaa": {"title": "A", "last_milestone": 3, "approach_notified_for": None,
                            "history": [{"milestone": 3, "reached_at": "2026-10-01T00:00:00Z", "views_at_detection": 3_000_100}]},
        }}
        videos = [video(2_999_000, "aaaaaaaaaaa", "A"), video(1_920_000, "bbbbbbbbbbb", "B")]
        data = build_site_data(videos, state, CONFIG, "2026-10-30T03:00:00Z")
        self.assertEqual([v["id"] for v in data["videos"]], ["bbbbbbbbbbb", "aaaaaaaaaaa"])
        b, a = data["videos"]
        self.assertTrue(b["approaching"])
        self.assertEqual(b["next_label"], "200万")
        # 減少していても表示上の節目は state の300万を維持
        self.assertEqual(a["last_milestone_label"], "300万")
        self.assertEqual(a["next_label"], "400万")
        self.assertEqual(a["last_reached_at"], "2026-10-01T00:00:00Z")
        self.assertEqual(data["recent_events"][0]["label"], "300万")


if __name__ == "__main__":
    unittest.main()
