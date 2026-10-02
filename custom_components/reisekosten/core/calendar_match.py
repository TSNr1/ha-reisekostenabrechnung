"""Wählt aus Kalendertermine den passenden zur Reise aus. Reines Python, ohne Home Assistant."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta


def _to_dt(value: str, tz) -> datetime | None:
    try:
        if len(value) == 10:                                   # ganztägig: 2026-03-02
            return datetime.combine(date.fromisoformat(value), time(0), tzinfo=tz)
        d = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=tz)


def _oneline(text: str | None, limit: int = 80) -> str:
    first = (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""
    return first[:limit]


def pick_event(events: list[dict], start: datetime, end: datetime) -> dict[str, str] | None:
    """Termin mit der größten Überschneidung -> Vorschlag {name, purpose} oder None."""
    best, best_overlap = None, timedelta(0)
    for ev in events:
        s, e = _to_dt(ev.get("start"), start.tzinfo), _to_dt(ev.get("end"), start.tzinfo)
        if s is None or e is None:
            continue
        overlap = min(e, end) - max(s, start)
        if overlap > best_overlap:
            best, best_overlap = ev, overlap
    if best is None:
        return None
    summary = _oneline(best.get("summary"))
    location = _oneline(best.get("location"))
    if not summary and not location:
        return None
    return {"name": location or summary, "purpose": summary or location}
