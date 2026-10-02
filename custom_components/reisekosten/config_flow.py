"""Einrichtung und Optionen (rechtliche Vorgaben) der Reisekosten-Integration."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ACC_CONTRA, ACC_KM, ACC_PAYMENT, ACC_PER_DIEM, CONF_CALENDARS, CONF_CITY, CONF_COMPANY,
    CHART_OPTIONS, CONF_CHART, CONF_EMPLOYMENT, CONF_ODOMETER, CONF_WORK_ZONE, EMPLOYMENT_OPTIONS,
    CONF_NAME, CONF_NOTIFY, CONF_PERSON, CONF_STREET, CONF_ZONE, DEFAULT_ZONE, DOMAIN,
    OPT_ACCOUNTS, OPT_CALENDAR_REQUIRED, OPT_OUTPUT_DIR, OPT_RULES, OPT_UPLOAD_ONEDRIVE,
)
from .core.rules import MIDNIGHT_RULES, Rules, diff_overrides, rules_for

MONEY_FIELDS = ("p8", "p24", "arrival_departure", "cut_breakfast", "cut_lunch", "cut_dinner",
                "km_car", "km_motorcycle", "km_scooter", "lodging_flat", "min_hours")


def _notify_services(hass) -> list[str]:
    services = hass.services.async_services_for_domain("notify")
    return sorted(name for name in services if name.startswith("mobile_app_"))


def _storage_locations(hass) -> list[str]:
    """Bekannte Speicherorte: Standard, Medienordner, /share, erlaubte Ordner und deren Unterordner."""
    import os

    roots = [hass.config.path("reisekosten")]
    bases = [*getattr(hass.config, "media_dirs", {}).values(), "/share",
             *getattr(hass.config, "allowlist_external_dirs", [])]
    for base in dict.fromkeys(str(b) for b in bases):
        if not os.path.isdir(base):
            continue
        roots.append(base)
        try:
            roots += sorted(e.path for e in os.scandir(base) if e.is_dir() and not e.name.startswith("."))
        except OSError:
            pass
    return list(dict.fromkeys(roots))


def _number(step: float = 0.01) -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=0, max=1000, step=step, mode=selector.NumberSelectorMode.BOX))


class ReisekostenConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Reisekosten", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_general_schema(self.hass, {}, setup=True))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ReisekostenOptionsFlow()


def _general_schema(hass, cur: dict[str, Any], setup: bool = False) -> vol.Schema:
    """Grunddaten: Person, Zone, Handy, Name/Firma/Adresse, Kalender (+ Speicherort in den Optionen)."""
    notify = _notify_services(hass)
    if cur.get(CONF_NOTIFY) and cur[CONF_NOTIFY] not in notify:
        notify.append(cur[CONF_NOTIFY])
    fields: dict[Any, Any] = {
        vol.Required(CONF_PERSON, **_d(cur, CONF_PERSON)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="person")),
        vol.Required(CONF_ZONE, default=cur.get(CONF_ZONE, DEFAULT_ZONE)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="zone")),
        vol.Required(CONF_EMPLOYMENT, default=cur.get(CONF_EMPLOYMENT, "self_employed")):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=list(EMPLOYMENT_OPTIONS), translation_key="employment",
                mode=selector.SelectSelectorMode.DROPDOWN)),
        vol.Optional(CONF_WORK_ZONE, description={"suggested_value": cur.get(CONF_WORK_ZONE)}):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="zone")),
        vol.Required(CONF_CHART, default=cur.get(CONF_CHART) or ("custom" if cur.get(OPT_ACCOUNTS) else "skr04")):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=list(CHART_OPTIONS), translation_key="chart",
                mode=selector.SelectSelectorMode.DROPDOWN)),
        vol.Optional(CONF_ODOMETER, description={"suggested_value": cur.get(CONF_ODOMETER)}):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Required(CONF_NOTIFY, **_d(cur, CONF_NOTIFY)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=notify, custom_value=True,
                                          mode=selector.SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_NAME, **_d(cur, CONF_NAME)): selector.TextSelector(),
        vol.Optional(CONF_COMPANY, default=cur.get(CONF_COMPANY, "")): selector.TextSelector(),
        vol.Optional(CONF_STREET, default=cur.get(CONF_STREET, "")): selector.TextSelector(),
        vol.Optional(CONF_CITY, default=cur.get(CONF_CITY, "")): selector.TextSelector(),
        vol.Optional(CONF_CALENDARS, default=cur.get(CONF_CALENDARS, [])): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="calendar", multiple=True)),
    }
    return vol.Schema(fields)


def _d(cur: dict[str, Any], key: str) -> dict[str, Any]:
    """default=... nur setzen, wenn es schon einen Wert gibt."""
    return {"default": cur[key]} if cur.get(key) not in (None, "") else {}


class ReisekostenOptionsFlow(OptionsFlow):
    """Menü: Grunddaten (Person, Handy, Kalender, Speicherort) und rechtliche Vorgaben."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["general", "rules"])

    @property
    def _cur(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_general(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        cur = self._cur
        default_dir = self.hass.config.path("reisekosten")
        if user_input is not None:
            out = dict(self.config_entry.options)
            out.update(user_input)
            chosen = (user_input.get(OPT_OUTPUT_DIR) or "").strip()
            out[OPT_OUTPUT_DIR] = "" if chosen == default_dir else chosen
            for key in (CONF_WORK_ZONE, CONF_ODOMETER):          # leeres Feld = Wert entfernen
                out[key] = user_input.get(key) or None
            out[OPT_UPLOAD_ONEDRIVE] = bool(user_input.get(OPT_UPLOAD_ONEDRIVE, False))
            out[OPT_CALENDAR_REQUIRED] = bool(user_input.get(OPT_CALENDAR_REQUIRED, False))
            return self.async_create_entry(data=out)

        fields = dict(_general_schema(self.hass, cur).schema)
        locations = await self.hass.async_add_executor_job(_storage_locations, self.hass)
        chosen = cur.get(OPT_OUTPUT_DIR) or default_dir
        if chosen not in locations:
            locations.append(chosen)
        fields[vol.Optional(OPT_OUTPUT_DIR, default=chosen)] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=locations, custom_value=True,
                                          mode=selector.SelectSelectorMode.DROPDOWN))
        fields[vol.Optional(OPT_CALENDAR_REQUIRED, default=bool(cur.get(OPT_CALENDAR_REQUIRED, False)))] = \
            selector.BooleanSelector()
        fields[vol.Optional(OPT_UPLOAD_ONEDRIVE, default=bool(cur.get(OPT_UPLOAD_ONEDRIVE, False)))] = \
            selector.BooleanSelector()
        return self.async_show_form(step_id="general", data_schema=vol.Schema(fields))

    async def async_step_rules(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = self.config_entry.options
        rules = rules_for(2026, current.get(OPT_RULES) or None).to_dict()
        acc = current.get(OPT_ACCOUNTS) or {}

        if user_input is not None:
            new_rules = {}
            for key in rules:
                value = user_input[key]
                new_rules[key] = str(Decimal(str(value))) if key in MONEY_FIELDS else value
            Rules.from_dict(new_rules)                      # validiert
            out = dict(current)
            out[OPT_RULES] = diff_overrides(new_rules)      # nur eigene Abweichungen speichern
            out[OPT_ACCOUNTS] = {
                ACC_PER_DIEM: user_input[ACC_PER_DIEM], ACC_KM: user_input[ACC_KM],
                ACC_CONTRA: user_input[ACC_CONTRA], ACC_PAYMENT: user_input[ACC_PAYMENT],
            }
            return self.async_create_entry(data=out)

        fields: dict[Any, Any] = {}
        for key, value in rules.items():
            if key in MONEY_FIELDS:
                fields[vol.Required(key, default=float(value))] = _number(0.01)
            elif key in ("strictly_more_than", "km_enabled"):
                fields[vol.Required(key, default=bool(value))] = selector.BooleanSelector()
            elif key == "midnight_rule":
                fields[vol.Required(key, default=value)] = selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(MIDNIGHT_RULES), translation_key="midnight_rule"))
            else:
                fields[vol.Required(key, default=value)] = selector.TextSelector()
        fields[vol.Optional(ACC_PER_DIEM, default=acc.get(ACC_PER_DIEM, "4664"))] = selector.TextSelector()
        fields[vol.Optional(ACC_KM, default=acc.get(ACC_KM, ""))] = selector.TextSelector()
        fields[vol.Optional(ACC_CONTRA, default=acc.get(ACC_CONTRA, ""))] = selector.TextSelector()
        fields[vol.Optional(ACC_PAYMENT, default=acc.get(ACC_PAYMENT, "Bar"))] = selector.TextSelector()
        return self.async_show_form(step_id="rules", data_schema=vol.Schema(fields))
