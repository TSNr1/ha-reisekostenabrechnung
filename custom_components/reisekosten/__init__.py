"""Reisekosten: automatische Reisekostenabrechnung als PDF."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .core.wizard import Pending, parse_km, parse_meals
from .manager import ReisekostenManager

_LOGGER = logging.getLogger(__name__)

SERVICE_ADD_TRIP = "add_trip"
SERVICE_ANSWER = "answer"

ADD_TRIP_SCHEMA = vol.Schema({
    vol.Required("start"): cv.datetime,
    vol.Required("end"): cv.datetime,
    vol.Optional("name"): cv.string,
    vol.Optional("purpose"): cv.string,
    vol.Optional("overnight"): cv.boolean,
    vol.Optional("km_car"): vol.Coerce(float),
    vol.Optional("meals"): cv.string,
})

ANSWER_SCHEMA = vol.Schema({
    vol.Required("trip_id"): cv.string,
    vol.Required("step"): vol.In(["name", "purpose", "km", "overnight", "meals"]),
    vol.Required("text"): cv.string,
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = ReisekostenManager(hass, entry)
    await manager.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager

    async def add_trip(call: ServiceCall) -> None:
        start = dt_util.as_local(call.data["start"])
        end = dt_util.as_local(call.data["end"])
        if end <= start:
            raise vol.Invalid("Ende muss nach dem Start liegen")
        d = call.data
        # Nicht angegebene Felder bleiben leer und werden per Rückfrage auf dem Handy erfragt.
        p = Pending(
            id=start.strftime("%Y%m%d%H%M"), start=start, end=end,
            name=d.get("name"), purpose=d.get("purpose"),
            km_car=(parse_km(str(d["km_car"])) if "km_car" in d else None)
            if manager.rules(start.year).km_enabled else parse_km("0"),
            overnight=d.get("overnight"),
            meals=parse_meals(d["meals"], start, end) if "meals" in d else None)
        await manager.async_add_trip(p)

    async def answer(call: ServiceCall) -> None:
        await manager.async_answer(call.data["trip_id"], call.data["step"], call.data["text"])

    hass.services.async_register(DOMAIN, SERVICE_ADD_TRIP, add_trip, schema=ADD_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ANSWER, answer, schema=ANSWER_SCHEMA)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager: ReisekostenManager = hass.data[DOMAIN].pop(entry.entry_id)
    manager.async_stop()
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_ADD_TRIP)
        hass.services.async_remove(DOMAIN, SERVICE_ANSWER)
    return True
