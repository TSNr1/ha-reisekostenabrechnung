"""Rechenkern der Reisekostenabrechnung (reines Python, ohne Home-Assistant-Abhängigkeit)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from .rules import Rules

CENT = Decimal("0.01")
ZERO = Decimal("0")

MEAL_NAMES = {"breakfast": "Frühstück", "lunch": "Mittagessen", "dinner": "Abendessen"}
VEHICLE_NAMES = {"car": "Pkw", "motorcycle": "Motorrad", "scooter": "Motorroller"}


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, ROUND_HALF_UP)


def fmt_money(value: Decimal) -> str:
    """14.5 -> '14,50 EUR' (deutsches Format, Tausenderpunkt)."""
    s = f"{money(value):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " EUR"


def fmt_hours(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _elapsed(a: datetime, b: datetime) -> timedelta:
    """Echte verstrichene Zeit (auch über Zeitumstellungen hinweg)."""
    return b.astimezone(timezone.utc) - a.astimezone(timezone.utc)


@dataclass
class Trip:
    """Eine Reise: Abfahrt, Rückkehr und alles, was Home Assistant nicht wissen kann."""

    start: datetime
    end: datetime
    overnight: bool = False                      # Auswärtsübernachtung?
    meals: dict[date, set[str]] = field(default_factory=dict)   # gestellte Mahlzeiten
    km: dict[str, Decimal] = field(default_factory=dict)        # car | motorcycle | scooter
    # Nur eintägig: tatsächlich abwesende Zeit, wenn mehrere Abwesenheiten desselben
    # Kalendertages zusammengerechnet werden (sonst: Ende minus Start).
    away: timedelta | None = None

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start und end brauchen eine Zeitzone")
        self.end = self.end.astimezone(self.start.tzinfo)
        if self.end <= self.start:
            raise ValueError("Ende muss nach dem Start liegen")
        if (self.end.date() - self.start.date()).days >= 2:
            self.overnight = True                # mehr als eine Mitternacht => mehrtägig


@dataclass(frozen=True)
class DayAmount:
    day: date
    kind: str                    # single | arrival | full | departure
    shown: timedelta             # angezeigte Abwesenheit an diesem Tag
    gross: Decimal               # Pauschale vor Kürzung
    cut: Decimal = ZERO          # Kürzung (positiv)
    meals: tuple[str, ...] = ()

    @property
    def net(self) -> Decimal:
        return self.gross - self.cut


@dataclass(frozen=True)
class Line:
    day: date
    text: str
    sub: str | None
    net: Decimal
    tax: Decimal = ZERO

    @property
    def gross(self) -> Decimal:
        return self.net + self.tax


@dataclass(frozen=True)
class Accounts:
    per_diem: str = "4664"
    per_diem_label: str = "Mahlzeiten-Pauschale DE"
    km: str = ""
    km_label: str = "Fahrtkosten-Pauschale DE"
    contra: str = ""
    payment: str = "Bar"


@dataclass(frozen=True)
class Meta:
    company: str
    person: str
    street: str
    city: str
    trip_name: str = ""
    purpose: str = ""
    route: str = ""
    number: str = ""
    user: str = ""
    status: str = "erstellt"
    note: str = ""
    accounts: Accounts = field(default_factory=Accounts)


@dataclass(frozen=True)
class Booking:
    label: str
    payment: str
    tax_rate: str
    account: str
    contra: str
    gross: Decimal
    tax: Decimal
    net: Decimal


@dataclass(frozen=True)
class Statement:
    trip: Trip
    meta: Meta
    rules: Rules
    days: list[DayAmount]
    lines: list[Line]
    bookings: list[Booking]
    calendar_days: int

    @property
    def total(self) -> Decimal:
        return sum((l.gross for l in self.lines), ZERO)

    @property
    def per_diem_total(self) -> Decimal:
        return sum((d.net for d in self.days), ZERO)


def _qualifies(span: timedelta, rules: Rules) -> bool:
    limit = timedelta(hours=float(rules.min_hours))
    return span > limit if rules.strictly_more_than else span >= limit


def _cut_for(meals: set[str], rules: Rules) -> Decimal:
    pct = {"breakfast": rules.cut_breakfast, "lunch": rules.cut_lunch,
           "dinner": rules.cut_dinner}
    return money(sum((rules.p24 * pct[m] for m in meals), ZERO))


def per_diem(trip: Trip, rules: Rules) -> list[DayAmount]:
    """Verpflegungspauschale je Kalendertag, inklusive Kürzung für gestellte Mahlzeiten."""
    s, e = trip.start, trip.end
    d0, d1 = s.date(), e.date()
    raw: list[DayAmount] = []

    if d0 == d1:
        span = trip.away if trip.away is not None else _elapsed(s, e)
        if _qualifies(span, rules):
            raw.append(DayAmount(d0, "single", span, rules.p8))

    elif trip.overnight:
        tz = s.tzinfo
        arrival_shown = datetime.combine(d0 + timedelta(days=1), time(0, 0), tz) - s
        departure_shown = e - datetime.combine(d1, time(0, 0), tz)
        raw.append(DayAmount(d0, "arrival", arrival_shown, rules.arrival_departure))
        day = d0 + timedelta(days=1)
        while day < d1:
            raw.append(DayAmount(day, "full", timedelta(hours=24), rules.p24))
            day += timedelta(days=1)
        raw.append(DayAmount(d1, "departure", departure_shown, rules.arrival_departure))

    else:  # über Mitternacht, aber ohne Übernachtung
        span = _elapsed(s, e)
        if _qualifies(span, rules):
            midnight = datetime.combine(d1, time(0, 0), s.tzinfo)
            before, after = _elapsed(s, midnight), _elapsed(midnight, e)
            if rules.midnight_rule == "end_day":
                day = d1
            elif rules.midnight_rule == "start_day":
                day = d0
            else:
                day = d0 if before > after else d1
            raw.append(DayAmount(day, "single", span, rules.p8))

    result = []
    for d in raw:
        meals = trip.meals.get(d.day, set())
        cut = min(_cut_for(meals, rules), d.gross)
        result.append(DayAmount(d.day, d.kind, d.shown, d.gross, cut,
                                tuple(m for m in MEAL_NAMES if m in meals)))
    return result


def _km_text(km: Decimal) -> str:
    return f"{km.normalize():f}".replace(".", ",")


def build_statement(trip: Trip, meta: Meta, rules: Rules) -> Statement:
    days = per_diem(trip, rules)
    lines: list[Line] = []

    run: list[DayAmount] = []

    def flush_run() -> None:
        if not run:
            return
        first = run[0]
        if len(run) == 1:
            text = f"Verpflegungspausch. {fmt_date(first.day)} voller Tag"
        else:
            text = (f"Verpflegungspausch. {len(run)} Tage ab {fmt_date(first.day)} "
                    f"x {int(first.gross) if first.gross == int(first.gross) else first.gross} EUR")
        lines.append(Line(first.day, text, None, sum((d.net for d in run), ZERO)))
        run.clear()

    for d in days:
        if d.kind == "full" and not d.meals:
            run.append(d)
            continue
        flush_run()
        stamp = fmt_date(d.day)
        hours = fmt_hours(d.shown)
        if d.kind == "arrival":
            lines.append(Line(d.day, f"Verpflegungspausch. {stamp} Anreisetag ({hours} Std.)",
                              f"Abreise: {trip.start:%H:%M}", d.gross))
        elif d.kind == "departure":
            lines.append(Line(d.day, f"Verpflegungspausch. {stamp} Abreisetag ({hours} Std.)",
                              f"Rückkehr: {trip.end:%H:%M}", d.gross))
        elif d.kind == "single":
            lines.append(Line(d.day, f"Verpflegungspausch. {stamp} ({hours} Std.)",
                              f"Abreise: {trip.start:%H:%M}, Rückkehr: {trip.end:%H:%M}", d.gross))
        else:  # voller Tag mit Kürzung
            lines.append(Line(d.day, f"Verpflegungspausch. {stamp} voller Tag", None, d.gross))
        if d.cut:
            names = ", ".join(MEAL_NAMES[m] for m in d.meals)
            lines.append(Line(d.day, f"Kürzung gestellte Mahlzeiten {stamp}: {names}", None, -d.cut))
    flush_run()

    km_total = ZERO
    for key, rate in (("car", rules.km_car), ("motorcycle", rules.km_motorcycle),
                      ("scooter", rules.km_scooter)):
        km = Decimal(str(trip.km.get(key, 0)))
        if km > 0:
            amount = money(km * rate)
            km_total += amount
            lines.append(Line(trip.start.date(),
                              f"Fahrtkosten {VEHICLE_NAMES[key]}: {_km_text(km)} km x {fmt_money(rate)}",
                              None, amount))

    acc = meta.accounts
    bookings: list[Booking] = []
    pd_total = sum((d.net for d in days), ZERO)
    if pd_total:
        bookings.append(Booking(acc.per_diem_label, acc.payment, "0.0", acc.per_diem,
                                acc.contra, pd_total, ZERO, pd_total))
    if km_total:
        bookings.append(Booking(acc.km_label, acc.payment, "0.0", acc.km,
                                acc.contra, km_total, ZERO, km_total))

    calendar_days = (trip.end.date() - trip.start.date()).days + 1
    return Statement(trip, meta, rules, days, lines, bookings, calendar_days)
