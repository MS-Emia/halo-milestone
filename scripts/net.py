"""YouTube API と Discord で共通の HTTP 送受信(標準ライブラリのみ)。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

# Python標準のUA("Python-urllib/3.x")はCloudflare配下のDiscordで拒否されることがあるため明示する
USER_AGENT = "kanata-milestone-notifier/1.0 (personal, non-commercial)"
TIMEOUT_SECONDS = 10
MAX_RETRIES = 3


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8")) if self.body else None


class NetworkError(Exception):
    """再試行しても接続できなかった。メッセージにURL(=秘密情報を含みうる)は入れない。"""


def request(method: str, url: str, payload: dict | None = None, sleep=time.sleep) -> Response:
    """リクエストを送り、ネットワーク障害・5xxは指数バックオフ(1,2,4秒)で再試行する。

    4xxは再試行せずそのまま返す(429の扱いは呼び出し側が決める)。
    """
    data = None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_problem = ""
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as res:
                return Response(res.status, dict(res.headers), res.read())
        except urllib.error.HTTPError as e:
            res = Response(e.code, dict(e.headers or {}), e.read() or b"")
            if e.code < 500:
                return res
            last_problem = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            # URLError.reason は URL を含まない(ホスト名解決失敗などの理由のみ)
            last_problem = type(e).__name__ + (f": {e.reason}" if hasattr(e, "reason") else "")
        if attempt < MAX_RETRIES:
            sleep(2**attempt)
    raise NetworkError(f"{MAX_RETRIES}回再試行しましたが失敗しました({last_problem})")
