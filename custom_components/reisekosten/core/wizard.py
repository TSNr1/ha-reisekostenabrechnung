"""Rückfrage-Ablauf (Wizard) nach einer Reise. Reines Python, ohne Home Assistant."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from .engine import Trip, per_diem
from .rules import Rules

STEPS = ("name", "purpose", "km", "overnight", "meals")
SKIP = {"", "-", "nein", "keine", "0"}
MEAL_LETTERS = {"F": "breakfast", "M": "lunch", "A": "dinner"}


@dataclass
class Pending:
    id: str
    start: datetime
    end: datetime
    name: str | None = None
    purpose: str | None = None
    km_car: Decimal | None = None
    overnight: bool | None = None
    meals: dict[date, set[str]] | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "start": self.start.isoformat(), "end": self.end.isoformat(),
            "name": self.name, "purpose": self.purpose,
            "km_car": None if self.km_car is None else str(self.km_car),
            "overnight": self.overnight,
            "meals": None if self.meals is None else
            {d.isoformat(): sorted(v) for d, v in self.meals.items()},
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Pending":
        meals = data.get("meals")
        return cls(
            id=data["id"],
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            name=data.get("name"), purpose=data.get("purpose"),
            km_car=None if data.get("km_car") is None else Decimal(data["km_car"]),
            overnight=data.get("overnight"),
            meals=None if meals is None else
            {date.fromisoformat(k): set(v) for k, v in meals.items()},
            note=data.get("note", ""),
        )


def crosses_midnight(p: Pending) -> bool:
    return p.start.date() != p.end.date()


def to_trip(p: Pending) -> Trip:
    km = {"car": p.km_car} if p.km_car and p.km_car > 0 else {}
    return Trip(p.start, p.end, overnight=bool(p.overnight), meals=p.meals or {}, km=km)


def qualifies(start: datetime, end: datetime, rules: Rules) -> bool:
    """Gibt es für diese Abwesenheit überhaupt eine Verpflegungspauschale?"""
    span = end - start
    if span <= timedelta(0):
        return False
    limit = timedelta(hours=float(rules.min_hours))
    return span > limit if rules.strictly_more_than else span >= limit


def next_step(p: Pending, rules: Rules) -> str | None:
    if p.name is None:
        return "name"
    if p.purpose is None:
        return "purpose"
    if p.km_car is None:
        if rules.km_enabled:
            return "km"
        p.km_car = Decimal(0)            # Kilometer werden nicht abgerechnet
    if p.overnight is None:
        days = (p.end.date() - p.start.date()).days
        if days == 1:
            return "overnight"
        p.overnight = days >= 2          # eintägig: nein, ab zwei Mitternächten: ja
    if p.meals is None:
        if per_diem(to_trip(p), rules):
            return "meals"
        p.meals = {}
    return None


def parse_km(text: str) -> Decimal:
    t = text.strip().lower().replace("km", "").replace(",", ".").strip()
    if t in SKIP:
        return Decimal("0")
    try:
        value = Decimal(t)
    except InvalidOperation as err:
        raise ValueError("Bitte eine Zahl eingeben, z. B. 123,5") from err
    if value < 0:
        raise ValueError("Kilometer dürfen nicht negativ sein")
    return value


_MEAL_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\s*([FMA]*)$", re.I)


def parse_meals(text: str, start: datetime, end: datetime) -> dict[date, set[str]]:
    """'08.01 FA, 09.01 M' -> {8.1.: {Frühstück, Abend}, 9.1.: {Mittag}}.
    F = Frühstück, M = Mittag, A = Abend. Ohne Buchstaben: alle drei Mahlzeiten."""
    if text.strip().lower() in SKIP:
        return {}
    result: dict[date, set[str]] = {}
    for part in re.split(r"[,;]", text):
        part = part.strip()
        if not part:
            continue
        m = _MEAL_RE.match(part)
        if not m:
            raise ValueError(f"'{part}' nicht verständlich. Beispiel: 08.01 FA, 09.01 M")
        day, month, year, letters = int(m[1]), int(m[2]), m[3], m[4].upper()
        year_i = start.year if not year else (int(year) + 2000 if len(year) == 2 else int(year))
        try:
            d = date(year_i, month, day)
        except ValueError as err:
            raise ValueError(f"'{part}' ist kein gültiges Datum") from err
        if not (start.date() <= d <= end.date()):
            raise ValueError(f"{d:%d.%m.%Y} liegt nicht im Reisezeitraum")
        meals = {MEAL_LETTERS[c] for c in letters} or set(MEAL_LETTERS.values())
        result.setdefault(d, set()).update(meals)
    return result


def apply_answer(p: Pending, step: str, text: str) -> None:
    """Übernimmt eine Antwort. Wirft ValueError bei Eingabefehlern."""
    text = (text or "").strip()
    if step == "name":
        p.name = "Dienstreise" if text in ("", "-") else text
    elif step == "purpose":
        p.purpose = "Dienstreise" if text in ("", "-") else text
    elif step == "km":
        p.km_car = parse_km(text)
    elif step == "overnight":
        p.overnight = text.lower() in ("yes", "ja", "j", "true")
    elif step == "meals":
        p.meals = parse_meals(text, p.start, p.end)
    else:
        raise ValueError(f"Unbekannter Schritt: {step}")
