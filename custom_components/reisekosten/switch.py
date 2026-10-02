"""Schalter Übernachtung für die Korrektur."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .entity import ReisekostenEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([OvernightSwitch(hass.data[DOMAIN][entry.entry_id], entry, "field_overnight")])


class OvernightSwitch(SwitchEntity, ReisekostenEntity):
    _attr_icon = "mdi:bed"

    @property
    def is_on(self) -> bool:
        return bool(self._manager.ui["overnight"])

    async def async_turn_on(self, **kwargs) -> None:
        self._manager.ui_set("overnight", True)

    async def async_turn_off(self, **kwargs) -> None:
        self._manager.ui_set("overnight", False)
