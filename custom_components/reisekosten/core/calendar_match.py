"""Wählt aus Kalendertermine den passenden zur Reise aus. Reines Python, ohne Home Assistant."""
from __future__ import annotations

import re
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


_PLZ_CITY = re.compile(r"\b\d{5}\s+([^,\n]+)")
MIN_OVERLAP = timedelta(hours=2)


def _place(location: str | None) -> str:
    """Kurzer Ortsname: bei Adressen mit Postleitzahl nur die Stadt, sonst die erste Zeile."""
    text = (location or "").strip()
    m = _PLZ_CITY.search(text)
    return m.group(1).strip()[:80] if m else _oneline(text)


def _unique(items: list[str], sep: str) -> str:
    seen: list[str] = []
    for item in items:
        if item and item.lower() not in (x.lower() for x in seen):
            seen.append(item)
    return sep.join(seen)


def pick_event(events: list[dict], start: datetime, end: datetime) -> dict[str, str] | None:
    """Passende Termine zur Reise -> Vorschlag {name, purpose} oder None.

    Alle Termine mit mindestens 2 Stunden Überschneidung (ganztägige zählen immer) werden nach Beginn
    sortiert zusammengefasst: Orte und Titel hintereinander, doppelte nur einmal. Gibt es keinen so langen
    Termin, gilt der mit der größten Überschneidung.
    """
    hits = []                                                   # (Überschneidung, Beginn, Termin)
    for ev in events:
        s, e = _to_dt(ev.get("start"), start.tzinfo), _to_dt(ev.get("end"), start.tzinfo)
        if s is None or e is None:
            continue
        overlap = min(e, end) - max(s, start)
        if overlap > timedelta(0) and (_oneline(ev.get("summary")) or _oneline(ev.get("location"))):
            hits.append((overlap, s, ev))
    if not hits:
        return None
    chosen = [h for h in hits if h[0] >= MIN_OVERLAP] or [max(hits, key=lambda h: h[0])]
    chosen.sort(key=lambda h: h[1])
    places = [_place(h[2].get("location")) or _oneline(h[2].get("summary")) for h in chosen]
    purposes = [_oneline(h[2].get("summary")) or _place(h[2].get("location")) for h in chosen]
    return {"name": _unique(places, ", "), "purpose": _unique(purposes, "; ")}
