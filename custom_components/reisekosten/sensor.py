"""Sensoren für das Dashboard: Summen, letzte Abrechnung, offene Reisen."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .manager import ReisekostenManager


def device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="Reisekosten",
                      manufacturer="Reisekosten", entry_type=DeviceEntryType.SERVICE)


def _last(s: dict[str, Any]) -> str | None:
    return s["last"]["number"] if s["last"] else None


def _last_attrs(m: ReisekostenManager, s: dict[str, Any]) -> dict[str, Any]:
    t = s["last"]
    if not t:
        return {}
    return {"betrag": float(t["total"]), "reise": t.get("name"), "zweck": t.get("purpose"),
            "von": t["start"], "bis": t["end"], "datei": t.get("file"), "link": m.trip_link(t)}


SENSORS: tuple[tuple[SensorEntityDescription, Callable[[dict], Any], Callable | None], ...] = (
    (SensorEntityDescription(key="last_statement", translation_key="last_statement",
                             icon="mdi:file-document-check"),
     _last, _last_attrs),
    (SensorEntityDescription(key="month_total", translation_key="month_total",
                             device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="EUR",
                             suggested_display_precision=2),
     lambda s: float(s["month_total"]), None),
    (SensorEntityDescription(key="year_total", translation_key="year_total",
                             device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="EUR",
                             suggested_display_precision=2),
     lambda s: float(s["year_total"]), None),
    (SensorEntityDescription(key="year_count", translation_key="year_count", icon="mdi:briefcase-clock"),
     lambda s: s["year_count"], None),
    (SensorEntityDescription(key="open_trips", translation_key="open_trips", icon="mdi:help-circle-outline"),
     lambda s: len(s["open"]), lambda m, s: {"reisen": s["open"]}),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    manager: ReisekostenManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(ReisekostenSensor(manager, entry, d, value, attrs) for d, value, attrs in SENSORS)


class ReisekostenSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: ReisekostenManager, entry: ConfigEntry, description: SensorEntityDescription,
                 value: Callable[[dict], Any], attrs: Callable | None) -> None:
        self.entity_description = description
        self._manager, self._value, self._attrs = manager, value, attrs
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._manager.add_listener(self.async_write_ha_state))
        # Monats- und Jahreswechsel: stündlich neu berechnen
        self.async_on_remove(async_track_time_interval(
            self.hass, self._hourly_refresh, timedelta(hours=1)))

    @callback
    def _hourly_refresh(self, _now: Any) -> None:
        # @callback: läuft im Event-Loop (sonst Warnung „aus fremdem Thread“)
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        return self._value(self._manager.summary())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self._attrs(self._manager, self._manager.summary()) if self._attrs else None
