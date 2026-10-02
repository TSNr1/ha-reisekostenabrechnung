import sys
import unittest
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "reisekosten"))

from core.engine import Meta, Trip, build_statement, per_diem  # noqa: E402
from core.rules import Rules, rules_for  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
META = Meta(company="Musterfirma GmbH", person="Max Mustermann", street="Musterstraße 1",
            city="12345 Musterstadt")


def dt(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


class SampleFromOnexma(unittest.TestCase):
    """Abrechnung Nr. 1000001: 07.01.2026 07:55 - 17.01.2026 13:42, Ergebnis 280,00 EUR."""

    def setUp(self):
        trip = Trip(dt(2026, 1, 7, 7, 55), dt(2026, 1, 17, 13, 42), overnight=True)
        self.st = build_statement(trip, META, Rules())

    def test_total(self):
        self.assertEqual(self.st.total, D("280.00"))

    def test_days(self):
        self.assertEqual(self.st.calendar_days, 11)

    def test_lines_like_onexma(self):
        l = self.st.lines
        self.assertEqual(len(l), 3)
        self.assertEqual(l[0].text, "Verpflegungspausch. 07.01.2026 Anreisetag (16:04 Std.)")
        self.assertEqual(l[0].sub, "Abreise: 07:55")
        self.assertEqual(l[0].net, D("14"))
        self.assertEqual(l[1].text, "Verpflegungspausch. 9 Tage ab 08.01.2026 x 28 EUR")
        self.assertEqual(l[1].net, D("252"))
        self.assertEqual(l[2].text, "Verpflegungspausch. 17.01.2026 Abreisetag (13:42 Std.)")
        self.assertEqual(l[2].sub, "Rückkehr: 13:42")

    def test_booking(self):
        b = self.st.bookings
        self.assertEqual(len(b), 1)
        self.assertEqual((b[0].label, b[0].account, b[0].net), ("Mahlzeiten-Pauschale DE", "4664", D("280")))


class SingleDay(unittest.TestCase):
    def amount(self, start, end, rules=None):
        return sum((d.net for d in per_diem(Trip(start, end), rules or Rules())), D(0))

    def test_exactly_eight_hours_is_not_enough(self):
        self.assertEqual(self.amount(dt(2026, 3, 2, 8, 0), dt(2026, 3, 2, 16, 0)), D(0))

    def test_eight_hours_one_minute(self):
        self.assertEqual(self.amount(dt(2026, 3, 2, 8, 0), dt(2026, 3, 2, 16, 1)), D(14))

    def test_seven_hours(self):
        self.assertEqual(self.amount(dt(2026, 3, 2, 8, 0), dt(2026, 3, 2, 15, 0)), D(0))

    def test_threshold_can_be_configured_to_inclusive(self):
        rules = Rules(strictly_more_than=False)
        self.assertEqual(self.amount(dt(2026, 3, 2, 8, 0), dt(2026, 3, 2, 16, 0), rules), D(14))


class MidnightWithoutOvernight(unittest.TestCase):
    def test_larger_share_goes_to_second_day(self):
        trip = Trip(dt(2026, 3, 2, 22, 0), dt(2026, 3, 3, 7, 0), overnight=False)
        days = per_diem(trip, Rules())
        self.assertEqual([(d.day, d.net) for d in days], [(date(2026, 3, 3), D(14))])

    def test_start_day_rule(self):
        trip = Trip(dt(2026, 3, 2, 22, 0), dt(2026, 3, 3, 7, 0), overnight=False)
        days = per_diem(trip, Rules(midnight_rule="start_day"))
        self.assertEqual(days[0].day, date(2026, 3, 2))

    def test_short_night_gives_nothing(self):
        trip = Trip(dt(2026, 3, 2, 22, 0), dt(2026, 3, 3, 5, 0), overnight=False)
        self.assertEqual(per_diem(trip, Rules()), [])

    def test_two_midnights_force_multi_day(self):
        trip = Trip(dt(2026, 3, 2, 22, 0), dt(2026, 3, 4, 7, 0), overnight=False)
        self.assertTrue(trip.overnight)
        self.assertEqual(sum((d.net for d in per_diem(trip, Rules())), D(0)), D(14 + 28 + 14))


class MealCuts(unittest.TestCase):
    def test_full_day_breakfast_cut(self):
        trip = Trip(dt(2026, 3, 2, 8, 0), dt(2026, 3, 4, 18, 0), overnight=True,
                    meals={date(2026, 3, 3): {"breakfast"}})
        st = build_statement(trip, META, Rules())
        self.assertEqual(st.total, D(14) + D("28") - D("5.60") + D(14))
        self.assertTrue(any("Kürzung" in l.text and l.net == D("-5.60") for l in st.lines))

    def test_cut_never_below_zero(self):
        trip = Trip(dt(2026, 3, 2, 8, 0), dt(2026, 3, 2, 20, 0),
                    meals={date(2026, 3, 2): {"breakfast", "lunch", "dinner"}})
        self.assertEqual(sum((d.net for d in per_diem(trip, Rules())), D(0)), D(0))


class Kilometers(unittest.TestCase):
    def test_car_and_scooter(self):
        trip = Trip(dt(2026, 3, 2, 8, 0), dt(2026, 3, 2, 18, 0), km={"car": D("123.5"), "scooter": D("10")})
        st = build_statement(trip, META, Rules())
        self.assertEqual(st.total, D(14) + D("37.05") + D("2.00"))
        self.assertEqual(len(st.bookings), 2)


class RulesConfig(unittest.TestCase):
    def test_override_and_roundtrip(self):
        r = rules_for(2026, {"p8": "15", "strictly_more_than": False})
        self.assertEqual(r.p8, D("15"))
        self.assertFalse(r.strictly_more_than)
        self.assertEqual(Rules.from_dict(r.to_dict()), r)

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValueError):
            Rules.from_dict({"p9": 1})

    def test_future_year_uses_latest_known(self):
        self.assertEqual(rules_for(2030).p24, D("28"))


class AwaySum(unittest.TestCase):
    def test_away_duration_replaces_span_for_single_day(self):
        from datetime import timedelta
        r = Rules()
        t = Trip(dt(2026, 3, 2, 7, 0), dt(2026, 3, 2, 19, 0), away=timedelta(hours=9))
        self.assertEqual(per_diem(t, r)[0].gross, D("14"))
        self.assertEqual(per_diem(Trip(dt(2026, 3, 2, 7, 0), dt(2026, 3, 2, 19, 0), away=timedelta(hours=6)), r), [])
        self.assertEqual(len(per_diem(Trip(dt(2026, 3, 2, 7, 0), dt(2026, 3, 2, 19, 0)), r)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
