import { api, ApiError } from "./api.js";
import { clear, h } from "./dom.js";
import { renderMatches } from "./views/matches.js";
import { renderProfile } from "./views/profile.js";
import { renderScheme } from "./views/scheme.js";
import { session } from "./state.js";
import { isValidSchemeId } from "./util.js";

const STEPS = ["Build your profile", "Explore matches", "Understand a scheme", "Prepare documents", "Ask a question"];
const view = document.getElementById("view");
const stepper = document.getElementById("stepper");
const statusBox = document.getElementById("status");
let options = null;

const go = (hash) => { if (location.hash === hash) route(); else location.hash = hash; };

function drawStepper(current, schemeSections = false) {
  clear(stepper);
  STEPS.forEach((label, i) => {
    const n = i + 1;
    const reachable = n === 1 || (n === 2 && session.result) || (n >= 3 && schemeSections);
    const attrs = { class: `step${n === current ? " current" : ""}${n < current ? " done" : ""}`, ...(n === current ? { "aria-current": "step" } : {}) };
    const onclick = () => {
      if (n === 1) go("#/"); else if (n === 2) go("#/matches");
      else if (n === 4) document.getElementById("documents")?.scrollIntoView({ behavior: "smooth" });
      else if (n === 5) document.getElementById("assistant")?.scrollIntoView({ behavior: "smooth" });
      else window.scrollTo({ top: 0, behavior: "smooth" });
    };
    stepper.append(h("li", attrs, h("button", { type: "button", disabled: !reachable, onclick }, h("span", { class: "num" }, n), h("span", { class: "lbl" }, label))));
  });
}

async function refreshStatus() {
  clear(statusBox);
  try {
    const hl = await api.health();
    statusBox.append(h("span", { class: "pill ok" }, "Backend connected"),
      h("span", { class: `pill ${hl.ai_configured ? "ok" : "off"}` }, hl.ai_configured ? "AI answers on" : "AI not configured (demo mode)"),
      h("span", { class: "pill" }, `${hl.catalogue_count} schemes in catalogue`));
  } catch {
    statusBox.append(h("span", { class: "pill bad" }, "Backend unavailable"),
      h("button", { class: "btn link", onclick: refreshStatus }, "Retry"));
  }
}

async function ensureOptions() {
  if (options) return options;
  options = await api.options();
  return options;
}

async function route() {
  const hash = location.hash || "#/";
  window.scrollTo(0, 0);
  try {
    if (hash.startsWith("#/scheme/")) {
      const id = decodeURIComponent(hash.slice("#/scheme/".length));
      drawStepper(3, true);
      if (!isValidSchemeId(id)) { clear(view).append(h("div", { class: "card empty" }, h("p", {}, "We couldn’t find that scheme. Return to recommendations."), h("button", { class: "btn primary", onclick: () => go("#/matches") }, "Return"))); return; }
      await renderScheme(view, { id, go });
    } else if (hash === "#/matches") {
      drawStepper(2);
      renderMatches(view, { go });
    } else {
      drawStepper(1);
      renderProfile(view, { options: await ensureOptions(), go });
    }
  } catch (err) {
    clear(view).append(h("div", { class: "card empty" }, h("p", { role: "alert" }, err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
      h("button", { class: "btn primary", onclick: () => { refreshStatus(); route(); } }, "Try again")));
  }
}

window.addEventListener("hashchange", route);
refreshStatus();
route();
