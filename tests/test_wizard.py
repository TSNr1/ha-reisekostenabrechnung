import sys
import unittest
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "reisekosten"))

from core.rules import Rules  # noqa: E402
from core.wizard import (  # noqa: E402
    Pending, apply_answer, next_step, parse_km, parse_meals, qualifies, to_trip,
)

TZ = ZoneInfo("Europe/Berlin")


def dt(d, h, mi=0, mo=3, y=2026):
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


class Qualifies(unittest.TestCase):
    def test_threshold(self):
        r = Rules()
        self.assertFalse(qualifies(dt(2, 8), dt(2, 16), r))
        self.assertTrue(qualifies(dt(2, 8), dt(2, 16, 1), r))
        self.assertFalse(qualifies(dt(2, 8), dt(2, 7), r))
        self.assertTrue(qualifies(dt(2, 8), dt(2, 16), Rules(strictly_more_than=False)))


class Flow(unittest.TestCase):
    def run_flow(self, p, answers, rules=None):
        rules = rules or Rules()
        asked = []
        while (step := next_step(p, rules)) is not None:
            asked.append(step)
            apply_answer(p, step, answers[step])
        return asked

    def test_single_day_asks_three_questions(self):
        p = Pending("x", dt(2, 7), dt(2, 18))
        asked = self.run_flow(p, {"name": "Kunde", "purpose": "Unterricht", "km": "120,5", "meals": "-"})
        self.assertEqual(asked, ["name", "purpose", "km", "meals"])
        self.assertFalse(p.overnight)
        t = to_trip(p)
        self.assertEqual(t.km, {"car": D("120.5")})

    def test_midnight_asks_overnight(self):
        p = Pending("x", dt(2, 22), dt(3, 9))
        asked = self.run_flow(p, {"name": "a", "purpose": "b", "km": "-", "overnight": "yes", "meals": "-"})
        self.assertIn("overnight", asked)
        self.assertTrue(p.overnight)
        self.assertEqual(to_trip(p).km, {})

    def test_multi_day_skips_overnight_question(self):
        p = Pending("x", dt(7, 8, mo=1), dt(17, 13, mo=1))
        asked = self.run_flow(p, {"name": "a", "purpose": "b", "km": "0", "meals": "-"})
        self.assertNotIn("overnight", asked)
        self.assertTrue(p.overnight)

    def test_no_meal_question_without_per_diem(self):
        p = Pending("x", dt(2, 22), dt(3, 5), name="a", purpose="b", km_car=D(0), overnight=False)
        self.assertIsNone(next_step(p, Rules()))
        self.assertEqual(p.meals, {})

    def test_km_disabled_skips_question_and_billing(self):
        p = Pending("x", dt(2, 7), dt(2, 18))
        asked = self.run_flow(p, {"name": "a", "purpose": "b", "meals": "-"}, Rules(km_enabled=False))
        self.assertEqual(asked, ["name", "purpose", "meals"])
        self.assertEqual(to_trip(p).km, {})

    def test_roundtrip(self):
        p = Pending("x", dt(2, 7), dt(2, 18), name="a", purpose="b", km_car=D("1.5"),
                    overnight=False, meals={date(2026, 3, 2): {"lunch"}})
        q = Pending.from_dict(p.to_dict())
        self.assertEqual(q, p)

    def test_blank_defaults(self):
        p = Pending("x", dt(2, 7), dt(2, 18))
        apply_answer(p, "name", "-")
        apply_answer(p, "purpose", "")
        self.assertEqual((p.name, p.purpose), ("Dienstreise", "Dienstreise"))


class Parsing(unittest.TestCase):
    def test_km(self):
        self.assertEqual(parse_km("123,5 km"), D("123.5"))
        self.assertEqual(parse_km("-"), D(0))
        with self.assertRaises(ValueError):
            parse_km("viel")
        with self.assertRaises(ValueError):
            parse_km("-5")

    def test_meals(self):
        m = parse_meals("08.01 FA, 09.01 M, 10.01", dt(7, 8, mo=1), dt(17, 13, mo=1))
        self.assertEqual(m[date(2026, 1, 8)], {"breakfast", "dinner"})
        self.assertEqual(m[date(2026, 1, 9)], {"lunch"})
        self.assertEqual(m[date(2026, 1, 10)], {"breakfast", "lunch", "dinner"})

    def test_meals_errors(self):
        with self.assertRaises(ValueError):
            parse_meals("blabla", dt(7, 8, mo=1), dt(17, 13, mo=1))
        with self.assertRaises(ValueError):
            parse_meals("20.01 F", dt(7, 8, mo=1), dt(17, 13, mo=1))
        with self.assertRaises(ValueError):
            parse_meals("31.02 F", dt(7, 8, mo=1), dt(17, 13, mo=1))

    def test_meals_skip(self):
        self.assertEqual(parse_meals("nein", dt(7, 8), dt(7, 18)), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
