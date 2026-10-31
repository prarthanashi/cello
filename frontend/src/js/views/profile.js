import { api, ApiError } from "../api.js";
import { clear, h, spinner } from "../dom.js";
import { session } from "../state.js";
import { buildProfilePayload, labelize } from "../util.js";

const FIELD_ORDER = ["state_ut", "district", "business_type", "business_type_other", "ownership_category", "business_stage",
  "annual_turnover_inr", "employee_count", "assistance_need", "registration_status", "additional_details"];

function select(name, values, selected, placeholder, labelFn = labelize) {
  return h("select", { name, id: `f-${name}`, "aria-describedby": `err-${name}` },
    h("option", { value: "" }, placeholder),
    values.map((v) => h("option", { value: v, selected: v === selected }, labelFn(v))));
}

function field(name, label, required, hint, control) {
  return h("div", { class: "field", id: `row-${name}` },
    h("label", { for: `f-${name}` }, label, " ", h("span", { class: required ? "tag req" : "tag opt" }, required ? "Required" : "Optional")),
    hint ? h("p", { class: "hint", id: `hint-${name}` }, hint) : null,
    control,
    h("p", { class: "field-error", id: `err-${name}`, role: "alert" }));
}

function collect(form) {
  const fd = new FormData(form);
  const v = Object.fromEntries([...fd.entries()].filter(([k]) => k !== "assistance_need"));
  v.assistance_need = fd.getAll("assistance_need");
  v.turnover_unsure = form.elements.turnover_unsure.checked;
  v.turnover_approximate = form.elements.turnover_approximate.checked;
  v.employees_unsure = form.elements.employees_unsure.checked;
  return v;
}

