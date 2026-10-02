import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "reisekosten"))

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


if __name__ == "__main__":
    unittest.main()
