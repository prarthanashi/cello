import { api, ApiError } from "../api.js";
import { clear, h, spinner } from "../dom.js";
import { session } from "../state.js";
import { MATCH_LABELS, checklistText, formatDate, labelize, safeUrl } from "../util.js";

const SUGGESTED = ["Who can apply?", "Which documents are listed?", "How do I apply?"];
const NOT_CONFIGURED = "AI answers are not configured yet; scheme matching and official links remain available.";

function officialLinks(urls) {
  const safe = (urls || []).map((u) => ({ u, s: safeUrl(u) })).filter((x) => x.s);
  if (!safe.length) return h("p", { class: "muted" }, "Official source link unavailable in the catalogue record.");
  return h("ul", { class: "links" }, safe.map(({ s }) => h("li", {},
    h("a", { class: "official", href: s, target: "_blank", rel: "noopener noreferrer" }, "Open official source ↗"),
    h("span", { class: "host" }, " " + new URL(s).hostname))));
}

function list(items, emptyText) {
  return items && items.length ? h("ul", {}, items.map((x) => h("li", {}, x))) : h("p", { class: "muted" }, emptyText);
}

function section(id, title, ...content) {
  return h("section", { class: "card section", id, "aria-labelledby": `${id}-h` }, h("h3", { id: `${id}-h` }, title), ...content);
}

function checklistView(id, cl) {
  const checked = { ...session.checkedFor(id) };
  const status = h("span", { class: "muted", role: "status" });
  const items = cl.items.map((it, i) => h("li", { class: "doc" },
    h("label", {}, h("input", { type: "checkbox", checked: !!checked[i], onchange: (e) => { checked[i] = e.target.checked; session.setChecked(id, i, e.target.checked); } }),
      h("span", { class: "doc-name" }, it.name)),
    h("span", { class: `req ${it.requirement_type}` }, it.label),
    it.notes ? h("p", { class: "doc-notes" }, it.notes) : null));
  const copy = async () => {
    const text = checklistText(cl, checked);
    try { await navigator.clipboard.writeText(text); status.textContent = "Checklist copied."; }
    catch {
      const ta = h("textarea", { class: "sr-only" }, text); document.body.append(ta); ta.select();
      try { document.execCommand("copy"); status.textContent = "Checklist copied."; } catch { status.textContent = "Couldn’t copy automatically; please select the list and copy it."; }
      ta.remove();
    }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([checklistText(cl, checked)], { type: "text/plain;charset=utf-8" }));
    const a = h("a", { href: url, download: `${id}-checklist.txt` }); document.body.append(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };
  return section("documents", "Prepare your documents",
    h("p", { class: "hint" }, cl.disclaimer, " Ticks are saved only in this browser tab. Nothing is uploaded."),
    cl.items.length ? h("ul", { class: "docs" }, items) : h("p", { class: "muted" }, cl.unavailable_message),
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: copy }, "Copy checklist"), h("button", { class: "btn", onclick: download }, "Download checklist"), status));
}

function renderAnswer(data, opts = {}) {
  const wrap = h("div", { class: `msg bot ${data.mode || ""}` });
  if (opts.banner) wrap.append(h("p", { class: "banner info" }, opts.banner));
  if (data.mode === "no_context") wrap.append(h("p", { class: "limit-label" }, "Not verified"));
  if (data.mode === "excerpts") wrap.append(h("p", { class: "limit-label" }, "Source excerpts (not AI-generated advice)"));
  wrap.append(h("p", { class: "answer" }, data.answer));
  if (data.uncertainty_note) wrap.append(h("p", { class: "uncertainty" }, data.uncertainty_note));
  if (data.citations?.length) {
    wrap.append(h("div", { class: "cites" }, h("strong", {}, "Sources"),
      data.citations.map((c) => {
        const link = safeUrl(c.url);
        return h("div", { class: "cite" },
          h("div", {}, c.source_title, c.page_or_section ? ` — ${c.page_or_section}` : ""),
          h("blockquote", {}, c.excerpt),
          link ? h("a", { class: "official", href: link, target: "_blank", rel: "noopener noreferrer" }, "Open official source ↗") : null);
      })));
  }
  if (data.freshness_note) wrap.append(h("p", { class: "muted" }, data.freshness_note));
  if (!data.citations?.length && data.official_source_urls?.length) wrap.append(officialLinks(data.official_source_urls));
  return wrap;
}

