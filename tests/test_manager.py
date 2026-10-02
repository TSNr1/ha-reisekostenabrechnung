"""Ablauf-Test des Managers gegen eine Nachbildung von Home Assistant (kein echtes HA nötig)."""
import asyncio
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BERLIN = ZoneInfo("Europe/Berlin")


def _install_stub():
    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    class State:
        def __init__(self, entity_id, state, last_changed, name=None):
            self.entity_id, self.state, self.last_changed = entity_id, state, last_changed
            self.name = name or entity_id

    class Event:
        def __init__(self, data):
            self.data = data

        def __class_getitem__(cls, item):
            return cls

    class Store:
        saved = None

        def __init__(self, hass, version, key):
            pass

        async def async_load(self):
            return None

        async def async_save(self, data):
            import copy
            Store.saved = copy.deepcopy(data)

    timers = []

    def async_call_later(hass, delay, action):
        timers.append((delay, action))
        return lambda: timers.remove((delay, action)) if (delay, action) in timers else None

    def async_track_state_change_event(hass, ids, cb):
        hass.person_cb = cb
        return lambda: None

    def as_local(d):
        return d.astimezone(BERLIN) if d.tzinfo else d.replace(tzinfo=BERLIN)

    dt_mod = mod("homeassistant.util.dt", as_local=as_local,
                 as_utc=lambda d: d.astimezone(timezone.utc),
                 parse_datetime=datetime.fromisoformat,
                 now=lambda: datetime(2026, 3, 2, 19, 0, tzinfo=BERLIN))
    mod("homeassistant")
    mod("homeassistant.util", dt=dt_mod)
    mod("homeassistant.config_entries", ConfigEntry=object)
    mod("homeassistant.core", Event=Event, EventStateChangedData=dict, HomeAssistant=object,
        State=State, ServiceCall=object, SupportsResponse=types.SimpleNamespace(ONLY='only'), callback=lambda f: f)
    mod("homeassistant.helpers")
    mod("homeassistant.helpers.event", async_call_later=async_call_later,
        async_track_state_change_event=async_track_state_change_event)
    mod("homeassistant.helpers.storage", Store=Store)
    try:
        import voluptuous  # noqa: F401
    except ImportError:
        mod("voluptuous", Schema=lambda x: x, Required=lambda k, **kw: k, Optional=lambda k, **kw: k,
            Coerce=lambda t: t, In=lambda x: x, Invalid=ValueError)
    cv = mod("homeassistant.helpers.config_validation", datetime=lambda v: v, string=str, boolean=bool)
    sys.modules["homeassistant.helpers"].config_validation = cv
    return State, Event, Store, timers


State, Event, Store, TIMERS = _install_stub()
sys.path.insert(0, str(ROOT))
from custom_components.reisekosten import manager as mgr  # noqa: E402


class FakeHass:
    def __init__(self, tmp):
        self.tmp = tmp
        self.states = types.SimpleNamespace(get=self._get)
        self._states = {}
        self.calls = []
        self.person_cb = None
        self.calendar_response = {}
        self.bus = types.SimpleNamespace(async_listen=lambda *_: (lambda: None))
        self.config = types.SimpleNamespace(path=lambda *p: str(Path(tmp, *p)))
        self.services = types.SimpleNamespace(async_call=self._call)

    def _get(self, entity_id):
        return self._states.get(entity_id)

    async def _call(self, domain, service, data, blocking=False, return_response=False):
        self.calls.append((domain, service, data))
        if (domain, service) == ("calendar", "get_events"):
            return self.calendar_response

    async def async_add_executor_job(self, fn, *args):
        return fn(*args)

    def async_create_task(self, coro):
        return asyncio.ensure_future(coro)


class Entry:
    data = {"person": "person.max", "zone": "zone.home", "notify_service": "mobile_app_s25",
            "person_name": "Max Mustermann", "company": "Musterfirma GmbH", "street": "Musterstraße 1",
            "city": "12345 Musterstadt"}
    options = {}


def utc(d, h, mi=0, mo=3):
    return datetime(2026, mo, d, h, mi, tzinfo=BERLIN).astimezone(timezone.utc)


class ManagerFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hass = FakeHass(self.tmp)
        self.hass._states["person.max"] = State("person.max", "home", utc(1, 0), "Max")
        self.m = mgr.ReisekostenManager(self.hass, Entry())
        await self.m.async_start()
        TIMERS.clear()

    def person(self, state, when):
        st = State("person.max", state, when, "Max")
        self.hass._states["person.max"] = st
        self.m._on_person(Event({"new_state": st}))

    def last_notify(self):
        return [c for c in self.hass.calls if c[0] == "notify"][-1][2]

    async def answer(self, step, text):
        pid = next(iter(self.m.data["pending"]))
        return await self.m.async_answer(pid, step, text)

    async def test_full_trip(self):
        self.person("not_home", utc(2, 7, 0))
        self.assertEqual(self.m.data["away_since"], utc(2, 7, 0).isoformat())
        self.person("home", utc(2, 18, 30))
        self.assertEqual(len(TIMERS), 1)               # Ankunft wird entprellt
        await TIMERS[0][1](None)
        self.assertEqual(self.m.data["away_since"], None)

        note = self.last_notify()
        self.assertIn("Wohin ging die Reise", note["message"])
        self.assertEqual(note["data"]["actions"][0]["behavior"], "textInput")

        self.assertTrue(await self.answer("name", "Kunde Musterstadt"))
        self.assertTrue(await self.answer("purpose", "Präsenzunterricht"))
        self.assertFalse(await self.answer("km", "viel"))            # Fehler: neu fragen
        self.assertIn("Zahl", self.last_notify()["message"])
        self.assertTrue(await self.answer("km", "123,5"))
        self.assertFalse(await self.answer("name", "zu spät"))       # veraltete Antwort
        self.assertTrue(await self.answer("meals", "-"))

        self.assertEqual(self.m.data["pending"], {})
        trip = self.m.data["trips"][0]
        self.assertEqual(trip["total"], str(14 + 37.05))
        pdf = Path(self.tmp, "www", "reisekosten", trip["file"])
        self.assertTrue(pdf.exists() and pdf.stat().st_size > 1000)
        done = self.last_notify()
        self.assertIn("51,05 EUR", done["message"])
        self.assertEqual(done["data"]["url"], f"/local/reisekosten/{trip['file']}")

    async def test_custom_folder_inside_www_keeps_link(self):
        self.m.entry = types.SimpleNamespace(data=Entry.data, options={"output_dir": "www/abrechnungen/2026"})
        folder, url = self.m._output()
        self.assertEqual(folder, Path(self.tmp, "www", "abrechnungen", "2026"))
        self.assertEqual(url, "/local/abrechnungen/2026")

    async def test_custom_folder_outside_www_has_no_link(self):
        target = tempfile.mkdtemp()
        self.m.entry = types.SimpleNamespace(data=Entry.data, options={"output_dir": target})
        self.assertEqual(self.m._output(), (Path(target), None))
        self.person("not_home", utc(2, 7, 0))
        self.person("home", utc(2, 18, 30))
        await TIMERS[0][1](None)
        for step, text in (("name", "A"), ("purpose", "B"), ("km", "-"), ("meals", "-")):
            await self.answer(step, text)
        trip = self.m.data["trips"][0]
        self.assertTrue(Path(target, trip["file"]).exists())
        note = self.last_notify()
        self.assertIn(target, note["message"])
        self.assertNotIn("url", note["data"])

    async def test_onedrive_failure_is_reported_but_pdf_is_kept(self):
        self.m.entry = types.SimpleNamespace(data=Entry.data, options={"upload_onedrive": True})
        self.person("not_home", utc(2, 7, 0))
        self.person("home", utc(2, 18, 30))
        await TIMERS[0][1](None)
        for step, text in (("name", "A"), ("purpose", "B"), ("km", "-"), ("meals", "-")):
            await self.answer(step, text)
        trip = self.m.data["trips"][0]
        self.assertTrue(Path(self.tmp, "www", "reisekosten", trip["file"]).exists())
        self.assertIn("OneDrive", self.last_notify()["message"])

    async def test_calendar_suggestion_can_be_accepted(self):
        self.m.entry = types.SimpleNamespace(data=Entry.data, options={"calendars": ["calendar.work"]})
        self.hass.calendar_response = {"calendar.work": {"events": [
            {"start": "2026-03-02T08:00:00+01:00", "end": "2026-03-02T16:00:00+01:00",
             "summary": "Schulung ABC", "location": "Musterstadt"},
            {"start": "2026-03-02T09:00:00+01:00", "end": "2026-03-02T09:30:00+01:00", "summary": "Telefonat"}]}}
        self.person("not_home", utc(2, 7, 0))
        self.person("home", utc(2, 18, 30))
        await TIMERS[0][1](None)
        note = self.last_notify()
        self.assertIn("Vorschlag aus dem Kalender: Musterstadt", note["message"])
        pid = next(iter(self.m.data["pending"]))
        self.assertEqual(note["data"]["actions"][1]["action"], f"RK_{pid}|name|accept")
        await self.m._on_action(Event({"action": f"RK_{pid}|name|accept"}))
        self.assertIn("Vorschlag aus dem Kalender: Schulung ABC", self.last_notify()["message"])
        await self.m._on_action(Event({"action": f"RK_{pid}|purpose|accept"}))
        self.assertEqual(self.m.data["pending"][pid]["name"], "Musterstadt")
        self.assertEqual(self.m.data["pending"][pid]["purpose"], "Schulung ABC")

    async def test_calendar_failure_is_harmless(self):
        self.m.entry = types.SimpleNamespace(data=Entry.data, options={"calendars": ["calendar.work"]})
        async def broken(domain, service, data, blocking=False, return_response=False):
            if domain == "calendar":
                raise RuntimeError("Kalender weg")
            self.hass.calls.append((domain, service, data))
        self.hass.services.async_call = broken
        self.person("not_home", utc(2, 7, 0))
        self.person("home", utc(2, 18, 30))
        await TIMERS[0][1](None)
        self.assertIn("Wohin ging die Reise", self.last_notify()["message"])

    async def go(self, a, b, d=2):
        self.person("not_home", utc(d, *a))
        self.person("home", utc(d, *b))
        await TIMERS[-1][1](None)
        TIMERS.clear()

    async def finish(self, km="-"):
        for step, text in (("name", "A"), ("purpose", "B"), ("km", km), ("meals", "-")):
            await self.answer(step, text)

    def notes(self):
        return [c for c in self.hass.calls if c[0] == "notify"]

    async def test_discard_button(self):
        await self.go((7, 0), (18, 30))
        note = self.last_notify()
        pid = next(iter(self.m.data["pending"]))
        self.assertEqual(note["data"]["actions"][-1]["action"], f"RK_{pid}|name|discard")
        await self.m._on_action(Event({"action": f"RK_{pid}|name|discard"}))
        self.assertEqual(self.m.data["pending"], {})
        self.assertIn("verworfen", self.last_notify()["message"])
        self.assertEqual(self.m.data["trips"], [])

    async def test_calendar_required_skips_trips_without_event(self):
        self.m.entry = types.SimpleNamespace(
            data=Entry.data, options={"calendars": ["calendar.work"], "calendar_required": True})
        await self.go((7, 0), (18, 30))
        self.assertEqual(self.notes(), [])
        self.assertEqual(self.m.data["pending"], {})
        self.hass.calendar_response = {"calendar.work": {"events": [
            {"start": "2026-03-03T08:00:00+01:00", "end": "2026-03-03T16:00:00+01:00", "summary": "Kunde"}]}}
        await self.go((7, 0), (18, 30), d=3)
        self.assertIn("Wohin ging die Reise", self.last_notify()["message"])

    async def test_two_absences_on_one_day_are_added_up(self):
        await self.go((7, 0), (11, 0))                    # 4 Std. allein: keine Pauschale
        self.assertEqual(self.notes(), [])
        await self.go((14, 0), (19, 0))                   # zusammen 9 Std.
        self.assertIn("zusammengerechnet: 9.0 Std.", self.last_notify()["message"])
        pid = next(iter(self.m.data["pending"]))
        self.assertTrue(pid.endswith("0700"))
        await self.finish()
        trip = self.m.data["trips"][0]
        self.assertEqual(float(trip["total"]), 14.0)
        await self.go((20, 0), (21, 30))                  # später am Tag: schon abgerechnet
        self.assertEqual(len(self.m.data["trips"]), 1)
        self.assertEqual(self.m.data["pending"], {})

    async def test_second_absence_extends_open_trip(self):
        await self.go((7, 0), (16, 30))                   # 9,5 Std., Fragen offen
        pid = next(iter(self.m.data["pending"]))
        await self.go((18, 0), (19, 0))
        self.assertEqual(list(self.m.data["pending"]), [pid])
        self.assertEqual(self.m.data["pending"][pid]["away_minutes"], 10 * 60 + 30)

    async def test_delete_trip_frees_number_and_file(self):
        await self.go((7, 0), (18, 30))
        await self.finish("10")
        first = self.m.data["trips"][0]
        await self.go((7, 0), (18, 30), d=3)
        await self.finish("10")
        self.assertEqual(self.m.data["counter"], 2)
        await self.m.async_delete_trip(first["number"])               # mittendrin: Zähler bleibt
        self.assertEqual(self.m.data["counter"], 2)
        self.assertFalse(Path(first["path"]).exists())
        await self.m.async_delete_trip(self.m.data["trips"][0]["number"])
        self.assertEqual((self.m.data["counter"], self.m.data["trips"]), (0, []))
        with self.assertRaises(ValueError):
            await self.m.async_delete_trip("2026999")

    async def test_regenerate_with_corrections(self):
        await self.go((7, 0), (18, 30))
        await self.finish("100")
        trip = self.m.data["trips"][0]
        self.assertEqual(float(trip["total"]), 44.0)
        await self.m.async_regenerate(trip["number"], {"km_car": 0, "purpose": "Neu"})
        trip = self.m.data["trips"][0]
        self.assertEqual((float(trip["total"]), trip["purpose"], len(self.m.data["trips"])), (14.0, "Neu", 1))
        self.assertTrue(Path(trip["path"]).exists())
        self.assertIn("Neu erzeugt", self.last_notify()["title"])
        trip.pop("data")
        with self.assertRaises(ValueError):
            await self.m.async_regenerate(trip["number"], {})

    async def test_dashboard_correction_fields(self):
        await self.go((7, 0), (18, 30))
        await self.finish("100")
        number = self.m.data["trips"][0]["number"]
        self.assertEqual((self.m.ui["selected"], self.m.ui["name"], self.m.ui["purpose"], self.m.ui["km"]),
                         (number, "A", "B", 100.0))
        self.m.ui_set("km", 0.0)
        self.m.ui_set("purpose", "Neu")
        await self.m.async_apply_ui()
        trip = self.m.data["trips"][0]
        self.assertEqual((float(trip["total"]), trip["purpose"]), (14.0, "Neu"))
        await self.m.async_delete_selected()
        self.assertEqual((self.m.data["trips"], self.m.ui["selected"]), ([], None))
        with self.assertRaises(ValueError):
            await self.m.async_apply_ui()

    async def test_dashboard_answer_and_resend(self):
        await self.go((7, 0), (18, 30))
        self.assertFalse(await self.m.async_answer_open("  "))
        before = len(self.notes())
        await self.m.async_resend()
        self.assertEqual(len(self.notes()), before + 1)
        self.assertTrue(await self.m.async_answer_open("Bensheim"))
        raw = next(iter(self.m.data["pending"].values()))
        self.assertEqual(raw["name"], "Bensheim")
        await self.m.async_discard_open()
        self.assertEqual(self.m.data["pending"], {})

    async def test_summary_for_dashboard_entities(self):
        calls = []
        remove = self.m.add_listener(lambda: calls.append(1))
        s = self.m.summary()
        self.assertEqual((float(s["month_total"]), s["last"], s["open"], s["away_since"]), (0.0, None, [], None))
        self.person("not_home", utc(2, 7, 0))
        self.assertTrue(self.m.summary()["away_since"])
        self.person("home", utc(2, 18, 30))
        await TIMERS[-1][1](None)
        s = self.m.summary()
        self.assertEqual([o["waiting_for"] for o in s["open"]], ["name"])
        self.assertTrue(calls)
        await self.finish("10")
        s = self.m.summary()
        self.assertEqual((float(s["month_total"]), float(s["year_total"]), s["year_count"], s["open"]),
                         (17.0, 17.0, 1, []))
        self.assertEqual(s["last"]["number"], "2026001")
        self.assertTrue(self.m.trip_link(s["last"]).startswith("/local/reisekosten/"))
        remove()
        n = len(calls)
        await self.m._save()
        self.assertEqual(len(calls), n)

    async def test_short_trip_is_ignored(self):
        self.person("not_home", utc(2, 8, 0))
        self.person("home", utc(2, 10, 0))
        await TIMERS[0][1](None)
        self.assertEqual(self.m.data["pending"], {})
        self.assertEqual([c for c in self.hass.calls if c[0] == "notify"], [])

    async def test_leaving_again_cancels_arrival(self):
        self.person("not_home", utc(2, 7, 0))
        self.person("home", utc(2, 12, 0))
        self.assertEqual(len(TIMERS), 1)
        self.person("not_home", utc(2, 12, 1))                       # Tür nur kurz geöffnet
        self.assertEqual(len(TIMERS), 0)
        self.assertEqual(self.m.data["away_since"], utc(2, 7, 0).isoformat())

    async def test_unknown_state_is_ignored(self):
        self.person("unavailable", utc(2, 7, 0))
        self.assertIsNone(self.m.data["away_since"])

    async def test_multi_day_trip_with_overnight_answers(self):
        self.person("not_home", utc(7, 7, 55, mo=1))
        self.person("home", utc(17, 13, 42, mo=1))
        await TIMERS[0][1](None)
        for step, text in (("name", "Kunde Musterstadt"), ("purpose", "Schulung"), ("km", "-"), ("meals", "-")):
            self.assertTrue(await self.answer(step, text), step)
        self.assertEqual(self.m.data["trips"][0]["total"], "280.00")

    async def test_notify_failure_falls_back_to_persistent_notification(self):
        async def broken(domain, service, data, blocking=False, return_response=False):
            if domain == "notify":
                raise RuntimeError("kein Handy")
            self.hass.calls.append((domain, service, data))
        self.hass.services.async_call = broken
        self.person("not_home", utc(2, 7, 0))
        self.person("home", utc(2, 18, 0))
        await TIMERS[0][1](None)
        self.assertEqual(self.hass.calls[-1][:2], ("persistent_notification", "create"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
