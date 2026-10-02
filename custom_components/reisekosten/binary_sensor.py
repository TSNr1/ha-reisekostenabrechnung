"""Binärsensor „Unterwegs“: ist die Person gerade außerhalb der Zone?"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .manager import ReisekostenManager
from .sensor import device_info


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([AwayBinarySensor(hass.data[DOMAIN][entry.entry_id], entry)])


class AwayBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "away"
    _attr_icon = "mdi:car-traffic"

    def __init__(self, manager: ReisekostenManager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_away"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._manager.add_listener(self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        return bool(self._manager.summary()["away_since"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"seit": self._manager.summary()["away_since"]}
