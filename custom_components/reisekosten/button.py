"""Knöpfe: neu erzeugen, löschen, offene Reise verwerfen, Frage erneut senden."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .const import DOMAIN
from .entity import ReisekostenEntity

BUTTONS = {
    "apply": ("async_apply_ui", "mdi:file-refresh"),
    "delete": ("async_delete_selected", "mdi:delete"),
    "discard_open": ("async_discard_open", "mdi:close-circle-outline"),
    "resend": ("async_resend", "mdi:send"),
}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    m = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(ReisekostenButton(m, entry, k, *v) for k, v in BUTTONS.items())


class ReisekostenButton(ButtonEntity, ReisekostenEntity):
    def __init__(self, manager, entry, key: str, method: str, icon: str) -> None:
        super().__init__(manager, entry, f"btn_{key}")
        self._method = method
        self._attr_icon = icon

    async def async_press(self) -> None:
        await getattr(self._manager, self._method)()
