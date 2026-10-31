import unittest

from app.matching import match_scheme, recommend
from .helpers import TODAY, make_scheme, profile


class MatchingTests(unittest.TestCase):
    def state_scheme(self):
        return make_scheme(scheme_id="test-tn-scheme", jurisdiction="state_ut", state_ut="Tamil Nadu")

    def test_state_scheme_requires_state_match(self):
        rec = match_scheme(self.state_scheme(), profile(state_ut="Kerala"), TODAY)
        self.assertNotEqual(rec["match_status"], "potential_match")
        self.assertEqual(rec["match_status"], "unlikely_to_qualify")
        out = recommend([self.state_scheme()], profile(state_ut="Kerala"), TODAY)
        self.assertEqual(out["recommendations"], [])
        self.assertEqual(out["not_likely"][0]["scheme_id"], "test-tn-scheme")

    def test_state_scheme_matches_own_state(self):
        rec = match_scheme(self.state_scheme(), profile(), TODAY)
        self.assertEqual(rec["match_status"], "potential_match")

    def test_unknown_mandatory_field_needs_more_information(self):
        rec = match_scheme(make_scheme(), profile(business_stage=None), TODAY)
        self.assertEqual(rec["match_status"], "needs_more_information")
        self.assertIn("business_stage", rec["missing_fields"])

    def test_unmet_mandatory_criterion_is_not_potential_match(self):
        rec = match_scheme(make_scheme(), profile(business_stage="established"), TODAY)
        self.assertEqual(rec["match_status"], "unlikely_to_qualify")

    def test_not_met_wins_over_unknown(self):
        s = make_scheme(eligibility_rules=[
            {"field": "business_stage", "operator": "in", "value": ["newly_operating"], "mandatory": True, "explanation": "a"},
            {"field": "annual_turnover_inr", "operator": "lte", "value": 100, "mandatory": True, "explanation": "b"}])
        rec = match_scheme(s, profile(business_stage="established", annual_turnover_inr=None), TODAY)
        self.assertEqual(rec["match_status"], "unlikely_to_qualify")

    def test_numeric_rules(self):
        s = make_scheme(eligibility_rules=[
            {"field": "annual_turnover_inr", "operator": "lte", "value": 1000, "mandatory": True, "explanation": "t"}])
        self.assertEqual(match_scheme(s, profile(annual_turnover_inr=900), TODAY)["match_status"], "potential_match")
        self.assertEqual(match_scheme(s, profile(annual_turnover_inr=1001), TODAY)["match_status"], "unlikely_to_qualify")
        self.assertEqual(match_scheme(s, profile(annual_turnover_inr=0), TODAY)["match_status"], "potential_match")

    def test_supporting_criteria_do_not_change_status(self):
        s = make_scheme(eligibility_rules=[
            {"field": "business_stage", "operator": "in", "value": ["newly_operating"], "mandatory": True, "explanation": "a"},
            {"field": "ownership_category", "operator": "in", "value": ["llp"], "mandatory": False, "explanation": "b"}])
        rec = match_scheme(s, profile(), TODAY)
        self.assertEqual(rec["match_status"], "potential_match")
        self.assertTrue(any(r["outcome"] == "not_met" and not r["mandatory"] for r in rec["reasons"]))

    def test_other_and_unsure_answers_are_unknown_not_guessed(self):
        s = make_scheme(eligible_business_types=["manufacturing"], eligibility_rules=[])
        rec = match_scheme(s, profile(business_type="other"), TODAY)
        self.assertEqual(rec["match_status"], "needs_more_information")

    def test_empty_eligibility_data_is_never_a_match(self):  # E5
        rec = match_scheme(make_scheme(eligibility_rules=[], eligible_business_types=[]), profile(), TODAY)
        self.assertEqual(rec["match_status"], "needs_more_information")
        self.assertTrue(rec["data_incomplete"])

    def test_expired_scheme_not_active_recommendation(self):
        for status in ("expired", "withdrawn", "unverified"):
            s = make_scheme(scheme_status=status)
            out = recommend([s], profile(), TODAY)
            self.assertEqual(out["recommendations"], [], status)
            self.assertEqual(out["not_likely"], [], status)
            self.assertEqual(out["historical"][0]["scheme_status"], status)

    def test_possibly_changed_carries_warning(self):
        rec = match_scheme(make_scheme(scheme_status="possibly_changed"), profile(), TODAY)
        self.assertTrue(any("may have changed" in w for w in rec["warnings"]))

    def test_old_verification_is_labelled_needs_reverification(self):
        rec = match_scheme(make_scheme(last_verified_at="2026-01-01"), profile(), TODAY, 90)
        self.assertTrue(rec["needs_reverification"])
        self.assertEqual(rec["match_status"], "potential_match")  # warning only, not invalid
        fresh = match_scheme(make_scheme(last_verified_at="2026-10-01"), profile(), TODAY, 90)
        self.assertFalse(fresh["needs_reverification"])

    def test_ranking_potential_before_needs_info_then_criteria_then_need(self):
        a = make_scheme(scheme_id="aaa-needs-info", name="A", eligibility_rules=[
            {"field": "annual_turnover_inr", "operator": "lte", "value": 5, "mandatory": True, "explanation": "t"}])
        b = make_scheme(scheme_id="bbb-potential", name="B", support_types=["subsidy_grant"])
        c = make_scheme(scheme_id="ccc-potential", name="C", support_types=["credit_loan"])
        out = recommend([a, b, c], profile(), TODAY)["recommendations"]
        self.assertEqual([r["scheme_id"] for r in out], ["ccc-potential", "bbb-potential", "aaa-needs-info"])

    def test_response_has_no_numeric_score(self):
        rec = match_scheme(make_scheme(), profile(), TODAY)
        self.assertFalse({"score", "percentage", "probability"} & set(rec))

    def test_district_specific_local_scheme(self):
        s = make_scheme(scheme_id="test-local", jurisdiction="local", state_ut="Tamil Nadu", district="Chennai")
        self.assertEqual(match_scheme(s, profile(district="Chennai"), TODAY)["match_status"], "potential_match")
        self.assertEqual(match_scheme(s, profile(district=None), TODAY)["match_status"], "needs_more_information")
        self.assertEqual(match_scheme(s, profile(district="Madurai"), TODAY)["match_status"], "unlikely_to_qualify")


if __name__ == "__main__":
    unittest.main()
