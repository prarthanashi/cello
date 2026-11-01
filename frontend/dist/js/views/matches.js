import { clear, h } from "../dom.js";
import { session } from "../state.js";
import { MATCH_LABELS, applyFilters, formatDate, formatInr, labelize, reasonsToShow, safeUrl } from "../util.js";

const filters = { state_ut: "", support_type: "", jurisdiction: "", status: "" };

function badge(status) {
  return h("span", { class: `badge ${status}` }, MATCH_LABELS[status] || labelize(status));
}

function card(rec, go) {
  const shown = reasonsToShow(rec);
  const rest = rec.reasons.slice(shown.length);
  const reasonLi = (r) => h("li", { class: `reason ${r.outcome}` },
    h("span", { class: "reason-mark", "aria-hidden": "true" }, r.outcome === "met" ? "✓" : r.outcome === "not_met" ? "✕" : "?"),
    h("span", {}, r.explanation, r.mandatory ? null : h("em", {}, " (supporting criterion; does not change the status)")));
  return h("article", { class: "card scheme-card", "aria-labelledby": `t-${rec.scheme_id}` },
    h("div", { class: "card-head" },
      h("h3", { id: `t-${rec.scheme_id}` }, rec.name),
      badge(rec.match_status)),
    h("p", { class: "meta" },
      h("span", { class: "chip" }, rec.jurisdiction === "central" ? "Central scheme" : `${rec.state_ut} scheme`),
      rec.support_types.map((s) => h("span", { class: "chip alt" }, labelize(s)))),
    rec.warnings.map((w) => h("p", { class: "warn" }, "⚠ ", w)),
    h("ul", { class: "reasons" }, shown.map(reasonLi)),
    rest.length ? h("details", {}, h("summary", {}, `Show all ${rec.reasons.length} checks`), h("ul", { class: "reasons" }, rest.map(reasonLi))) : null,
    rec.missing_fields.length
      ? h("p", { class: "missing" }, h("strong", {}, "To confirm: "), `we couldn’t check ${rec.missing_fields.map(labelize).join(", ").toLowerCase()} because it is missing or unsure.`)
      : null,
    rec.conditions_to_confirm.length
      ? h("details", {}, h("summary", {}, "Other conditions to check on the official source"), h("ul", {}, rec.conditions_to_confirm.map((c) => h("li", {}, c))))
      : null,
    h("div", { class: "card-foot" },
      h("span", { class: "verified" }, `Last verified ${formatDate(rec.last_verified_at)}`, rec.needs_reverification ? h("strong", { class: "stale" }, " · Needs re-verification") : null),
      h("button", { class: "btn primary", onclick: () => go(`#/scheme/${rec.scheme_id}`) }, "View details")));
}

function filterBar(result, rerender) {
  const all = [...result.recommendations, ...result.not_likely];
  const states = [...new Set(all.map((r) => r.state_ut).filter(Boolean))].sort();
  const supports = [...new Set(all.flatMap((r) => r.support_types))].sort();
  const sel = (key, label, options) => h("label", {}, label,
    h("select", { onchange: (e) => { filters[key] = e.target.value; rerender(); } },
      h("option", { value: "" }, "All"),
      options.map(([v, l]) => h("option", { value: v, selected: filters[key] === v }, l))));
  return h("div", { class: "filters card", role: "search", "aria-label": "Filter schemes" },
    sel("state_ut", "State / UT", [["central", "Central (all India)"], ...states.map((s) => [s, s])]),
    sel("support_type", "Support type", supports.map((s) => [s, labelize(s)])),
    sel("jurisdiction", "Scheme type", [["central", "Central"], ["state_ut", "State / UT"]]),
    sel("status", "Match status", Object.entries(MATCH_LABELS)),
    h("button", { class: "btn link", onclick: () => { Object.keys(filters).forEach((k) => { filters[k] = ""; }); rerender(); } }, "Reset filters"));
}

export function renderMatches(root, { go }) {
  const result = session.result;
  if (!result) { go("#/"); return; }
  const p = result.profile_used;

  const body = h("div", {});
  const draw = () => {
    clear(body);
    const recs = applyFilters(result.recommendations, filters);
    const unlikely = applyFilters(result.not_likely, filters);
    body.append(filterBar(result, draw));
    if (!result.recommendations.length) {
      body.append(h("div", { class: "card empty" }, h("h3", {}, "No likely matches found in the current catalogue"),
        h("p", {}, "Try adding missing profile details or changing your support needs. The catalogue is small, so this does not mean no support exists."),
        h("button", { class: "btn primary", onclick: () => go("#/") }, "Edit profile")));
    } else if (!recs.length) {
      body.append(h("div", { class: "card empty" }, h("p", {}, "No schemes match these filters."), h("button", { class: "btn", onclick: () => { Object.keys(filters).forEach((k) => { filters[k] = ""; }); draw(); } }, "Reset filters")));
    } else {
      body.append(h("div", { class: "grid" }, recs.map((r) => card(r, go))));
    }
    if (unlikely.length) {
      body.append(h("details", { class: "card unlikely" }, h("summary", {}, `Schemes unlikely to qualify (${unlikely.length})`),
        h("p", { class: "hint" }, "Shown so you can see why these were ruled out. Check the reasons; your answers may be incomplete."),
        h("div", { class: "grid" }, unlikely.map((r) => card(r, go)))));
    }
    if (result.historical.length) {
      body.append(h("div", { class: "card" }, h("h3", {}, "Expired, withdrawn or unverified records"),
        h("ul", {}, result.historical.map((s) => h("li", {}, `${s.name}: ${s.message}`)))));
    }
  };
  draw();

  const summary = h("div", { class: "card summary" },
    h("div", {}, h("h2", {}, "Your matches"),
      h("p", { class: "meta" },
        [["State / UT", p.state_ut], ["Business", labelize(p.business_type)], ["Ownership", labelize(p.ownership_category)],
          ["Stage", labelize(p.business_stage)], ["Turnover", p.annual_turnover_inr == null ? "Not provided" : formatInr(p.annual_turnover_inr) + (p.turnover_is_approximate ? " (approx.)" : "")],
          ["Employees", p.employee_count ?? "Not provided"], ["Support", p.assistance_need.map(labelize).join(", ")]]
          .map(([k, v]) => h("span", { class: "chip" }, `${k}: ${v}`)))),
    h("button", { class: "btn", onclick: () => go("#/") }, "Edit profile"));

  clear(root).append(summary,
    h("p", { class: "notice" }, result.catalogue_notice),
    h("p", { class: "hint" }, result.ranking_note),
    body);
}
