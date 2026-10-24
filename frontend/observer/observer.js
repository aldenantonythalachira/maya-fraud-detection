const $ = (s) => document.querySelector(s),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const money = (p) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    p / 100,
  );
let data = null,
  selected = null,
  stream = null,
  stages = [],
  busy = false,
  refreshTimer = null;
let followLatest = true,
  activePayment = null,
  activeEvaluation = null;
async function api(url, body) {
  const r = await fetch(url, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(10000),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || "Unable to connect");
  return d;
}
function fail(e) {
  $("#error").hidden = false;
  $("#error").textContent = e.message;
}
$("#pair-form").onsubmit = async (e) => {
  e.preventDefault();
  try {
    await api("/v1/observe/pair", { code: $("#code").value.trim() });
    sessionStorage.removeItem("maya-v4-event-cursor");
    stages = [];
    selected = null;
    await connect();
  } catch (e) {
    fail(e);
  }
};
async function refresh() {
  if (busy) return;
  busy = true;
  try {
    data = await api("/v1/observe");
    $("#pairing").hidden = true;
    $("#dashboard").hidden = false;
    $("#error").hidden = true;
    if (data.role === "recipient") {
      renderRecipient();
      return;
    }
    selected =
      (followLatest
        ? data.reviews[0]
        : data.reviews.find((r) => r.id === selected?.id)) ||
      data.reviews[0] ||
      null;
    render();
  } catch (e) {
    $("#connection").textContent = "Access unavailable";
    stream?.close();
    fail(e);
  } finally {
    busy = false;
  }
}
async function connect() {
  while (busy) await new Promise((r) => setTimeout(r, 20));
  await refresh();
  if (!data) return;
  if (data.role === "judge") {
    stream?.close();
    const cursor = sessionStorage.getItem("maya-v4-event-cursor") || "0";
    stream = new EventSource(
      "/v1/observe/events?after=" + encodeURIComponent(cursor),
    );
    stream.onopen = () => {
      $("#connection").textContent = "Connected · live";
    };
    stream.onmessage = (e) => {
      const event = JSON.parse(e.data);
      sessionStorage.setItem("maya-v4-event-cursor", e.lastEventId);
      stages.push(event);
      if (stages.length > 300) stages.shift();
      if (event.stage === "intent_validated") {
        followLatest = true;
        activePayment = event.payment_id;
        activeEvaluation = null;
      }
      if (followLatest && event.evaluation_id) {
        activePayment = event.payment_id;
        activeEvaluation = event.evaluation_id;
      }
      renderStages();
      if (
        [
          "review_saved",
          "settled",
          "cancelled",
          "intent_validated",
          "review_failed",
        ].includes(event.stage)
      ) {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(refresh, 80);
      }
    };
    stream.onerror = () => {
      $("#connection").textContent = "Reconnecting…";
    };
  } else {
    $("#connection").textContent = "Connected · recipient";
    refreshTimer = setInterval(refresh, 2000);
  }
}
const labels = {
  intent_validated: "Input and validation",
  history_loaded: "Available evidence",
  features_computed: "Feature computation",
  model_scored: "Model inference",
  uncertainty_computed: "Uncertainty",
  policy_evaluated: "Policy",
  review_saved: "Durable review",
  settled: "Confirmed transfer",
  review_failed: "Review failed",
};
function renderStages() {
  if (data?.role !== "judge") return;
  const current = followLatest
    ? activeEvaluation || selected?.id
    : selected?.id;
  const payment = followLatest
    ? activePayment || selected?.payment_id
    : selected?.payment_id;
  const applicable = stages.filter((e) =>
    e.evaluation_id ? e.evaluation_id === current : e.payment_id === payment,
  );
  const defaults = [
    "intent_validated",
    "history_loaded",
    "features_computed",
    "model_scored",
    "uncertainty_computed",
    "policy_evaluated",
    "review_saved",
  ];
  $("#stages").innerHTML = defaults
    .map((k) => {
      const ev = applicable.findLast((e) => e.stage === k);
      const key = {
        history_loaded: "history_loaded",
        features_computed: "features_computed",
        model_scored: "model_scored",
        uncertainty_computed: "uncertainty_computed",
        policy_evaluated: "policy_evaluated",
      }[k];
      const historical = selected?.id === current;
      const measured =
        ev?.duration_ms ?? (historical ? selected?.timings_ms[key] : undefined);
      const done =
        !!ev || (historical && !!selected && k !== "intent_validated");
      return `<div class="stage ${done ? "done" : ""}"><span>${esc(labels[k])}</span><span class="number">${measured !== undefined ? esc(measured.toFixed(2)) + " ms" : done ? "Committed" : "Waiting"}</span></div>`;
    })
    .join("");
  const terminal = applicable.findLast(
    (e) => e.stage === "review_failed" || e.stage === "settled",
  );
  if (terminal)
    $("#stages").insertAdjacentHTML(
      "beforeend",
      `<div class="stage ${terminal.stage === "review_failed" ? "failed" : "done"}"><strong>${esc(labels[terminal.stage])}</strong><span>${esc(terminal.status || "Committed")}</span></div>`,
    );
}
function render() {
  if (!selected) {
    $("#summary").innerHTML = "<h2>A customer can now create a payment.</h2>";
    $("#evidence").textContent = "No review yet.";
    renderStages();
    return;
  }
  $("#headline").textContent = "One payment. Every decision visible.";
  const r = selected,
    a = r.decision.action;
  const transfer = data.transfers.find((t) => t.review_id === r.id);
  $("#summary").innerHTML =
    `<span class="pill ${a}">${esc(a.toUpperCase())}</span><p class="amount">${esc(money(r.amount_paise))}</p><p>Recipient #${esc(r.recipient)} · revision ${esc(r.revision)}</p><p>${transfer ? "<strong>Confirmed sandbox transfer</strong>" : "Review complete · no confirmed transfer for this review"}</p><small class="number">${esc(r.id)}</small>`;
  $("#evidence").innerHTML =
    `<ul class="reasons">${r.decision.reasons.map((s) => `<li>${esc(s)}</li>`).join("")}</ul><p>Prediction set: <strong>${esc(r.model.uncertainty)}</strong></p><p>Model score: <strong>${Number(r.model.score).toFixed(4)}</strong></p><p class="muted">${esc(r.graph_convention)}</p><p>Groups: ${Object.entries(
      r.groups,
    )
      .map(([k, v]) => esc(k) + ": " + (v ? "present" : "absent"))
      .join(" · ")}</p>`;
  $("#history").innerHTML = data.reviews
    .map(
      (x) =>
        `<button class="quiet" data-review="${esc(x.id)}">${esc(money(x.amount_paise))} · ${esc(x.decision.action)} · ${esc(x.id.slice(0, 6))}</button>`,
    )
    .join("");
  document.querySelectorAll("[data-review]").forEach(
    (b) =>
      (b.onclick = () => {
        followLatest = false;
        selected = data.reviews.find((x) => x.id === b.dataset.review);
        render();
      }),
  );
  $("#model").innerHTML = Object.entries(r.versions)
    .map(
      ([k, v]) =>
        `<p><strong>${esc(k)}</strong><br><small>${esc(v)}</small></p>`,
    )
    .join("");
  $("#features").innerHTML =
    `<table class="feature-table"><thead><tr><th>Feature</th><th>Value</th><th>SHAP, log-odds</th></tr></thead><tbody>${Object.entries(
      r.features,
    )
      .map(([k, v]) => {
        const c = r.model.contributions?.find((c) => c.feature === k);
        return `<tr><td>${esc(k)}</td><td>${v === null ? "Missing" : Number(v).toFixed(4)}</td><td>${c ? Number(c.value).toFixed(4) : "Unavailable"}</td></tr>`;
      })
      .join("")}</tbody></table>`;
  renderStages();
  renderGraph();
}
function renderRecipient() {
  const main = $("#dashboard");
  main.innerHTML = `<span class="pill sandbox">SANDBOX · DUMMY MONEY</span><h1>${esc(data.recipient)}</h1><p class="muted">Current dummy balance</p><p class="amount">${esc(money(data.balance_paise))}</p><h2>Confirmed incoming payments</h2>${data.transfers.length ? data.transfers.map((t) => `<section class="card"><span class="pill release">Confirmed</span><h2>${esc(money(t.amount_paise))}</h2><p class="muted">${esc(t.id)}</p></section>`).join("") : "<p>Waiting for an incoming payment.</p>"}`;
}
function renderGraph() {
  const svg = $("#graph");
  svg.replaceChildren();
  const edges = selected.graph || [],
    nodes = [...new Set(edges.flatMap((e) => [e.source, e.target]))].slice(
      0,
      14,
    ),
    ns = "http://www.w3.org/2000/svg";
  const positions = new Map(
    nodes.map((n, i) => [
      n,
      {
        x: 300 + 220 * Math.cos((2 * Math.PI * i) / nodes.length),
        y: 110 + 80 * Math.sin((2 * Math.PI * i) / nodes.length),
      },
    ]),
  );
  for (const e of edges) {
    const a = positions.get(e.source),
      b = positions.get(e.target);
    if (!a || !b) continue;
    const line = document.createElementNS(ns, "line");
    for (const [k, v] of Object.entries({ x1: a.x, y1: a.y, x2: b.x, y2: b.y }))
      line.setAttribute(k, v);
    svg.append(line);
  }
  for (const [n, p] of positions) {
    const circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", p.x);
    circle.setAttribute("cy", p.y);
    circle.setAttribute("r", "17");
    const text = document.createElementNS(ns, "text");
    text.setAttribute("x", p.x);
    text.setAttribute("y", p.y + 4);
    text.textContent = String(n);
    svg.append(circle, text);
  }
}
$("#refresh").onclick = refresh;
$("#export").onclick = () => {
  if (!selected) return;
  const u = URL.createObjectURL(
    new Blob([JSON.stringify(selected, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = u;
  a.download = `maya-review-${selected.id}.json`;
  a.click();
  URL.revokeObjectURL(u);
};
window.addEventListener("pagehide", () => {
  stream?.close();
  clearInterval(refreshTimer);
});
const evidenceLink = document.createElement("a");
evidenceLink.href = "/demo/benchmarks.html";
evidenceLink.textContent = "Validation evidence";
document.querySelector(".header").append(evidenceLink);
connect().catch(() => {});
