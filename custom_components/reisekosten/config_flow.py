"""Einrichtung und Optionen (rechtliche Vorgaben) der Reisekosten-Integration."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    ACC_CONTRA, ACC_KM, ACC_PAYMENT, ACC_PER_DIEM, CONF_CITY, CONF_COMPANY, CONF_NAME,
    CONF_NOTIFY, CONF_PERSON, CONF_STREET, CONF_ZONE, DEFAULT_ZONE, DOMAIN, OPT_ACCOUNTS,
    OPT_OUTPUT_DIR, OPT_RULES, OPT_UPLOAD_ONEDRIVE,
)
from .core.rules import MIDNIGHT_RULES, Rules, rules_for

MONEY_FIELDS = ("p8", "p24", "arrival_departure", "cut_breakfast", "cut_lunch", "cut_dinner",
                "km_car", "km_motorcycle", "km_scooter", "lodging_flat", "min_hours")


def _notify_services(hass) -> list[str]:
    services = hass.services.async_services_for_domain("notify")
    return sorted(name for name in services if name.startswith("mobile_app_"))


def _storage_locations(hass) -> list[str]:
    """Bekannte Speicherorte: Standard, Medienordner, /share, erlaubte Ordner und deren Unterordner."""
    import os

    roots = [hass.config.path("www", "reisekosten")]
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

        notify = _notify_services(self.hass)
        schema = vol.Schema({
            vol.Required(CONF_PERSON): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person")),
            vol.Required(CONF_ZONE, default=DEFAULT_ZONE): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="zone")),
            vol.Required(CONF_NOTIFY): selector.SelectSelector(selector.SelectSelectorConfig(
                options=notify, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_NAME): selector.TextSelector(),
            vol.Optional(CONF_COMPANY, default=""): selector.TextSelector(),
            vol.Optional(CONF_STREET, default=""): selector.TextSelector(),
            vol.Optional(CONF_CITY, default=""): selector.TextSelector(),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ReisekostenOptionsFlow()


class ReisekostenOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = self.config_entry.options
        rules = rules_for(2026, current.get(OPT_RULES) or None).to_dict()
        acc = current.get(OPT_ACCOUNTS) or {}
        default_dir = self.hass.config.path("www", "reisekosten")

        if user_input is not None:
            new_rules = {}
            for key in rules:
                value = user_input[key]
                new_rules[key] = str(Decimal(str(value))) if key in MONEY_FIELDS else value
            Rules.from_dict(new_rules)                      # validiert
            return self.async_create_entry(data={
                OPT_RULES: new_rules,
                OPT_OUTPUT_DIR: ("" if (user_input.get(OPT_OUTPUT_DIR) or "").strip() == default_dir
                                 else (user_input.get(OPT_OUTPUT_DIR) or "").strip()),
                OPT_UPLOAD_ONEDRIVE: bool(user_input.get(OPT_UPLOAD_ONEDRIVE, False)),
                OPT_ACCOUNTS: {
                    ACC_PER_DIEM: user_input[ACC_PER_DIEM], ACC_KM: user_input[ACC_KM],
                    ACC_CONTRA: user_input[ACC_CONTRA], ACC_PAYMENT: user_input[ACC_PAYMENT],
                },
            })

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
        locations = await self.hass.async_add_executor_job(_storage_locations, self.hass)
        chosen = current.get(OPT_OUTPUT_DIR) or default_dir
        if chosen not in locations:
            locations.append(chosen)
        fields[vol.Optional(OPT_OUTPUT_DIR, default=chosen)] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=locations, custom_value=True,
                                          mode=selector.SelectSelectorMode.DROPDOWN))
        fields[vol.Optional(OPT_UPLOAD_ONEDRIVE, default=bool(current.get(OPT_UPLOAD_ONEDRIVE, False)))] = \
            selector.BooleanSelector()
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
