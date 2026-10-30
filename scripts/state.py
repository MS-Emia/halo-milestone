"""state.json の読み書き。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

STATE_VERSION = 1


class StateError(Exception):
    pass


def empty_state() -> dict:
    return {"version": STATE_VERSION, "videos": {}}


def load_state(path: Path) -> dict:
    """無ければ空の state を返す。壊れていたら StateError(自動初期化すると全通知状態を失うため)。"""
    if not path.exists():
        return empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise StateError(f"{path.name} を読めません: {e}") from e
    _validate(state, path.name)
    return state


def _validate(state, name: str) -> None:
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        raise StateError(f"{name} の形式またはバージョンが想定外です")
    videos = state.get("videos")
    if not isinstance(videos, dict):
        raise StateError(f"{name} の videos が不正です")
    for video_id, entry in videos.items():
        ok = (
            isinstance(entry, dict)
            and _is_int(entry.get("last_milestone"))
            and (entry.get("approach_notified_for") is None or _is_int(entry.get("approach_notified_for")))
            and isinstance(entry.get("history", []), list)
        )
        if not ok:
            raise StateError(f"{name} の動画 {video_id} のデータが不正です")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def dump_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_atomic(path: Path, text: str) -> None:
    """一時ファイルに書いてからリネームし、途中で落ちても元ファイルを壊さない。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save_state(path: Path, state: dict) -> bool:
    """内容が変わったときだけ書く。書いたら True。"""
    text = dump_json(state)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    write_atomic(path, text)
    return True