function assistant(scheme) {
  const log = h("div", { class: "chat-log", "aria-live": "polite" });
  const input = h("textarea", { rows: 2, maxlength: 2000, placeholder: "Ask about this scheme…", "aria-label": "Your question" });
  const send = h("button", { class: "btn primary", type: "button" }, "Ask");
  const counter = h("span", { class: "muted" }, "0 / 2,000");
  const profile = session.result?.profile_used;
  const profileFields = profile ? Object.fromEntries(["state_ut", "business_type", "ownership_category", "business_stage", "assistance_need"].map((k) => [k, profile[k]])) : undefined;

  async function ask(question) {
    const q = question.trim();
    if (!q) { log.append(h("p", { class: "banner error", role: "alert" }, "Enter a question of up to 2,000 characters.")); return; }
    log.append(h("div", { class: "msg user" }, q));
    const pending = h("div", { class: "msg bot" }, spinner("Looking in the source notes…"));
    log.append(pending);
    send.disabled = true;
    try {
      const data = await api.ask({ question: q, scheme_id: scheme.scheme_id, ...(profileFields ? { profile: profileFields } : {}) });
      pending.replaceWith(renderAnswer(data));
    } catch (err) {
      let node;
      if (err instanceof ApiError && err.code === "ai_not_configured" && err.extra?.fallback) {
        node = renderAnswer(err.extra.fallback, { banner: NOT_CONFIGURED });
      } else {
        const retryable = !(err instanceof ApiError) || err.status >= 500 || err.code === "network";
        node = h("div", { class: "msg bot error" }, h("p", { role: "alert" }, err.message),
          retryable ? h("button", { class: "btn", onclick: () => { node.remove(); ask(q); } }, "Try again") : null, officialLinks(scheme.official_source_urls));
      }
      pending.replaceWith(node);
    } finally { send.disabled = false; log.scrollTop = log.scrollHeight; }
  }
  send.addEventListener("click", () => { const q = input.value; input.value = ""; counter.textContent = "0 / 2,000"; ask(q); });
  input.addEventListener("input", () => { counter.textContent = `${input.value.length.toLocaleString("en-IN")} / 2,000`; });
  return section("assistant", "Ask a question",
    h("p", { class: "hint" }, "Answers come only from the catalogue’s source notes for this scheme, with the source shown. If the notes don’t cover it, we say so."),
    h("div", { class: "chips" }, SUGGESTED.map((s) => h("button", { class: "chip btn-chip", type: "button", onclick: () => ask(s) }, s))),
    log, h("div", { class: "ask-row" }, input, send), counter);
}

export async function renderScheme(root, { id, go }) {
  clear(root).append(h("div", { class: "card" }, spinner("Loading scheme…")));
  let detail, cl;
  try {
    [detail, cl] = await Promise.all([api.scheme(id), api.checklist(id)]);
  } catch (err) {
    clear(root).append(h("div", { class: "card empty" }, h("p", { role: "alert" }, err.message),
      err.status === 404 ? null : h("button", { class: "btn", onclick: () => renderScheme(root, { id, go }) }, "Try again"),
      h("button", { class: "btn primary", onclick: () => go(session.result ? "#/matches" : "#/") }, "Return to recommendations")));
    return;
  }
  const s = detail.scheme;
  const mine = session.result && [...session.result.recommendations, ...session.result.not_likely].find((r) => r.scheme_id === s.scheme_id);
  const rules = (s.eligibility_rules || []);

  clear(root).append(
    h("button", { class: "btn link", onclick: () => go(session.result ? "#/matches" : "#/") }, "← Back to matches"),
    h("div", { class: "card" },
      h("div", { class: "card-head" }, h("h2", {}, s.name),
        mine ? h("span", { class: `badge ${mine.match_status}` }, MATCH_LABELS[mine.match_status]) : null),
      h("p", { class: "meta" }, h("span", { class: "chip" }, s.jurisdiction === "central" ? "Central scheme" : `${s.state_ut} scheme`),
        h("span", { class: `chip status-${s.scheme_status}` }, labelize(s.scheme_status)), s.support_types.map((t) => h("span", { class: "chip alt" }, labelize(t)))),
      h("p", { class: "warning-box" }, "Eligibility and availability must be confirmed with the relevant department or the official portal. A match here is not an eligibility decision."),
      detail.freshness.warnings.map((w) => h("p", { class: "warn" }, "⚠ ", w))),
    section("overview", "Overview", h("p", {}, s.summary), officialLinks(s.official_source_urls)),
    mine ? section("your-match", "How your profile compares",
      h("ul", { class: "reasons" }, mine.reasons.map((r) => h("li", { class: `reason ${r.outcome}` },
        h("span", { class: "reason-mark", "aria-hidden": "true" }, r.outcome === "met" ? "✓" : r.outcome === "not_met" ? "✕" : "?"), r.explanation)))) : null,
    section("qualify", "Who may qualify",
      s.eligible_business_types.length ? h("p", {}, h("strong", {}, "Business activities listed: "), s.eligible_business_types.map(labelize).join(", ")) : null,
      rules.length ? h("ul", {}, rules.map((r) => h("li", {}, r.explanation, r.mandatory ? "" : " (supporting)"))) : null,
      s.conditions_to_confirm.length ? h("div", {}, h("strong", {}, "Also confirm:"), h("ul", {}, s.conditions_to_confirm.map((c) => h("li", {}, c)))) : null,
      !rules.length && !s.eligible_business_types.length && !s.conditions_to_confirm.length ? h("p", { class: "muted" }, "Eligibility details are incomplete in the available source.") : null),
    section("exclude", "Who may not qualify", list(s.exclusions, "Not specified in the available source.")),
    section("benefits", "Benefits", list(s.benefits, "Not specified in the available source.")),
    checklistView(s.scheme_id, cl),
    section("apply", "How to apply", s.application_steps.length ? h("ol", {}, s.application_steps.map((x) => h("li", {}, x))) : h("p", { class: "muted" }, "Not specified in the available source."),
      h("p", { class: "hint" }, "BenefitBridge does not submit applications. Apply only on the official portal or with the lender.")),
    section("source", "Source and freshness",
      h("p", {}, h("strong", {}, "Source: "), s.source_title || "Unavailable"), h("p", {}, h("strong", {}, "Last verified: "), formatDate(s.last_verified_at),
        detail.freshness.needs_reverification ? h("strong", { class: "stale" }, " · Needs re-verification") : null),
      officialLinks(s.official_source_urls), s.review_notes?.length ? h("div", {}, h("strong", {}, "Curator review notes:"), h("ul", {}, s.review_notes.map((n) => h("li", {}, n)))) : null,
      h("p", { class: "hint" }, detail.catalogue_notice)),
    assistant(s));
}
