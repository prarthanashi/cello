// Session-local state. Profiles are never stored on the server; this lives in the browser tab only.
const KEY = "benefitbridge.session.v1";
const blank = () => ({ draft: {}, result: null, checked: {} });
let state = blank();

try {
  const saved = JSON.parse(sessionStorage.getItem(KEY) || "null");
  if (saved && typeof saved === "object") state = { ...blank(), ...saved };
} catch { /* storage unavailable: keep in memory only */ }

function persist() {
  try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch { /* ignore */ }
}

export const session = {
  get draft() { return state.draft; },
  set draft(v) { state.draft = v; persist(); },
  get result() { return state.result; },
  set result(v) { state.result = v; persist(); },
  checkedFor(id) { return state.checked[id] || {}; },
  setChecked(id, idx, val) { state.checked[id] = { ...(state.checked[id] || {}), [idx]: val }; persist(); },
  reset() { state = blank(); try { sessionStorage.removeItem(KEY); } catch { /* ignore */ } },
};
