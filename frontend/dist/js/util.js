// Pure helpers (no DOM). Unit-tested in frontend/tests/util.test.mjs.

export const LABELS = {
  retail_trade: "Retail / trading", manufacturing: "Manufacturing", services: "Services",
  food_processing: "Food processing", artisan_craft: "Artisan / craft", technology: "Technology",
  agriculture_allied: "Agriculture-allied", street_vending: "Street vending / hawking", other: "Other",
  individual_proprietorship: "Individual / proprietorship", partnership: "Partnership", llp: "LLP",
  private_limited_company: "Private limited company", cooperative: "Cooperative",
  self_help_group: "Self-help group", other_unsure: "Other / I’m not sure",
  idea_pre_launch: "Idea / pre-launch", newly_operating: "Newly operating", established: "Established", expanding: "Expanding",
  credit_loan: "Credit / loan support", subsidy_grant: "Subsidy / grant", equipment_technology: "Equipment / technology",
  training_mentoring: "Training / mentoring", market_access: "Market access", working_capital: "Working capital",
  low_income_assistance: "Low-income assistance",
  registered: "Registered", not_registered: "Not registered", in_progress: "In progress", unsure: "Unsure",
  central: "Central", state_ut: "State / UT", local: "Local",
  active: "Active", possibly_changed: "Possibly changed", expired: "Expired", withdrawn: "Withdrawn", unverified: "Unverified",
  annual_turnover_inr: "Annual turnover", employee_count: "Employee count", business_stage: "Business stage",
  business_type: "Business type", ownership_category: "Ownership category", assistance_need: "Support needed",
  registration_status: "Registration status", district: "District", jurisdiction: "Location", eligibility_details: "Eligibility details",
};

export const MATCH_LABELS = {
  potential_match: "Potential match",
  needs_more_information: "Needs more information",
  unlikely_to_qualify: "Unlikely to qualify",
};

export function labelize(value) {
  if (value in LABELS) return LABELS[value];
  const s = String(value ?? "").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function formatInr(n) {
  if (n === null || n === undefined || n === "") return "Not provided";
  return "₹" + Number(n).toLocaleString("en-IN");
}

export function formatDate(iso) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) return "Unavailable";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** Only https links are ever rendered as links. */
export function safeUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

/** Form values -> API payload. "Not sure" choices become null (unknown), never 0 or a guess. */
export function buildProfilePayload(v) {
  const num = (x) => (x === "" || x === null || x === undefined ? null : Number(x));
  return {
    state_ut: (v.state_ut || "").trim(),
    district: (v.district || "").trim() || null,
    business_type: v.business_type || "",
    business_type_other: v.business_type === "other" ? ((v.business_type_other || "").trim() || null) : null,
    ownership_category: v.ownership_category || "",
    business_stage: v.business_stage || "",
    annual_turnover_inr: v.turnover_unsure ? null : num(v.annual_turnover_inr),
    turnover_is_approximate: Boolean(v.turnover_approximate) && !v.turnover_unsure,
    employee_count: v.employees_unsure ? null : num(v.employee_count),
    assistance_need: Array.isArray(v.assistance_need) ? v.assistance_need : [],
    registration_status: v.registration_status || null,
    additional_details: (v.additional_details || "").trim() || null,
  };
}

export function reasonsToShow(rec, limit = 2) {
  return rec.reasons.slice(0, limit);
}

export function applyFilters(recs, f) {
  return recs.filter((r) =>
    (!f.state_ut || (f.state_ut === "central" ? r.jurisdiction === "central" : r.state_ut === f.state_ut)) &&
    (!f.support_type || r.support_types.includes(f.support_type)) &&
    (!f.jurisdiction || r.jurisdiction === f.jurisdiction) &&
    (!f.status || r.match_status === f.status));
}

export function checklistText(cl, checked = {}) {
  const lines = [`Document checklist: ${cl.scheme_name}`, `Catalogue record last verified: ${formatDate(cl.last_verified_at)}`, ""];
  if (!cl.items.length) lines.push(cl.unavailable_message || "Document requirements are not specified in the available source.");
  cl.items.forEach((it, i) => {
    lines.push(`${checked[i] ? "[x]" : "[ ]"} ${it.name} — ${it.label}${it.notes ? ` (${it.notes})` : ""}`);
  });
  lines.push("", cl.disclaimer);
  if (cl.official_source_urls?.length) lines.push("Official source: " + cl.official_source_urls.join(" "));
  lines.push("Prepared with BenefitBridge, an independent information tool (not a government website).");
  return lines.join("\n");
}

export function isValidSchemeId(id) {
  return /^[a-z0-9][a-z0-9-]{2,80}$/.test(id || "");
}
