"""マイルストーン判定。API・Discord・ファイルI/Oに依存しない純粋関数だけを置く。"""

from __future__ import annotations

from dataclasses import dataclass


def label(milestone: int, step: int = 1_000_000) -> str:
    """節目番号を「100万」のような表示に変える。"""
    return f"{milestone * step // 10000}万"


def compute_milestone(views: int, step: int) -> int:
    return views // step


@dataclass(frozen=True)
class Decision:
    """1動画分の判定結果。stateの書き換えは呼び出し側が送信成功後に行う。"""

    is_new: bool
    current_milestone: int  # 減少時は前回値を維持した「実効」節目
    reached_from: int | None  # 到達通知が必要なら前回の節目番号
    next_milestone: int
    remaining: int
    approach_notify: bool

    @property
    def reached(self) -> bool:
        return self.reached_from is not None

    @property
    def skipped_multiple(self) -> bool:
        return self.reached and self.current_milestone - self.reached_from > 1


def decide_notifications(
    entry: dict | None,
    views: int,
    step: int,
    discord_approach_remaining: int,
) -> Decision:
    m_now = compute_milestone(views, step)
    reached_from = None

    if entry is None:
        current = m_now
    else:
        last = entry["last_milestone"]
        if m_now > last:
            reached_from = last
            current = m_now
        else:
            # 再生数補正で一時的に減っても節目は下げない。
            # 下げると次回に同じ節目を再通知してしまう。
            current = last

    next_milestone = current + 1
    remaining = next_milestone * step - views
    already_notified = entry is not None and entry.get("approach_notified_for") == next_milestone
    approach_notify = remaining <= discord_approach_remaining and not already_notified

    return Decision(
        is_new=entry is None,
        current_milestone=current,
        reached_from=reached_from,
        next_milestone=next_milestone,
        remaining=remaining,
        approach_notify=approach_notify,
    )


def progress_ratio(views: int, current_milestone: int, step: int) -> float:
    """現在の節目から次の節目までの進捗(0.0〜1.0)。"""
    ratio = (views - current_milestone * step) / step
    return min(max(ratio, 0.0), 1.0)
