"""Steuerung: erkennt Reisen über die Person, fragt per Handy nach und erzeugt die PDF."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACC_CONTRA, ACC_KM, ACC_PAYMENT, ACC_PER_DIEM, ACTION_PREFIX, ARRIVAL_DEBOUNCE_SECONDS,
    CONF_CALENDARS, CONF_CITY, CONF_COMPANY, CONF_NAME, CONF_NOTIFY, CONF_PERSON, CONF_STREET, CONF_ZONE,
    ACCOUNT_TABLE, ACTIVITY_EMPLOYEE, ACTIVITY_SELF, CONF_CHART, CONF_EMPLOYMENT, CONF_ODOMETER,
    CONF_WORK_ZONE, DEFAULT_ZONE, DOMAIN, OPT_ACCOUNTS, OPT_CALENDAR_REQUIRED, OPT_OUTPUT_DIR, OPT_RULES, OPT_UPLOAD_ONEDRIVE, ONEDRIVE_FOLDER, OUTPUT_SUBDIR, PDF_VIEW_URL, STORAGE_KEY,
    STORAGE_VERSION,
)
from .core.calendar_match import pick_event
from .core.engine import Accounts, Meta, build_statement, fmt_money
from .core.rules import rules_for
from .core.wizard import (
    Pending, apply_answer, meals_to_text, next_step, parse_km, parse_meals, qualifies, qualifies_span,
    to_trip,
)

_LOGGER = logging.getLogger(__name__)


def _render(statement, path: Path) -> Path:
    """Läuft im Executor (reportlab wird erst hier importiert)."""
    from .core.pdf import render_pdf

    return render_pdf(statement, path)


class ReisekostenManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict[str, Any] = {"counter": 0, "away_since": None, "pending": {}, "trips": []}
        self._unsubs: list = []
        self._listeners: list = []
        # Eingabepuffer für die Korrektur-Entitäten im Dashboard
        self.ui: dict[str, Any] = {"selected": None, "name": "", "purpose": "", "km": 0.0,
                                   "overnight": False, "meals": ""}
        self._arrival_timer = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ Konfiguration
    @property
    def cfg(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def default_activity(self) -> str | None:
        """Tätigkeit neuer Reisen; None = bei „beides“ per Handyfrage klären."""
        return {"employee": ACTIVITY_EMPLOYEE, "both": None}.get(self.cfg.get(CONF_EMPLOYMENT), ACTIVITY_SELF)

    def rules(self, year: int):
        return rules_for(year, self.entry.options.get(OPT_RULES) or None)

    def _meta(self, p: Pending, number: str) -> Meta:
        c = self.cfg
        acc = c.get(OPT_ACCOUNTS) or {}
        chart = ACCOUNT_TABLE.get(c.get(CONF_CHART) or "custom")
        if chart:                                  # SKR03/SKR04: Konten nach Tätigkeit
            per_diem, km = chart[p.activity or ACTIVITY_SELF]
        else:
            per_diem, km = acc.get(ACC_PER_DIEM, "4664"), acc.get(ACC_KM, "")
        person_state = self.hass.states.get(c[CONF_PERSON])
        user = (person_state.name if person_state else c[CONF_NAME]).replace(" ", "")
        return Meta(
            company=c.get(CONF_COMPANY, ""), person=c[CONF_NAME],
            street=c.get(CONF_STREET, ""), city=c.get(CONF_CITY, ""),
            trip_name=p.name or "", purpose=p.purpose or "", number=number, user=user,
            status="erstellt",
            note=f"{user}, {dt_util.now():%d.%m.%Y %H:%M}: Abrechnung automatisch erstellt"
            + (f"; mehrere Abwesenheiten am {p.start:%d.%m.%Y} zusammengerechnet "
               f"({p.away_minutes // 60}:{p.away_minutes % 60:02d} Std.)" if p.away_minutes else ""),
            accounts=Accounts(
                per_diem=per_diem, km=km,
                contra=acc.get(ACC_CONTRA, ""), payment=acc.get(ACC_PAYMENT, "Bar")),
        )

    # ------------------------------------------------------------------ Start / Stopp
    async def async_start(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self.data.update(stored)
        self._ui_sync()
        person = self.cfg[CONF_PERSON]
        self._unsubs.append(async_track_state_change_event(self.hass, [person], self._on_person))
        self._unsubs.append(self.hass.bus.async_listen("mobile_app_notification_action", self._on_action))

        state = self.hass.states.get(person)
        if self.data.get("away_since") and state is not None and self._is_home(state):
            self._schedule_arrival(state.last_changed)
        async with self._lock:
            for raw in list(self.data["pending"].values()):
                await self._advance(Pending.from_dict(raw))

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._arrival_timer:
            self._arrival_timer()
            self._arrival_timer = None

    async def _save(self) -> None:
        await self._store.async_save(self.data)
        self._ui_sync()
        self._notify_listeners()

    def _notify_listeners(self) -> None:
        for callback_ in list(self._listeners):
            callback_()

    def add_listener(self, callback_):
        """Für Entitäten: wird bei jeder Änderung der Daten aufgerufen. Gibt eine Abmelde-Funktion zurück."""
        self._listeners.append(callback_)
        return lambda: self._listeners.remove(callback_) if callback_ in self._listeners else None

    # ------------------------------------------------------------------ Dashboard: Korrekturfelder
    def ui_numbers(self) -> list[str]:
        return [t["number"] for t in reversed(self.data["trips"])]

    def _ui_sync(self) -> None:
        """Hält die Auswahl gültig; bei Wechsel werden die Felder mit den Werten der Abrechnung gefüllt."""
        numbers = self.ui_numbers()
        if self.ui["selected"] not in numbers:
            self.ui["selected"] = numbers[0] if numbers else None
            self._ui_load()

    def _ui_load(self) -> None:
        trip = next((t for t in self.data["trips"] if t["number"] == self.ui["selected"]), None)
        snap = (trip or {}).get("data")
        if not trip:
            self.ui.update(name="", purpose="", km=0.0, overnight=False, meals="")
        elif not snap:
            self.ui.update(name=trip.get("name") or "", purpose=trip.get("purpose") or "", km=0.0,
                           overnight=False, meals="")
        else:
            p = Pending.from_dict(snap)
            self.ui.update(name=p.name or "", purpose=p.purpose or "", km=float(p.km_car or 0),
                           overnight=bool(p.overnight), meals=meals_to_text(p.meals))

    def ui_select(self, number: str) -> None:
        self.ui["selected"] = number
        self._ui_load()
        self._notify_listeners()

    def ui_set(self, field: str, value: Any) -> None:
        self.ui[field] = value
        self._notify_listeners()

    async def async_apply_ui(self) -> None:
        """Korrekturfelder auf die gewählte Abrechnung anwenden (PDF neu erzeugen)."""
        if not self.ui["selected"]:
            raise ValueError("Keine Abrechnung ausgewählt")
        await self.async_regenerate(self.ui["selected"], {
            "name": self.ui["name"], "purpose": self.ui["purpose"], "km_car": self.ui["km"],
            "overnight": self.ui["overnight"], "meals": self.ui["meals"] or "-"})

    async def async_delete_selected(self) -> None:
        if not self.ui["selected"]:
            raise ValueError("Keine Abrechnung ausgewählt")
        await self.async_delete_trip(self.ui["selected"])

    async def async_resend(self) -> None:
        """Offene Fragen erneut aufs Handy schicken."""
        async with self._lock:
            for raw in list(self.data["pending"].values()):
                await self._advance(Pending.from_dict(raw))

    async def async_discard_open(self) -> None:
        """Älteste offene Reise verwerfen (Knopf im Dashboard)."""
        if self.data["pending"]:
            await self.async_discard(next(iter(self.data["pending"])))

    async def async_answer_open(self, text: str) -> bool:
        """Antwort aus dem Dashboard auf die aktuell offene Frage der ältesten offenen Reise."""
        if not self.data["pending"] or not text.strip():
            return False
        pid = next(iter(self.data["pending"]))
        step = next_step(Pending.from_dict(self.data["pending"][pid]), self.rules(2026))
        return bool(step) and await self.async_answer(pid, step, text)

    def signed_link(self, number: str, hours: int = 24 * 7) -> str | None:
        """Befristeter, signierter Link zur PDF (öffnet ohne weitere Anmeldung, läuft nach `hours` ab)."""
        path = PDF_VIEW_URL.format(number=number)
        try:
            from homeassistant.components.http.auth import async_sign_path

            return async_sign_path(self.hass, path, timedelta(hours=hours), use_content_user=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Link zur PDF konnte nicht signiert werden: %s", err)
            return None

    def trip_link(self, trip: dict[str, Any]) -> str | None:
        """Signierter Link zur PDF (24 Stunden gültig, der Sensor erneuert ihn stündlich)."""
        return self.signed_link(trip["number"], hours=24) if trip.get("number") else None

    def summary(self) -> dict[str, Any]:
        """Kennzahlen für die Entitäten (Dashboard)."""
        now = dt_util.now()
        month, year = Decimal(0), Decimal(0)
        year_count = 0
        for t in self.data["trips"]:
            end = datetime.fromisoformat(t["end"])
            if end.year == now.year:
                year += Decimal(t["total"])
                year_count += 1
                if end.month == now.month:
                    month += Decimal(t["total"])
        last = self.data["trips"][-1] if self.data["trips"] else None
        open_trips = []
        for raw in self.data["pending"].values():
            p = Pending.from_dict(raw)
            step = next_step(p, self.rules(p.end.year))
            open_trips.append({"id": p.id, "start": p.start.isoformat(), "end": p.end.isoformat(),
                               "name": p.name, "waiting_for": step or "fertig"})
        return {"month_total": month, "year_total": year, "year_count": year_count, "last": last,
                "open": open_trips, "away_since": self.data.get("away_since")}

    # ------------------------------------------------------------------ Personenerkennung
    def _zone_matches(self, state: State, zone_id: str | None) -> bool:
        if not zone_id:
            return False
        if zone_id == DEFAULT_ZONE:
            return state.state == "home"
        zone = self.hass.states.get(zone_id)
        return zone is not None and state.state == zone.name

    def _base(self, state: State | None) -> str | bool | None:
        """'home' / 'work' = in der Wohn- bzw. Arbeitszone, False = unterwegs, None = unbekannt."""
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        if self._zone_matches(state, self.cfg.get(CONF_ZONE, DEFAULT_ZONE)):
            return "home"
        if self._zone_matches(state, self.cfg.get(CONF_WORK_ZONE)):
            return "work"
        return False

    def _is_home(self, state: State) -> bool | None:
        base = self._base(state)
        return None if base is None else bool(base)

    @callback
    def _on_person(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        if new is None:
            return
        base = self._base(new)
        if base is None:
            return
        if base:
            self._schedule_arrival(new.last_changed, base)
        else:
            self._on_leave(new.last_changed, self._base(event.data.get("old_state")) or None)

    def _cancel_arrival(self) -> None:
        if self._arrival_timer:
            self._arrival_timer()
            self._arrival_timer = None

    def _odometer(self) -> float | None:
        """Aktueller Kilometerstand (km) aus dem gewählten Sensor, sonst None."""
        entity = self.cfg.get(CONF_ODOMETER)
        state = self.hass.states.get(entity) if entity else None
        if state is None:
            return None
        try:
            value = float(str(state.state).replace(",", "."))
        except ValueError:
            return None
        unit = str((getattr(state, "attributes", None) or {}).get("unit_of_measurement", "")).lower()
        return value * 1.609344 if unit in ("mi", "mile", "miles") else value

    def _on_leave(self, when: datetime, origin: str | None = None) -> None:
        self._cancel_arrival()                       # kurz weg und wieder da = gleiche Reise
        if not self.data.get("away_since"):
            self.data["away_since"] = dt_util.as_utc(when).isoformat()
            self.data["away_from"] = origin
            self.data["odo_start"] = self._odometer()
            self.hass.async_create_task(self._save())

    def _schedule_arrival(self, when: datetime, at: str | None = None) -> None:
        if not self.data.get("away_since"):
            return
        self._cancel_arrival()

        async def _fire(_now: datetime) -> None:
            self._arrival_timer = None
            await self._finalize(when, at)

        self._arrival_timer = async_call_later(self.hass, ARRIVAL_DEBOUNCE_SECONDS, _fire)

    async def _finalize(self, arrival: datetime, at: str | None = None) -> None:
        async with self._lock:
            raw = self.data.get("away_since")
            if not raw:
                return
            start = dt_util.as_local(dt_util.parse_datetime(raw))
            end = dt_util.as_local(arrival)
            self.data["away_since"] = None
            origin, odo_start = self.data.pop("away_from", None), self.data.pop("odo_start", None)
            rules = self.rules(end.year)
            if self.cfg.get(CONF_WORK_ZONE) and origin and at and origin != at \
                    and not qualifies(start, end, rules):
                _LOGGER.debug("Wohn-Arbeitsstätte %s - %s, keine Dienstreise", start, end)
                await self._save()
                return
            if start.date() == end.date():
                p = await self._merge_same_day(start, end, rules)
            else:
                p = Pending(id=start.strftime("%Y%m%d%H%M"), start=start, end=end,
                            activity=self.default_activity()) \
                    if qualifies(start, end, rules) else None
            if p is None:
                await self._save()
                return
            await self._remember_suggestion(p)
            if (self.cfg.get(CONF_CALENDARS) and self.cfg.get(OPT_CALENDAR_REQUIRED)
                    and p.id not in (self.data.get("suggest") or {})):
                _LOGGER.debug("Kein passender Kalendertermin für %s - %s, keine Rückfrage", p.start, p.end)
                await self._save()
                return
            self._remember_km(p, odo_start)
            await self._advance(p)

    def _remember_km(self, p: Pending, odo_start: float | None) -> None:
        """Kilometer-Vorschlag aus der Differenz des Kilometerzähler-Sensors (Abfahrt bis Ankunft)."""
        now = self._odometer()
        if odo_start is None or now is None or now <= odo_start:
            return
        self.data.setdefault("suggest", {}).setdefault(p.id, {})["km"] = f"{now - odo_start:.1f}".rstrip("0").rstrip(".")

    async def _merge_same_day(self, start: datetime, end: datetime, rules) -> Pending | None:
        """Mehrere Abwesenheiten am selben Kalendertag werden zusammengerechnet."""
        days: dict[str, list] = self.data.setdefault("days", {})
        today = dt_util.now().date()
        for key in [k for k in days if (today - datetime.fromisoformat(k).date()).days > 3]:
            del days[key]
        key = start.date().isoformat()
        segments = days.setdefault(key, [])
        segments.append([start.isoformat(), end.isoformat()])
        parsed = [(datetime.fromisoformat(a), datetime.fromisoformat(b)) for a, b in segments]
        total = sum((b - a for a, b in parsed), timedelta(0))

        def same_day(s: str, e: str) -> bool:
            return s[:10] == key and e[:10] == key

        if any(same_day(t["start"], t["end"]) for t in self.data["trips"]):
            _LOGGER.debug("Am %s gibt es schon eine Abrechnung, weitere Abwesenheit bringt nichts", key)
            return None
        for raw in self.data["pending"].values():
            if same_day(raw["start"], raw["end"]):             # offene Reise desselben Tages erweitern
                p0 = Pending.from_dict(raw)
                p0.end = max(p0.end, end)
                p0.away_minutes = int(total.total_seconds() // 60)
                await self._advance(p0)
                return None
        if not qualifies_span(total, rules):
            return None
        first = min(a for a, _ in parsed)
        return Pending(id=first.strftime("%Y%m%d%H%M"), start=first, end=end, activity=self.default_activity(),
                       away_minutes=int(total.total_seconds() // 60) if len(parsed) > 1 else None)

    # ------------------------------------------------------------------ Rückfragen
    async def _advance(self, p: Pending) -> None:
        """Speichert den Stand und stellt die nächste Frage bzw. schließt die Abrechnung ab."""
        step = next_step(p, self.rules(p.end.year))
        self.data["pending"][p.id] = p.to_dict()
        await self._save()
        if step is None:
            await self._complete(p)
        else:
            await self._ask(p, step)

    def _question(self, p: Pending, step: str) -> tuple[str, str, bool]:
        hours = (p.away_minutes * 60 if p.away_minutes else (p.end - p.start).total_seconds()) / 3600
        header = f"Unterwegs {p.start:%d.%m. %H:%M} - {p.end:%d.%m. %H:%M} ({hours:.1f} Std.)"
        if p.away_minutes:
            header = f"Mehrere Abwesenheiten am {p.start:%d.%m.} zusammengerechnet: {hours:.1f} Std."
        if step == "activity":
            return "Reisekosten: Tätigkeit", f"{header}\nWar das eine selbstständige oder eine angestellte Reise?", False
        if step == "name":
            return "Reisekosten: Reise", f"{header}\nWohin ging die Reise? (z. B. Kunde Musterstadt)", True
        if step == "purpose":
            return "Reisekosten: Zweck", "Zweck der Reise? (z. B. Präsenzunterricht)", True
        if step == "km":
            return "Reisekosten: Kilometer", "Gefahrene Kilometer mit dem Pkw (gesamt)? Bei keinen: „Keine“ tippen.", True
        if step == "overnight":
            return "Reisekosten: Übernachtung", "Gab es eine Übernachtung auswärts?", False
        return ("Reisekosten: Mahlzeiten",
                "Gestellte Mahlzeiten? Beispiel: 08.01 FA, 09.01 M (F=Frühstück, M=Mittag, A=Abend). Wurden keine gestellt: „Keine“ tippen.",
                True)

    async def _ask(self, p: Pending, step: str, error: str | None = None) -> None:
        title, message, text_input = self._question(p, step)
        if error:
            message = f"{error}\n{message}"
        if text_input:
            actions = [{"action": f"{ACTION_PREFIX}{p.id}|{step}|reply", "title": "Antworten",
                        "behavior": "textInput", "textInputButtonTitle": "Senden"}]
            suggestion = (self.data.get("suggest") or {}).get(p.id, {}).get(step)
            if suggestion:
                message += (f"\nVorschlag vom Kilometerzähler: {suggestion} km" if step == "km"
                            else f"\nVorschlag aus dem Kalender: {suggestion}")
                actions.append({"action": f"{ACTION_PREFIX}{p.id}|{step}|accept",
                                "title": f"Übernehmen: {suggestion}"[:40]})
            if step == "name":
                actions.append({"action": f"{ACTION_PREFIX}{p.id}|{step}|discard", "title": "Keine Dienstreise"})
            elif step in ("km", "meals"):
                actions.append({"action": f"{ACTION_PREFIX}{p.id}|{step}|none", "title": "Keine"})
        elif step == "activity":
            actions = [{"action": f"{ACTION_PREFIX}{p.id}|{step}|self", "title": "Selbstständig"},
                       {"action": f"{ACTION_PREFIX}{p.id}|{step}|employee", "title": "Angestellt"},
                       {"action": f"{ACTION_PREFIX}{p.id}|{step}|discard", "title": "Keine Dienstreise"}]
        else:
            actions = [{"action": f"{ACTION_PREFIX}{p.id}|{step}|yes", "title": "Ja"},
                       {"action": f"{ACTION_PREFIX}{p.id}|{step}|no", "title": "Nein"}]
        await self._notify(title, message, {"tag": f"rk_{p.id}", "sticky": True,
                                            "persistent": True, "actions": actions})

    async def _notify(self, title: str, message: str, data: dict | None = None) -> None:
        service = self.cfg.get(CONF_NOTIFY)
        try:
            if not service:
                raise ValueError("kein Notify-Dienst eingestellt")
            await self.hass.services.async_call(
                "notify", service, {"title": title, "message": message, "data": data or {}},
                blocking=True)
        except Exception as err:  # noqa: BLE001 - Rückfall auf Benachrichtigung in HA
            _LOGGER.warning("Mobile Benachrichtigung fehlgeschlagen (%s)", err)
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"title": title, "message": message,
                 "notification_id": (data or {}).get("tag", "reisekosten")})

    async def _on_action(self, event: Event) -> None:
        action = str(event.data.get("action", ""))
        if not action.startswith(ACTION_PREFIX):
            return
        try:
            pid, step, value = action[len(ACTION_PREFIX):].split("|", 2)
        except ValueError:
            return
        if value == "discard":
            await self.async_discard(pid)
            return
        if value == "none":
            text = "-"
        elif value == "accept":
            text = (self.data.get("suggest") or {}).get(pid, {}).get(step, "")
        else:
            text = event.data.get("reply_text", "") if value == "reply" else value
        await self.async_answer(pid, step, text)

    async def async_answer(self, pid: str, step: str, text: str) -> bool:
        async with self._lock:
            raw = self.data["pending"].get(pid)
            if raw is None:
                _LOGGER.debug("Antwort für unbekannte Reise %s", pid)
                return False
            p = Pending.from_dict(raw)
            if next_step(p, self.rules(p.end.year)) != step:
                _LOGGER.debug("Veraltete Antwort für Schritt %s ignoriert", step)
                return False
            try:
                apply_answer(p, step, text)
            except ValueError as err:
                await self._ask(p, step, error=str(err))
                return False
            await self._advance(p)
            return True

    async def async_discard(self, pid: str) -> bool:
        """Offene Reise verwerfen („keine Dienstreise“)."""
        async with self._lock:
            raw = self.data["pending"].pop(pid, None)
            if raw is None:
                return False
            p = Pending.from_dict(raw)
            (self.data.get("suggest") or {}).pop(pid, None)
            (self.data.get("days") or {})[p.start.date().isoformat()] = []
            await self._save()
        await self._notify("Reisekosten", f"Reise vom {p.start:%d.%m.%Y} verworfen – keine Abrechnung.",
                           {"tag": f"rk_{pid}"})
        return True

    # ------------------------------------------------------------------ Abrechnung
    async def async_add_trip(self, p: Pending) -> None:
        """Manuell angelegte Reise (Service reisekosten.add_trip); fehlende Felder werden erfragt."""
        async with self._lock:
            await self._remember_suggestion(p)
            await self._advance(p)

    async def _remember_suggestion(self, p: Pending) -> None:
        """Sucht in den gewählten Kalendern nach einem Termin zur Reise (Vorschlag für Ziel/Zweck)."""
        calendars = self.cfg.get(CONF_CALENDARS) or []
        if not calendars or (p.name is not None and p.purpose is not None):
            return
        try:
            resp = await self.hass.services.async_call(
                "calendar", "get_events",
                {"entity_id": list(calendars), "start_date_time": p.start.isoformat(),
                 "end_date_time": p.end.isoformat()},
                blocking=True, return_response=True)
        except Exception as err:  # noqa: BLE001 - Kalender ist nur eine Hilfe
            _LOGGER.warning("Kalender konnte nicht gelesen werden: %s", err)
            return
        events = [ev for cal in (resp or {}).values() for ev in (cal or {}).get("events", [])]
        suggestion = pick_event(events, p.start, p.end)
        if suggestion:
            self.data.setdefault("suggest", {})[p.id] = suggestion

    def _output(self) -> Path:
        """Zielordner der PDFs (Standard: <config>/reisekosten; absolute Pfade bleiben absolut)."""
        custom = str(self.entry.options.get(OPT_OUTPUT_DIR) or "").strip()
        return Path(self.hass.config.path(custom)) if custom else Path(self.hass.config.path(*OUTPUT_SUBDIR))

    async def _onedrive(self, filename: str, data: bytes | None = None, delete: bool = False) -> str | None:
        """Datei im App-Ordner der HA-OneDrive-Integration ablegen oder löschen. None = ok, sonst Fehlertext."""
        try:
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            from homeassistant.helpers.config_entry_oauth2_flow import (
                OAuth2Session, async_get_config_entry_implementation)

            entries = self.hass.config_entries.async_entries("onedrive")
            if not entries:
                return "Die OneDrive-Integration ist in Home Assistant nicht eingerichtet."
            entry = entries[0]
            session = OAuth2Session(self.hass, entry, await async_get_config_entry_implementation(self.hass, entry))
            await session.async_ensure_token_valid()
            url = (f"https://graph.microsoft.com/v1.0/me/drive/special/approot:/"
                   f"{ONEDRIVE_FOLDER}/{filename}:" + ("" if delete else "/content"))
            headers = {"Authorization": f"Bearer {session.token['access_token']}"}
            web = async_get_clientsession(self.hass)
            if delete:
                resp = await web.delete(url, headers=headers)
                ok = (200, 204, 404)
            else:
                resp = await web.put(url, data=data, headers={**headers, "Content-Type": "application/pdf"})
                ok = (200, 201)
            if resp.status not in ok:
                return f"OneDrive antwortete mit Status {resp.status}."
            return None
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("OneDrive-Zugriff fehlgeschlagen: %s", err)
            return f"OneDrive-Zugriff fehlgeschlagen ({err})."

    async def _upload_onedrive(self, path: Path) -> str | None:
        data = await self.hass.async_add_executor_job(path.read_bytes)
        return await self._onedrive(path.name, data=data)

    async def _create_pdf(self, p: Pending, number: str, filename: str):
        """Rechnet, schreibt die PDF und lädt sie ggf. nach OneDrive. -> (statement, path, link, extra)."""
        statement = build_statement(to_trip(p), self._meta(p, number), self.rules(p.end.year))
        path = self._output() / filename
        await self.hass.async_add_executor_job(_render, statement, path)
        extra = ""
        if self.entry.options.get(OPT_UPLOAD_ONEDRIVE):
            err = await self._upload_onedrive(path)
            extra = (f"\nOneDrive: Apps/…/{ONEDRIVE_FOLDER}" if err is None else f"\n{err}")
        return statement, path, self.signed_link(number), extra

    async def _announce(self, p: Pending, number: str, statement, path: Path, link: str | None,
                        extra: str, title: str = "Reisekostenabrechnung") -> None:
        total = fmt_money(Decimal(statement.total))
        if link:
            await self._notify(f"{title} {number}", f"{p.name}: {total}. Zum Öffnen tippen.{extra}",
                               {"tag": f"rk_{p.id}", "url": link, "clickAction": link})
        else:   # Signatur nicht möglich: Pfad anzeigen
            await self._notify(f"{title} {number}", f"{p.name}: {total}. Gespeichert unter {path}{extra}",
                               {"tag": f"rk_{p.id}"})

    async def _complete(self, p: Pending) -> None:
        self.data["counter"] += 1
        number = f"{p.end.year}{self.data['counter']:03d}"
        filename = f"Reisekostenabrechnung_{number}_{p.start:%Y-%m-%d}.pdf"
        try:
            statement, path, link, extra = await self._create_pdf(p, number, filename)
        except Exception:  # noqa: BLE001
            self.data["counter"] -= 1
            _LOGGER.exception("PDF konnte nicht erzeugt werden")
            await self._notify("Reisekosten: Fehler",
                               f"Die PDF konnte nicht nach {self._output()} geschrieben werden. "
                               "Details stehen im HA-Log.")
            return
        self.data["pending"].pop(p.id, None)
        (self.data.get("suggest") or {}).pop(p.id, None)
        self.data["trips"].append({
            "number": number, "file": filename, "path": str(path), "start": p.start.isoformat(),
            "end": p.end.isoformat(), "name": p.name, "purpose": p.purpose,
            "total": str(statement.total), "data": p.to_dict(),
        })
        await self._save()
        await self._announce(p, number, statement, path, link, extra)
        _LOGGER.info("Reisekostenabrechnung %s erstellt: %s", number, path)

    # ------------------------------------------------------------------ Korrigieren / Löschen
    def list_trips(self) -> list[dict[str, Any]]:
        return [{k: t.get(k) for k in ("number", "start", "end", "name", "purpose", "total")}
                for t in self.data["trips"]]

    def _find_trip(self, number: str) -> dict[str, Any]:
        for t in self.data["trips"]:
            if t["number"] == str(number):
                return t
        raise ValueError(f"Abrechnung {number} nicht gefunden")

    async def async_delete_trip(self, number: str) -> None:
        """Abrechnung löschen (Eintrag, PDF, OneDrive-Kopie); der Zähler wird angepasst."""
        async with self._lock:
            trip = self._find_trip(number)
            path = Path(trip.get("path") or self._output() / trip["file"])
            self.data["trips"].remove(trip)
            nums = [int(t["number"][4:]) for t in self.data["trips"] if t["number"][4:].isdigit()]
            self.data["counter"] = max(nums, default=0)
            (self.data.get("days") or {}).pop(trip["start"][:10], None)
            await self._save()
        await self.hass.async_add_executor_job(lambda: path.unlink(missing_ok=True))
        extra = ""
        if self.entry.options.get(OPT_UPLOAD_ONEDRIVE):
            err = await self._onedrive(path.name, delete=True)
            extra = "" if err is None else f"\n{err}"
        await self._notify("Reisekosten", f"Abrechnung {number} gelöscht.{extra}")

    async def async_regenerate(self, number: str, changes: dict[str, Any]) -> None:
        """Abrechnung mit gleicher Nummer neu erzeugen, optional mit korrigierten Angaben."""
        async with self._lock:
            trip = self._find_trip(number)
            if not trip.get("data"):
                raise ValueError(f"Abrechnung {number} stammt aus einer älteren Version und lässt sich nicht "
                                 "neu erzeugen. Bitte löschen und neu anlegen.")
            p = Pending.from_dict(trip["data"])
            if changes.get("name"):
                p.name = changes["name"]
            if changes.get("purpose"):
                p.purpose = changes["purpose"]
            if "km_car" in changes and self.rules(p.end.year).km_enabled:
                p.km_car = parse_km(str(changes["km_car"]))
            if "overnight" in changes:
                p.overnight = bool(changes["overnight"])
            if "meals" in changes:
                p.meals = parse_meals(changes["meals"], p.start, p.end)
            statement, path, link, extra = await self._create_pdf(p, trip["number"], trip["file"])
            trip.update({"path": str(path), "name": p.name, "purpose": p.purpose,
                         "total": str(statement.total), "data": p.to_dict()})
            await self._save()
        await self._announce(p, trip["number"], statement, path, link, extra, title="Neu erzeugt:")
