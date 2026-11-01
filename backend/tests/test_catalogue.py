import unittest

from app.catalogue import build_catalogue, is_official_url, validate_scheme_record
from app.config import DEFAULT_OFFICIAL_SUFFIXES as SUF
from .helpers import raw_scheme


class CatalogueTests(unittest.TestCase):
    def test_missing_official_url_prevents_activation(self):
        errors = validate_scheme_record(raw_scheme(official_source_urls=[]), SUF)
        self.assertTrue(any("official source URL" in e for e in errors))
        cat = build_catalogue([raw_scheme(official_source_urls=[])], SUF)
        self.assertEqual(cat.get("test-central-scheme").scheme_status, "unverified")
        self.assertTrue(cat.get("test-central-scheme").is_inactive)

    def test_non_official_url_is_rejected(self):  # E6
        for bad in ["https://some-blog.com/page", "http://www.department.gov.in", "https://evilgov.in.example.com/x", "javascript:alert(1)"]:
            self.assertFalse(is_official_url(bad, SUF), bad)
        errors = validate_scheme_record(raw_scheme(official_source_urls=["https://blog.example.com/x"]), SUF)
        self.assertTrue(errors)

    def test_official_urls_accepted(self):
        self.assertTrue(is_official_url("https://department.gov.in/", SUF))
        self.assertTrue(is_official_url("https://portal.nic.in/", SUF))

    def test_empty_eligible_business_types_means_unknown_not_all(self):
        from .helpers import make_scheme
        self.assertEqual([r for r in make_scheme(eligibility_rules=[], eligible_business_types=[]).effective_rules()], [])

    def test_record_needs_verification_date_and_structured_eligibility(self):
        self.assertTrue(validate_scheme_record(raw_scheme(last_verified_at="31/10/2026"), SUF))
        self.assertTrue(validate_scheme_record(raw_scheme(eligibility_rules=[], eligible_business_types=[]), SUF))

    def test_between_rule_requires_two_numeric_bounds(self):
        rule = {"field": "annual_turnover_inr", "operator": "between", "value": [10, 100],
                "mandatory": True, "explanation": "Turnover range.", "source_excerpt": "Turnover range."}
        self.assertEqual(validate_scheme_record(raw_scheme(eligibility_rules=[rule]), SUF), [])
        rule["value"] = [10, "100"]
        self.assertTrue(validate_scheme_record(raw_scheme(eligibility_rules=[rule]), SUF))

    def test_state_scheme_needs_canonical_state(self):
        self.assertTrue(validate_scheme_record(raw_scheme(jurisdiction="state_ut", state_ut="Tamilnadu"), SUF))

    def test_duplicate_ids_are_not_silently_merged(self):
        cat = build_catalogue([raw_scheme(), raw_scheme(name="Other")], SUF)
        self.assertEqual(len(cat), 1)
        self.assertTrue(any("duplicate" in e for p in cat.load_errors for e in p["errors"]))

if __name__ == "__main__":
    unittest.main()
