// Small client for the Maya API, shared by /app and /demo.

export async function api(path, body) {
  const options = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  options.signal = AbortSignal.timeout(10000);
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("network");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
    err.status = response.status;
    throw err;
  }
  return data;
}

export const getScenarios = () => api("/v1/demo/scenarios");
export const getModel = () => api("/v1/model");

/** Score a scenario (or any feature row) through the hot path. */
export function score({ features, amount_inr, soft_signals, mulehunter_status }, explain = false) {
  return api("/v1/score", { features, amount_inr, soft_signals, mulehunter_status: mulehunter_status ?? null, explain });
}

/** ₹ with Indian digit grouping: 196538.18 -> ₹1,96,538 */
export function rupees(amount, { paise = false } = {}) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency", currency: "INR",
    minimumFractionDigits: paise ? 2 : 0, maximumFractionDigits: paise ? 2 : 0,
  }).format(amount);
}

export const PAYMENT_HISTORY = ["n_t", "e_t", "z_t", "zc_t", "pi_t"];
export const RECEIVING = ["d_R", "mulehunter"];

/** Which of the three signal groups fired, from a /v1/score response. */
export function signalGroups(result) {
  const hard = result.fired_signals?.hard ?? {};
  const soft = result.fired_signals?.soft ?? {};
  return {
    history: PAYMENT_HISTORY.filter((k) => hard[k]),
    receiving: RECEIVING.filter((k) => hard[k]),
    phone: Object.keys(soft).filter((k) => soft[k]),
  };
}
