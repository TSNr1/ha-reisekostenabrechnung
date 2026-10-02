"""Eingabefelder für die Korrektur und für die Antwort auf offene Fragen."""
from __future__ import annotations

from homeassistant.components.text import TextEntity

from .const import DOMAIN
from .entity import ReisekostenEntity

FIELDS = {"name": "mdi:map-marker", "purpose": "mdi:text-short", "meals": "mdi:silverware-fork-knife"}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    m = hass.data[DOMAIN][entry.entry_id]
    entities = [TripField(m, entry, key, icon) for key, icon in FIELDS.items()]
    entities.append(AnswerField(m, entry, "answer"))
    async_add_entities(entities)


class TripField(TextEntity, ReisekostenEntity):
    _attr_native_max = 255

    def __init__(self, manager, entry, key: str, icon: str) -> None:
        super().__init__(manager, entry, f"field_{key}")
        self._field = key
        self._attr_icon = icon

    @property
    def native_value(self) -> str:
        return self._manager.ui[self._field] or ""

    async def async_set_value(self, value: str) -> None:
        self._manager.ui_set(self._field, value)


class AnswerField(TextEntity, ReisekostenEntity):
    """Antwort auf die offene Frage; bleibt nach dem Senden leer."""
    _attr_native_max = 255
    _attr_icon = "mdi:message-reply-text"

    @property
    def native_value(self) -> str:
        return ""

    async def async_set_value(self, value: str) -> None:
        await self._manager.async_answer_open(value)
