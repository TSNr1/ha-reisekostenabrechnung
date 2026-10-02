import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import corepath  # noqa: F401, E402

from core.calendar_match import pick_event  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
START, END = datetime(2026, 3, 2, 7, tzinfo=TZ), datetime(2026, 3, 2, 18, tzinfo=TZ)


class PickEvent(unittest.TestCase):
    def test_largest_overlap_wins_and_location_is_name(self):
        ev = [{"start": "2026-03-02T09:00:00+01:00", "end": "2026-03-02T09:30:00+01:00", "summary": "Call"},
              {"start": "2026-03-02T08:00:00+01:00", "end": "2026-03-02T16:00:00+01:00",
               "summary": "Schulung", "location": "Musterstadt\nStr. 1"}]
        self.assertEqual(pick_event(ev, START, END), {"name": "Musterstadt", "purpose": "Schulung"})

    def test_without_location_summary_is_both(self):
        ev = [{"start": "2026-03-02T08:00:00+01:00", "end": "2026-03-02T16:00:00+01:00", "summary": "Messe"}]
        self.assertEqual(pick_event(ev, START, END), {"name": "Messe", "purpose": "Messe"})

    def test_all_day_event(self):
        ev = [{"start": "2026-03-02", "end": "2026-03-03", "summary": "Seminar"}]
        self.assertEqual(pick_event(ev, START, END)["purpose"], "Seminar")

    def test_no_overlap_or_garbage(self):
        ev = [{"start": "2026-03-03", "end": "2026-03-04", "summary": "Morgen"},
              {"start": "kaputt", "end": "x", "summary": "?"}, {"start": "2026-03-02", "end": "2026-03-03"}]
        self.assertIsNone(pick_event(ev, START, END))
        self.assertIsNone(pick_event([], START, END))

    def test_short_call_is_ignored_when_a_long_event_exists(self):
        ev = [{"start": "2026-03-02T09:00:00+01:00", "end": "2026-03-02T09:30:00+01:00", "summary": "Call"},
              {"start": "2026-03-02T08:00:00+01:00", "end": "2026-03-02T16:00:00+01:00", "summary": "Schulung"}]
        self.assertEqual(pick_event(ev, START, END), {"name": "Schulung", "purpose": "Schulung"})

    def test_only_short_event_is_still_used(self):
        ev = [{"start": "2026-03-02T09:00:00+01:00", "end": "2026-03-02T09:30:00+01:00", "summary": "Call"}]
        self.assertEqual(pick_event(ev, START, END)["purpose"], "Call")

    def test_several_events_are_joined_in_order(self):
        tz = ZoneInfo("Europe/Berlin")
        start, end = datetime(2026, 10, 26, 6, tzinfo=tz), datetime(2026, 11, 9, 21, tzinfo=tz)
        ev = [
            {"start": "2026-11-05", "end": "2026-11-09", "summary": "VPT KGG Fellbach",
             "location": "Hotel Bürkle, Augustenstraße 1, 70736 Fellbach"},
            {"start": "2026-10-27", "end": "2026-11-01", "summary": "Inhouse Reha-Med Sinsheim",
             "location": "Gesundheitszentrum Reha-Med, Neulandstraße 16, 74889 Sinsheim"},
            {"start": "2026-11-01", "end": "2026-11-05", "summary": "VPT KGG Fellbach",
             "location": "Hotel Bürkle, Augustenstraße 1, 70736 Fellbach"},
            {"start": "2026-11-09", "end": "2026-11-10", "summary": "TRENA Fellbach",
             "location": "Hotel Bürkle, Augustenstraße 1, 70736 Fellbach"},
            {"start": "2026-11-12", "end": "2026-11-16", "summary": "Später", "location": "Anderswo"}]
        self.assertEqual(pick_event(ev, start, end), {
            "name": "Sinsheim, Fellbach",
            "purpose": "Inhouse Reha-Med Sinsheim; VPT KGG Fellbach; TRENA Fellbach"})


if __name__ == "__main__":
    unittest.main()
