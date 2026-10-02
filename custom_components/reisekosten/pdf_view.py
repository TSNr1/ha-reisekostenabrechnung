"""Abruf der PDFs über Home Assistant: nur mit Anmeldung oder mit signiertem (befristetem) Link."""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PDF_VIEW_URL


class ReisekostenPdfView(HomeAssistantView):
    url = PDF_VIEW_URL
    name = "api:reisekosten:pdf"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, number: str) -> web.StreamResponse:
        # Es werden nur PDFs ausgeliefert, die in der Liste der Abrechnungen stehen (keine freien Pfade).
        for manager in list(self.hass.data.get(DOMAIN, {}).values()):
            trip = next((t for t in manager.data["trips"] if t["number"] == number), None)
            if trip is None:
                continue
            path = Path(trip.get("path") or manager._output() / trip["file"])
            if await self.hass.async_add_executor_job(path.is_file):
                return web.FileResponse(path, headers={
                    "Content-Type": "application/pdf",
                    "Content-Disposition": f'inline; filename="{path.name}"'})
        raise web.HTTPNotFound()