export function renderProfile(root, { options, go, notice }) {
  clear(root);
  const d = session.draft;
  const form = h("form", { class: "card form", novalidate: true, "aria-labelledby": "profile-title" });
  const banner = h("div", { class: "banner error", role: "alert", hidden: true });
  const submit = h("button", { type: "submit", class: "btn primary" }, "Find relevant schemes");

  const otherRow = field("business_type_other", "Describe your business", false, "Example: “home-based tailoring and alterations”.",
    h("input", { type: "text", name: "business_type_other", id: "f-business_type_other", maxlength: 100, value: d.business_type_other || "", "aria-describedby": "err-business_type_other" }));
  const toggleOther = () => { otherRow.hidden = form.elements.business_type.value !== "other"; };

  const turnover = h("input", { type: "number", name: "annual_turnover_inr", id: "f-annual_turnover_inr", min: 0, step: "any", inputmode: "numeric",
    value: d.annual_turnover_inr ?? "", disabled: d.turnover_unsure, "aria-describedby": "err-annual_turnover_inr" });
  const employees = h("input", { type: "number", name: "employee_count", id: "f-employee_count", min: 0, step: 1, inputmode: "numeric",
    value: d.employee_count ?? "", disabled: d.employees_unsure, "aria-describedby": "err-employee_count" });
  const check = (name, label, on, handler) =>
    h("label", { class: "check" }, h("input", { type: "checkbox", name, checked: !!on, onchange: handler }), label);

  const details = h("textarea", { name: "additional_details", id: "f-additional_details", rows: 3, maxlength: 1000, "aria-describedby": "hint-additional_details err-additional_details" }, d.additional_details || "");

  form.append(
    h("h2", { id: "profile-title" }, "Build your business profile"),
    h("p", { class: "lead" }, "Tell us a little about your business. We compare it with a small catalogue of government schemes and show what may fit. Skip anything you’re unsure about; we won’t guess."),
    h("div", { class: "privacy" }, h("strong", {}, "Privacy: "), "Your profile is not saved on our servers. It stays in this browser tab for the session and is cleared when you reset or close the tab. Use fictional or minimal details; never enter bank, identity or password information."),
    banner,
    h("fieldset", {}, h("legend", {}, "1 · Business location"),
      field("state_ut", "State / Union Territory", true, "Where the business operates.", select("state_ut", options.states_ut, d.state_ut, "Select state / UT", (x) => x)),
      field("district", "District or city", false, "Example: “Chennai”. Only a few schemes need this.",
        h("input", { type: "text", name: "district", id: "f-district", maxlength: 80, value: d.district || "", autocomplete: "off", "aria-describedby": "hint-district err-district" }))),
    h("fieldset", {}, h("legend", {}, "2 · Business details"),
      field("business_type", "Business type / activity", true, "Choose the closest match; pick “Other” if none fits.",
        select("business_type", options.business_types, d.business_type, "Select a business type")),
      otherRow,
      field("ownership_category", "Ownership category", true, "How the business is legally set up. Choose “Other / I’m not sure” if unsure.",
        select("ownership_category", options.ownership_categories, d.ownership_category, "Select ownership category")),
      field("business_stage", "Business stage", true, "Where the business is today.", select("business_stage", options.business_stages, d.business_stage, "Select stage")),
      field("annual_turnover_inr", "Annual turnover (₹ per year)", false, "Example: 1200000. Leave blank or tick “I’m not sure” if you don’t know.",
        h("div", { class: "inline" }, turnover,
          check("turnover_approximate", "This is approximate", d.turnover_approximate),
          check("turnover_unsure", "I’m not sure", d.turnover_unsure, (e) => { turnover.disabled = e.target.checked; }))),
      field("employee_count", "Number of employees", false, "Include yourself only if you count as an employee. Whole number.",
        h("div", { class: "inline" }, employees,
          check("employees_unsure", "I’m not sure", d.employees_unsure, (e) => { employees.disabled = e.target.checked; }))),
      field("registration_status", "Registration status", false, "For example Udyam or GST registration. Ask only where it helps matching.",
        select("registration_status", options.registration_statuses, d.registration_status, "Not specified"))),
    h("fieldset", {}, h("legend", {}, "3 · Support needed"),
      field("assistance_need", "What kind of support are you looking for?", true, "Choose at least one.",
        h("div", { class: "checks", role: "group", "aria-describedby": "err-assistance_need" },
          options.assistance_needs.map((n) => h("label", { class: "check" },
            h("input", { type: "checkbox", name: "assistance_need", value: n, checked: (d.assistance_need || []).includes(n) }), labelize(n))))),
      field("additional_details", "Anything else? (max 1,000 characters)", false, "Warning: do not enter bank account numbers, passwords, identity numbers or other sensitive information. This text is not used for matching.", details)),
    h("div", { class: "actions" }, submit,
      h("button", { type: "button", class: "btn", onclick: async (e) => {
        e.target.disabled = true;
        try { const r = await api.demoProfile(); session.draft = r.profile; renderProfile(root, { options, go, notice }); }
        catch (err) { show(banner, err.message); e.target.disabled = false; }
      } }, "Use sample profile"),
      h("button", { type: "button", class: "btn link", onclick: () => { session.reset(); renderProfile(root, { options, go, notice }); } }, "Reset form")),
  );

  form.addEventListener("input", () => { session.draft = collect(form); });
  form.addEventListener("change", () => { session.draft = collect(form); toggleOther(); });
  toggleOther();

  function show(el, msg) { el.textContent = msg; el.hidden = false; }
  function markErrors(fields) {
    form.querySelectorAll(".field-error").forEach((p) => { p.textContent = ""; });
    form.querySelectorAll("[aria-invalid]").forEach((i) => i.removeAttribute("aria-invalid"));
    let first = null;
    for (const name of FIELD_ORDER.filter((n) => fields[n])) {
      document.getElementById(`err-${name}`).textContent = fields[name];
      const input = form.elements[name]?.[0] ?? form.elements[name];
      input?.setAttribute?.("aria-invalid", "true");
      first = first || input;
    }
    first?.focus?.();
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    banner.hidden = true;
    markErrors({});
    const values = collect(form);
    session.draft = values;
    submit.disabled = true;
    clear(submit).append(spinner("Finding schemes…"));
    try {
      session.result = await api.match(buildProfilePayload(values));
      go("#/matches");
    } catch (err) {
      if (err instanceof ApiError && err.code === "validation_error") {
        show(banner, "Please complete the highlighted fields to find relevant schemes.");
        markErrors(err.fields || {});
      } else {
        show(banner, err.message);  // values stay in the form (E1, E16)
      }
    } finally {
      submit.disabled = false;
      clear(submit).append("Find relevant schemes");
    }
  });

  root.append(form);
}
