"""YouTube Data API v3 から再生リストの動画と再生数を取得する。"""

from __future__ import annotations

import re
import urllib.parse

import net

API_BASE = "https://www.googleapis.com/youtube/v3"
PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,64}$")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
BATCH_SIZE = 50
THUMBNAIL_PREFERENCE = ("medium", "high", "standard", "default")


class YouTubeError(Exception):
    pass


def parse_playlist_id(value: str) -> str:
    """再生リストURL(list= を含む)またはIDそのものから、検証済みIDを返す。"""
    value = value.strip()
    if "://" in value or "list=" in value:
        query = urllib.parse.urlparse(value).query
        ids = urllib.parse.parse_qs(query).get("list", [])
        if not ids:
            raise ValueError(f"URLに list= がありません: {value}")
        value = ids[0]
    if not PLAYLIST_ID_RE.fullmatch(value):
        raise ValueError(f"再生リストIDの形式が不正です: {value}")
    return value


def _get(endpoint: str, params: dict, api_key: str) -> dict:
    url = f"{API_BASE}/{endpoint}?" + urllib.parse.urlencode({**params, "key": api_key})
    res = net.request("GET", url)
    if res.status == 200:
        body = res.json()
        if not isinstance(body, dict):
            raise YouTubeError(f"{endpoint}: 想定外のレスポンス形式です")
        return body
    raise YouTubeError(_describe_error(endpoint, res))


def _describe_error(endpoint: str, res: net.Response) -> str:
    reason = ""
    try:
        errors = res.json()["error"]["errors"]
        reason = errors[0].get("reason", "")
    except (ValueError, KeyError, IndexError, TypeError):
        pass
    hints = {
        "quotaExceeded": "1日のクォータを使い切りました。日本時間16〜17時頃(太平洋時間0時)のリセットを待ってください",
        "dailyLimitExceeded": "1日のクォータを使い切りました",
        "keyInvalid": "APIキーが無効です。Secrets の YOUTUBE_API_KEY を確認してください",
        "accessNotConfigured": "Google Cloud で YouTube Data API v3 が有効になっていません",
        "forbidden": "アクセスが拒否されました(APIキーの制限設定を確認してください)",
        "playlistNotFound": "再生リストが見つかりません。非公開になっていないか、IDが正しいか確認してください",
    }
    hint = hints.get(reason, "")
    return f"YouTube API {endpoint} がHTTP {res.status}を返しました(reason={reason or '不明'}){' — ' + hint if hint else ''}"


def fetch_video_ids(api_key: str, playlist_id: str) -> list[str]:
    ids: list[str] = []
    page_token = None
    while True:
        params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": BATCH_SIZE}
        if page_token:
            params["pageToken"] = page_token
        body = _get("playlistItems", params, api_key)
        for item in body.get("items", []):
            video_id = (item.get("contentDetails") or {}).get("videoId")
            if isinstance(video_id, str) and VIDEO_ID_RE.fullmatch(video_id):
                ids.append(video_id)
        page_token = body.get("nextPageToken")
        if not isinstance(page_token, str) or not page_token:
            return ids


def parse_video_item(item: dict) -> dict | None:
    """videos.list の1件を内部形式にする。再生数が取れないものは None。"""
    video_id = item.get("id")
    if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
        return None
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    try:
        views = int(stats["viewCount"])
    except (KeyError, TypeError, ValueError):
        return None
    if views < 0:
        return None

    title = snippet.get("title")
    published_at = snippet.get("publishedAt")
    return {
        "id": video_id,
        "title": title if isinstance(title, str) else "",
        "thumbnail_url": _pick_thumbnail(snippet.get("thumbnails")),
        "published_at": published_at if isinstance(published_at, str) else "",
        "views": views,
    }


def _pick_thumbnail(thumbnails) -> str:
    if not isinstance(thumbnails, dict):
        return ""
    for size in THUMBNAIL_PREFERENCE:
        url = (thumbnails.get(size) or {}).get("url")
        if isinstance(url, str) and url.startswith("https://"):
            return url
    return ""


def fetch_video_stats(api_key: str, video_ids: list[str], log=print) -> list[dict]:
    videos = []
    for start in range(0, len(video_ids), BATCH_SIZE):
        chunk = video_ids[start : start + BATCH_SIZE]
        body = _get("videos", {"part": "snippet,statistics", "id": ",".join(chunk)}, api_key)
        returned = set()
        for item in body.get("items", []):
            if not isinstance(item, dict):
                continue
            returned.add(item.get("id"))
            video = parse_video_item(item)
            if video is None:
                log(f"skip: 再生数を取得できない動画 {item.get('id')}(再生数非公開など)")
                continue
            videos.append(video)
        for missing in sorted(set(chunk) - returned):
            log(f"skip: 非公開または削除された動画 {missing}")
    return videos
