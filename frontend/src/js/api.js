// All backend access. The frontend never calls an AI provider; it only calls the BenefitBridge API.
const BASE = (globalThis.BENEFITBRIDGE_API_BASE ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(code, message, status = 0, fields = null, extra = null) {
    super(message);
    this.code = code; this.status = status; this.fields = fields; this.extra = extra;
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      ...options,
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) },
    });
  } catch {
    // E16
    throw new ApiError("network", "We couldn’t connect to the service. Check your connection and try again.");
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok) {
    const e = data?.error;
    throw new ApiError(e?.code || "http_error", e?.message || "Something went wrong. Please try again.", res.status, e?.fields || null, data);
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  options: () => request("/api/meta/options"),
  demoProfile: () => request("/api/demo/profile"),
  match: (profile) => request("/api/eligibility/match", { method: "POST", body: JSON.stringify(profile) }),
  scheme: (id) => request(`/api/schemes/${encodeURIComponent(id)}`),
  checklist: (id) => request(`/api/schemes/${encodeURIComponent(id)}/checklist`),
  ask: (body) => request("/api/assistant/ask", { method: "POST", body: JSON.stringify(body) }),
};
