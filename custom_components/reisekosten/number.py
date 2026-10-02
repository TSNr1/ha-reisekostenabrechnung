"""Kilometer-Feld für die Korrektur."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode

from .const import DOMAIN
from .entity import ReisekostenEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([KmNumber(hass.data[DOMAIN][entry.entry_id], entry, "field_km")])


class KmNumber(NumberEntity, ReisekostenEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 5000
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "km"
    _attr_icon = "mdi:car"

    @property
    def native_value(self) -> float:
        return float(self._manager.ui["km"] or 0)

    async def async_set_native_value(self, value: float) -> None:
        self._manager.ui_set("km", value)
