"""Rechtliche Vorgaben für die Reisekostenabrechnung.

Alle Werte sind einstellbar. Die Standardwerte entsprechen den Inlandssätzen
für 2026 (14 EUR / 28 EUR, km-Pauschalen 0,30 / 0,20 EUR). Die Regeln sind
bewusst reine Daten, damit sie später über die Optionen der Integration oder
eine JSON-Datei pro Jahr überschrieben werden können.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from decimal import Decimal

D = Decimal

MIDNIGHT_RULES = ("larger_share", "end_day", "start_day")


@dataclass(frozen=True)
class Rules:
    country: str = "Deutschland"

    # Verpflegungsmehraufwand
    p8: Decimal = D("14")                 # eintägig, mehr als min_hours
    p24: Decimal = D("28")                # voller Kalendertag (24 h)
    arrival_departure: Decimal = D("14")  # An-/Abreisetag bei mehrtägiger Reise
    min_hours: Decimal = D("8")
    strictly_more_than: bool = True       # True = "mehr als 8 h", False = ab 8 h

    # Kürzung bei gestellten Mahlzeiten (Anteil von p24)
    cut_breakfast: Decimal = D("0.20")
    cut_lunch: Decimal = D("0.40")
    cut_dinner: Decimal = D("0.40")

    # Fahrtkosten je km. Aus, wenn das Fahrzeug über den Betrieb läuft (keine km-Abrechnung).
    km_enabled: bool = True
    km_car: Decimal = D("0.30")
    km_motorcycle: Decimal = D("0.30")
    km_scooter: Decimal = D("0.20")

    # Übernachtung ohne Beleg (Inland)
    lodging_flat: Decimal = D("20")

    # Reise über Mitternacht ohne Übernachtung: welchem Kalendertag wird die
    # Pauschale zugeordnet? (Bitte mit dem Steuerberater abstimmen.)
    midnight_rule: str = "larger_share"

    def __post_init__(self) -> None:
        if self.midnight_rule not in MIDNIGHT_RULES:
            raise ValueError(f"midnight_rule muss eines von {MIDNIGHT_RULES} sein")

    @classmethod
    def from_dict(cls, data: dict) -> "Rules":
        """Erzeugt Regeln aus einem Dict (z. B. Optionen oder JSON)."""
        known = {f.name: f for f in fields(cls)}
        kwargs = {}
        for key, value in data.items():
            if key not in known:
                raise ValueError(f"Unbekannte Regel: {key}")
            if key in ("country", "midnight_rule"):
                kwargs[key] = str(value)
            elif key in ("strictly_more_than", "km_enabled"):
                kwargs[key] = bool(value)
            else:
                kwargs[key] = D(str(value))
        return cls(**kwargs)

    def to_dict(self) -> dict:
        out = {}
        for f in fields(self):
            v = getattr(self, f.name)
            out[f.name] = str(v) if isinstance(v, Decimal) else v
        return out


# Sätze je Jahr. Für die Inlandspauschalen waren 2024-2026 unverändert.
RULES_BY_YEAR: dict[int, Rules] = {y: Rules() for y in (2024, 2025, 2026)}


def rules_for(year: int, overrides: dict | None = None) -> Rules:
    """Regeln für ein Jahr; fehlt es, gilt das nächstkleinere bekannte Jahr."""
    known = sorted(RULES_BY_YEAR)
    base = RULES_BY_YEAR[max([y for y in known if y <= year] or [known[0]])]
    if overrides:
        return Rules.from_dict({**base.to_dict(), **overrides})
    return base
