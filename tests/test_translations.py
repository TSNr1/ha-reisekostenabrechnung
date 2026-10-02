import json
import unittest
from pathlib import Path

T = Path(__file__).resolve().parents[1] / "custom_components" / "reisekosten" / "translations"
EXPECTED = {
    "select": {"trip"}, "text": {"field_name", "field_purpose", "field_meals", "answer"},
    "number": {"field_km"}, "switch": {"field_overnight"},
    "button": {"btn_apply", "btn_delete", "btn_discard_open", "btn_resend"},
}


class Translations(unittest.TestCase):
    def test_entity_names_have_ha_structure(self):
        for lang in ("de", "en"):
            ent = json.loads((T / f"{lang}.json").read_text(encoding="utf-8"))["entity"]
            for platform, keys in EXPECTED.items():
                self.assertEqual(set(ent[platform]), keys, (lang, platform))
                for k, v in ent[platform].items():
                    self.assertIsInstance(v, dict, (lang, platform, k))
                    self.assertTrue(v.get("name"), (lang, platform, k))
