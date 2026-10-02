"""Gemeinsame Basis der Dashboard-Entitäten (Korrekturfelder)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity

from .manager import ReisekostenManager
from .sensor import device_info


class ReisekostenEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: ReisekostenManager, entry: ConfigEntry, key: str) -> None:
        self._manager = manager
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._manager.add_listener(self.async_write_ha_state))
