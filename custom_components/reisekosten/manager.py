"""Steuerung: erkennt Reisen über die Person, fragt per Handy nach und erzeugt die PDF."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
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
    CONF_CITY, CONF_COMPANY, CONF_NAME, CONF_NOTIFY, CONF_PERSON, CONF_STREET, CONF_ZONE,
    DEFAULT_ZONE, DOMAIN, OPT_ACCOUNTS, OPT_OUTPUT_DIR, OPT_RULES, OPT_UPLOAD_ONEDRIVE, ONEDRIVE_FOLDER, OUTPUT_SUBDIR, OUTPUT_URL, STORAGE_KEY,
    STORAGE_VERSION,
)
from .core.engine import Accounts, Meta, build_statement, fmt_money
from .core.rules import rules_for
from .core.wizard import Pending, apply_answer, next_step, qualifies, to_trip

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
        self._arrival_timer = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ Konfiguration
    @property
    def cfg(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def rules(self, year: int):
        return rules_for(year, self.entry.options.get(OPT_RULES) or None)

    def _meta(self, p: Pending, number: str) -> Meta:
        c = self.cfg
        acc = c.get(OPT_ACCOUNTS) or {}
        person_state = self.hass.states.get(c[CONF_PERSON])
        user = (person_state.name if person_state else c[CONF_NAME]).replace(" ", "")
        return Meta(
            company=c.get(CONF_COMPANY, ""), person=c[CONF_NAME],
            street=c.get(CONF_STREET, ""), city=c.get(CONF_CITY, ""),
            trip_name=p.name or "", purpose=p.purpose or "", number=number, user=user,
            status="erstellt",
            note=f"{user}, {dt_util.now():%d.%m.%Y %H:%M}: Abrechnung automatisch erstellt",
            accounts=Accounts(
                per_diem=acc.get(ACC_PER_DIEM, "4664"), km=acc.get(ACC_KM, ""),
                contra=acc.get(ACC_CONTRA, ""), payment=acc.get(ACC_PAYMENT, "Bar")),
        )

    # ------------------------------------------------------------------ Start / Stopp
    async def async_start(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self.data.update(stored)
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

    # ------------------------------------------------------------------ Personenerkennung
    def _is_home(self, state: State) -> bool | None:
        if state.state in ("unknown", "unavailable"):
            return None
        zone_id = self.cfg.get(CONF_ZONE, DEFAULT_ZONE)
        if zone_id == DEFAULT_ZONE:
            return state.state == "home"
        zone = self.hass.states.get(zone_id)
        return zone is not None and state.state == zone.name

    @callback
    def _on_person(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        if new is None:
            return
        home = self._is_home(new)
        if home is None:
            return
        if home:
            self._schedule_arrival(new.last_changed)
        else:
            self._on_leave(new.last_changed)

    def _cancel_arrival(self) -> None:
        if self._arrival_timer:
            self._arrival_timer()
            self._arrival_timer = None

    def _on_leave(self, when: datetime) -> None:
        self._cancel_arrival()                       # kurz weg und wieder da = gleiche Reise
        if not self.data.get("away_since"):
            self.data["away_since"] = dt_util.as_utc(when).isoformat()
            self.hass.async_create_task(self._save())

    def _schedule_arrival(self, when: datetime) -> None:
        if not self.data.get("away_since"):
            return
        self._cancel_arrival()

        async def _fire(_now: datetime) -> None:
            self._arrival_timer = None
            await self._finalize(when)

        self._arrival_timer = async_call_later(self.hass, ARRIVAL_DEBOUNCE_SECONDS, _fire)

    async def _finalize(self, arrival: datetime) -> None:
        async with self._lock:
            raw = self.data.get("away_since")
            if not raw:
                return
            start = dt_util.as_local(dt_util.parse_datetime(raw))
            end = dt_util.as_local(arrival)
            self.data["away_since"] = None
            if not qualifies(start, end, self.rules(end.year)):
                _LOGGER.debug("Abwesenheit %s - %s zu kurz, keine Abrechnung", start, end)
                await self._save()
                return
            p = Pending(id=start.strftime("%Y%m%d%H%M"), start=start, end=end)
            await self._advance(p)

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
        hours = (p.end - p.start).total_seconds() / 3600
        header = f"Unterwegs {p.start:%d.%m. %H:%M} - {p.end:%d.%m. %H:%M} ({hours:.1f} Std.)"
        if step == "name":
            return "Reisekosten: Reise", f"{header}\nWohin ging die Reise? (z. B. Kunde Musterstadt)", True
        if step == "purpose":
            return "Reisekosten: Zweck", "Zweck der Reise? (z. B. Präsenzunterricht)", True
        if step == "km":
            return "Reisekosten: Kilometer", "Gefahrene Kilometer mit dem Pkw (gesamt)? - für keine", True
        if step == "overnight":
            return "Reisekosten: Übernachtung", "Gab es eine Übernachtung auswärts?", False
        return ("Reisekosten: Mahlzeiten",
                "Gestellte Mahlzeiten? Beispiel: 08.01 FA, 09.01 M (F=Frühstück, M=Mittag, A=Abend). - für keine",
                True)

    async def _ask(self, p: Pending, step: str, error: str | None = None) -> None:
        title, message, text_input = self._question(p, step)
        if error:
            message = f"{error}\n{message}"
        if text_input:
            actions = [{"action": f"{ACTION_PREFIX}{p.id}|{step}|reply", "title": "Antworten",
                        "behavior": "textInput", "textInputButtonTitle": "Senden"}]
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

    # ------------------------------------------------------------------ Abrechnung
    async def async_add_trip(self, p: Pending) -> None:
        """Manuell angelegte Reise (Service reisekosten.add_trip) ohne Rückfragen."""
        async with self._lock:
            await self._advance(p)

    def _output(self) -> tuple[Path, str | None]:
        """Zielordner und (nur unterhalb von <config>/www) die URL, unter der er erreichbar ist."""
        custom = str(self.entry.options.get(OPT_OUTPUT_DIR) or "").strip()
        folder = Path(self.hass.config.path(*OUTPUT_SUBDIR))
        if custom:
            folder = Path(self.hass.config.path(custom))      # absolute Pfade bleiben absolut
        www = Path(self.hass.config.path("www"))
        try:
            rel = folder.resolve().relative_to(www.resolve())
        except ValueError:
            return folder, None
        return folder, "/local/" + "/".join(rel.parts) if rel.parts else "/local"

    async def _upload_onedrive(self, path: Path) -> str | None:
        """Lädt die PDF in den App-Ordner der HA-OneDrive-Integration. None = ok, sonst Fehlertext."""
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
            data = await self.hass.async_add_executor_job(path.read_bytes)
            url = (f"https://graph.microsoft.com/v1.0/me/drive/special/approot:/"
                   f"{ONEDRIVE_FOLDER}/{path.name}:/content")
            resp = await async_get_clientsession(self.hass).put(
                url, data=data, headers={"Authorization": f"Bearer {session.token['access_token']}",
                                         "Content-Type": "application/pdf"})
            if resp.status not in (200, 201):
                return f"OneDrive antwortete mit Status {resp.status}."
            return None
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("OneDrive-Upload fehlgeschlagen: %s", err)
            return f"OneDrive-Upload fehlgeschlagen ({err})."

    async def _complete(self, p: Pending) -> None:
        self.data["counter"] += 1
        number = f"{p.end.year}{self.data['counter']:03d}"
        statement = build_statement(to_trip(p), self._meta(p, number), self.rules(p.end.year))
        filename = f"Reisekostenabrechnung_{number}_{p.start:%Y-%m-%d}.pdf"
        folder, base_url = self._output()
        path = folder / filename
        try:
            await self.hass.async_add_executor_job(_render, statement, path)
        except Exception:  # noqa: BLE001
            self.data["counter"] -= 1
            _LOGGER.exception("PDF konnte nicht erzeugt werden")
            await self._notify("Reisekosten: Fehler",
                               f"Die PDF konnte nicht nach {folder} geschrieben werden. "
                               "Details stehen im HA-Log.")
            return
        self.data["pending"].pop(p.id, None)
        self.data["trips"].append({
            "number": number, "file": filename, "start": p.start.isoformat(),
            "end": p.end.isoformat(), "name": p.name, "purpose": p.purpose,
            "total": str(statement.total),
        })
        await self._save()
        total = fmt_money(Decimal(statement.total))
        extra = ""
        if self.entry.options.get(OPT_UPLOAD_ONEDRIVE):
            err = await self._upload_onedrive(path)
            extra = (f"\nOneDrive: Apps/…/{ONEDRIVE_FOLDER}" if err is None else f"\n{err}")
        if base_url:
            url = f"{base_url}/{filename}"
            await self._notify(f"Reisekostenabrechnung {number}",
                               f"{p.name}: {total}. Zum Öffnen tippen.{extra}",
                               {"tag": f"rk_{p.id}", "url": url, "clickAction": url})
        else:   # Ordner außerhalb von www: kein Link möglich
            await self._notify(f"Reisekostenabrechnung {number}",
                               f"{p.name}: {total}. Gespeichert unter {path}{extra}",
                               {"tag": f"rk_{p.id}"})
        _LOGGER.info("Reisekostenabrechnung %s erstellt: %s", number, path)
