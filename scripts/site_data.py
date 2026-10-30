"""サイト表示用の site/data.json を組み立てる。"""

from __future__ import annotations

from milestones import compute_milestone, label, progress_ratio

RECENT_EVENTS_LIMIT = 20


def build_site_data(videos: list[dict], state: dict, config: dict, generated_at: str) -> dict:
    step = config["milestone_step"]
    site_threshold = config["site_approach_remaining"]
    entries = state["videos"]

    rows = []
    for video in videos:
        entry = entries.get(video["id"], {})
        # state 側の節目を優先し、再生数が一時的に減っても表示上の節目を下げない
        current = max(entry.get("last_milestone", 0), compute_milestone(video["views"], step))
        next_milestone = current + 1
        remaining = next_milestone * step - video["views"]
        history = entry.get("history", [])
        rows.append(
            {
                "id": video["id"],
                "title": video["title"],
                "thumbnail_url": video["thumbnail_url"],
                "published_at": video["published_at"],
                "views": video["views"],
                "last_milestone": current,
                "last_milestone_label": label(current, step) if current > 0 else None,
                "next_milestone": next_milestone,
                "next_label": label(next_milestone, step),
                "remaining": remaining,
                "progress": round(progress_ratio(video["views"], current, step), 4),
                "approaching": remaining <= site_threshold,
                "last_reached_at": history[-1]["reached_at"] if history else None,
            }
        )
    rows.sort(key=lambda r: r["remaining"])

    return {
        "generated_at": generated_at,
        "milestone_step": step,
        "videos": rows,
        "recent_events": _recent_events(entries, step),
    }


def _recent_events(entries: dict, step: int) -> list[dict]:
    events = []
    for video_id, entry in entries.items():
        for item in entry.get("history", []):
            events.append(
                {
                    "id": video_id,
                    "title": entry.get("title", ""),
                    "milestone": item["milestone"],
                    "label": label(item["milestone"], step),
                    "reached_at": item["reached_at"],
                    "views_at_detection": item.get("views_at_detection"),
                }
            )
    events.sort(key=lambda e: e["reached_at"], reverse=True)
    return events[:RECENT_EVENTS_LIMIT]
