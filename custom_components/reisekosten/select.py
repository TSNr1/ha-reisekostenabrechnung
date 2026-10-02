"""Auswahl der Abrechnung, die korrigiert werden soll."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import DOMAIN
from .entity import ReisekostenEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([TripSelect(hass.data[DOMAIN][entry.entry_id], entry, "trip")])


class TripSelect(SelectEntity, ReisekostenEntity):
    _attr_icon = "mdi:file-document-edit"

    @property
    def options(self) -> list[str]:
        return self._manager.ui_numbers()

    @property
    def current_option(self) -> str | None:
        return self._manager.ui["selected"]

    async def async_select_option(self, option: str) -> None:
        self._manager.ui_select(option)
