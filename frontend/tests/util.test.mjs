import test from "node:test";
import assert from "node:assert/strict";
import { applyFilters, buildProfilePayload, checklistText, formatDate, formatInr, isValidSchemeId, labelize, safeUrl } from "../src/js/util.js";

test("safeUrl only allows https links", () => {
  assert.equal(safeUrl("https://www.mudra.org.in/"), "https://www.mudra.org.in/");
  for (const bad of ["javascript:alert(1)", "http://insecure.example", "data:text/html,x", "not a url", null, undefined]) assert.equal(safeUrl(bad), null, String(bad));
});

test("'I'm not sure' becomes null, never 0", () => {
  const p = buildProfilePayload({ state_ut: " Tamil Nadu ", business_type: "retail_trade", ownership_category: "other_unsure", business_stage: "established",
    annual_turnover_inr: "500000", turnover_unsure: true, employee_count: "4", employees_unsure: true, assistance_need: ["credit_loan"] });
  assert.equal(p.annual_turnover_inr, null);
  assert.equal(p.employee_count, null);
  assert.equal(p.state_ut, "Tamil Nadu");
  assert.equal(p.turnover_is_approximate, false);
});

test("blank optional numbers are null and numbers are parsed", () => {
  const p = buildProfilePayload({ annual_turnover_inr: "", employee_count: "0", assistance_need: [] });
  assert.equal(p.annual_turnover_inr, null);
  assert.equal(p.employee_count, 0);
  assert.equal(p.district, null);
  assert.equal(p.registration_status, null);
});

test("business_type_other only sent for 'other'", () => {
  assert.equal(buildProfilePayload({ business_type: "services", business_type_other: "x" }).business_type_other, null);
  assert.equal(buildProfilePayload({ business_type: "other", business_type_other: " tailoring " }).business_type_other, "tailoring");
});

test("filters", () => {
  const recs = [
    { name: "A", jurisdiction: "central", state_ut: null, support_types: ["credit_loan"], match_status: "potential_match" },
    { name: "B", jurisdiction: "state_ut", state_ut: "Tamil Nadu", support_types: ["subsidy_grant"], match_status: "needs_more_information" },
  ];
  assert.equal(applyFilters(recs, {}).length, 2);
  assert.deepEqual(applyFilters(recs, { state_ut: "central" }).map((r) => r.name), ["A"]);
  assert.deepEqual(applyFilters(recs, { state_ut: "Tamil Nadu" }).map((r) => r.name), ["B"]);
  assert.deepEqual(applyFilters(recs, { support_type: "credit_loan" }).map((r) => r.name), ["A"]);
  assert.deepEqual(applyFilters(recs, { status: "needs_more_information", jurisdiction: "state_ut" }).map((r) => r.name), ["B"]);
  assert.equal(applyFilters(recs, { status: "unlikely_to_qualify" }).length, 0);
});

test("checklist text includes labels, tick state and disclaimer", () => {
  const cl = { scheme_name: "X", last_verified_at: "2026-10-31", disclaimer: "May change.", official_source_urls: ["https://a.gov.in/"],
    items: [{ name: "KYC", label: "Confirm with official source", notes: "n" }, { name: "Quote", label: "Conditional", notes: "" }] };
  const t = checklistText(cl, { 0: true });
  assert.match(t, /\[x\] KYC — Confirm with official source \(n\)/);
  assert.match(t, /\[ \] Quote — Conditional/);
  assert.match(t, /May change\./);
  assert.match(t, /not a government website/);
  assert.match(checklistText({ ...cl, items: [], unavailable_message: "None listed." }), /None listed\./);
});

test("formatting helpers", () => {
  assert.equal(formatInr(null), "Not provided");
  assert.equal(formatInr(1200000), "₹12,00,000");
  assert.equal(formatDate("2026-10-31"), "31 Oct 2026");
  assert.equal(formatDate("bad"), "Unavailable");
  assert.equal(labelize("credit_loan"), "Credit / loan support");
  assert.equal(labelize("some_new_value"), "Some new value");
});

test("scheme id validation", () => {
  assert.ok(isValidSchemeId("in-central-pmegp"));
  for (const bad of ["../etc", "A B", "", "x", undefined, "a/b"]) assert.equal(isValidSchemeId(bad), false, String(bad));
});
