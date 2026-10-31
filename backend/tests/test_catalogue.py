import json
import unittest

from app.catalogue import build_catalogue, is_official_url, validate_scheme_record
from app.config import DEFAULT_OFFICIAL_SUFFIXES as SUF, PROJECT_ROOT
from .helpers import raw_scheme


class CatalogueTests(unittest.TestCase):
    def test_missing_official_url_prevents_activation(self):
        errors = validate_scheme_record(raw_scheme(official_source_urls=[]), SUF)
        self.assertTrue(any("official source URL" in e for e in errors))
        cat = build_catalogue([raw_scheme(official_source_urls=[])], SUF)
        self.assertEqual(cat.get("test-central-scheme").scheme_status, "unverified")
        self.assertTrue(cat.get("test-central-scheme").is_inactive)

    def test_non_official_url_is_rejected(self):  # E6
        for bad in ["https://some-blog.com/pmegp", "http://www.kviconline.gov.in", "https://evilgov.in.example.com/x", "javascript:alert(1)"]:
            self.assertFalse(is_official_url(bad, SUF), bad)
        errors = validate_scheme_record(raw_scheme(official_source_urls=["https://blog.example.com/x"]), SUF)
        self.assertTrue(errors)

    def test_official_urls_accepted(self):
        self.assertTrue(is_official_url("https://www.mudra.org.in/", SUF))
        self.assertTrue(is_official_url("https://pmsvanidhi.mohua.gov.in/", SUF))

    def test_empty_eligible_business_types_means_unknown_not_all(self):
        from .helpers import make_scheme
        self.assertEqual([r for r in make_scheme(eligibility_rules=[], eligible_business_types=[]).effective_rules()], [])

    def test_record_needs_verification_date_and_structured_eligibility(self):
        self.assertTrue(validate_scheme_record(raw_scheme(last_verified_at="31/10/2026"), SUF))
        self.assertTrue(validate_scheme_record(raw_scheme(eligibility_rules=[], eligible_business_types=[]), SUF))

    def test_state_scheme_needs_canonical_state(self):
        self.assertTrue(validate_scheme_record(raw_scheme(jurisdiction="state_ut", state_ut="Tamilnadu"), SUF))

    def test_duplicate_ids_are_not_silently_merged(self):
        cat = build_catalogue([raw_scheme(), raw_scheme(name="Other")], SUF)
        self.assertEqual(len(cat), 1)
        self.assertTrue(any("duplicate" in e for p in cat.load_errors for e in p["errors"]))

    def test_seed_catalogue_is_valid_and_fully_sourced(self):  # AC3
        data = json.loads((PROJECT_ROOT / "data" / "schemes.json").read_text(encoding="utf-8"))
        cat = build_catalogue(data["schemes"], SUF)
        self.assertEqual(cat.load_errors, [])
        self.assertGreaterEqual(len(cat), 1)
        for s in cat.all():
            self.assertTrue(s.scheme_id and s.last_verified_at and s.jurisdiction and s.scheme_status)
            if s.scheme_status in ("active", "possibly_changed"):
                self.assertTrue(s.official_source_urls)
                self.assertTrue(all(is_official_url(u, SUF) for u in s.official_source_urls))


if __name__ == "__main__":
    unittest.main()
