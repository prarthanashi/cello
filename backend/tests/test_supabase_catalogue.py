import unittest
from types import SimpleNamespace

from app.supabase_catalogue import load_supabase_catalogue
from .helpers import make_settings


class FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.start = 0
        self.end = len(rows)

    def select(self, _columns):
        return self

    def range(self, start, end):
        self.start, self.end = start, end + 1
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows[self.start:self.end])


class FakeClient:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeTable(self.tables[name])


class SupabaseCatalogueTests(unittest.TestCase):
    def test_related_rows_are_mapped_into_scheme_record(self):
        client = FakeClient({
            "schemes": [{
                "scheme_id": "test-central-scheme", "name": "Example Scheme",
                "summary": "Example summary.", "jurisdiction": "central", "state_ut": None,
                "support_types": ["credit_loan"], "eligible_business_types": [],
                "benefits": ["Example benefit."], "exclusions": [], "application_steps": ["Apply online."],
                "scheme_status": "active", "last_verified_at": "2026-10-31",
            }],
            "eligibility_rules": [{
                "scheme_id": "test-central-scheme", "field": "business_stage", "operator": "in",
                "value": ["newly_operating"], "is_mandatory": True, "explanation": "New businesses.",
                "source_excerpt": "New businesses may apply.",
            }],
            "scheme_documents": [{
                "scheme_id": "test-central-scheme", "name": "Identity document",
                "requirement_type": "required", "notes": "Bring proof of identity.",
            }],
            "scheme_sources": [{
                "scheme_id": "test-central-scheme", "url": "https://example.gov.in/scheme",
                "title": "Official scheme page",
            }],
        })

        catalogue = load_supabase_catalogue(
            make_settings(supabase_url="https://example.supabase.co", supabase_secret_key="test-key"),
            ("gov.in", "nic.in"), client=client,
        )

        self.assertEqual(catalogue.load_errors, [])
        scheme = catalogue.get("test-central-scheme")
        self.assertEqual(scheme.official_source_urls, ["https://example.gov.in/scheme"])
        self.assertEqual(scheme.eligibility_rules[0]["mandatory"], True)
        self.assertEqual(scheme.eligibility_rules[0]["source_excerpt"], "New businesses may apply.")
        self.assertEqual(scheme.required_documents[0]["name"], "Identity document")
        self.assertEqual(scheme.benefits, ["Example benefit."])

    def test_missing_credentials_yield_empty_catalogue_with_error(self):
        catalogue = load_supabase_catalogue(make_settings(), ("gov.in",))
        self.assertEqual(len(catalogue), 0)
        self.assertTrue(catalogue.load_errors)


if __name__ == "__main__":
    unittest.main()
