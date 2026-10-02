import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, "custom_components/reisekosten")
from core.engine import Meta, Trip, build_statement
from core.pdf import render_pdf
from core.rules import rules_for

tz = ZoneInfo("Europe/Berlin")
trip = Trip(datetime(2026, 1, 7, 7, 55, tzinfo=tz), datetime(2026, 1, 17, 13, 42, tzinfo=tz), overnight=True)
meta = Meta(company="Musterfirma GmbH", person="Max Mustermann", street="Musterstraße 1", city="12345 Musterstadt",
            trip_name="Kunde Musterstadt, Schulung",
            purpose="Präsenzveranstaltung, Präsenzunterricht",
            route="Musterstraße 1, 12345 Musterstadt - Musterstadt, Beispielburg",
            number="1000001", user="MaxMustermann", status="eingereicht",
            note="MaxMustermann, 05.03.2026 12:44: Abrechnung eingereicht")
st = build_statement(trip, meta, rules_for(2026))
out = render_pdf(st, "/mnt/user-data/outputs/Beispiel_Reisekostenabrechnung_HA.pdf")
print(out, st.total)
