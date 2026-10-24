// Judges' demo: the live phone on the left, why Maya decided on the right.
import { getModel, getScenarios, rupees, score, signalGroups } from "/static/api.js";
import { REASONS, SIGNAL_NAMES, initialLang, rememberLang, t } from "/static/i18n.js";

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let lang = initialLang();
let scenarios = [], current = null, result = null, model = null, phoneReady = false;
const L = () => t(lang);
const pick = (obj) => (obj && typeof obj === "object" ? obj[lang] ?? obj.en : obj);
const phone = () => $("#phone").contentWindow;
const send = (msg) => phoneReady && phone().postMessage({ maya: true, ...msg }, location.origin);

// --- board ---------------------------------------------------------------------

function resetBoard() {
  result = null;
  $("#story").textContent = pick(current.story);
  $("#prompt").hidden = false;
  const gate = $("#gate");
  gate.classList.remove("reveal");
  gate.dataset.state = "waiting";
  document.querySelectorAll(".group").forEach((g) => {
    g.classList.remove("lit");
    g.querySelector(".state").textContent = "";
    g.querySelector(".facts").innerHTML = "";
  });
  $("#verdict").hidden = true;
  renderPath();
  renderEvidence();
}

function renderBoard(res, { animate = true } = {}) {
  result = res;
  $("#prompt").hidden = true;
  const groups = signalGroups(res);
  const gate = $("#gate");
  gate.classList.remove("reveal");
  gate.dataset.state = "waiting";
  document.querySelectorAll(".group").forEach((g) => g.classList.remove("lit"));
  void gate.offsetWidth;  // restart the sequence
  if (animate) gate.classList.add("reveal");

  for (const name of ["history", "receiving", "phone"]) {
    const el = document.querySelector(`.group[data-group="${name}"]`);
    const keys = groups[name];
    const facts = keys.map((k) => REASONS[lang][k]).filter(Boolean);
    el.classList.toggle("lit", keys.length > 0);
    el.querySelector(".state").textContent = keys.length ? L().risky : L().none_fired;
    el.querySelector(".facts").innerHTML = keys.length ? facts.slice(0, 3).map((f) => `<li>${esc(f)}</li>`).join("") : "";
  }
  gate.dataset.state = res.action;

  const setWord = { "{fine}": L().set_fine, "{scam}": L().set_scam, "{fine, scam}": L().set_unsure }[res.conformal_set];
  $("#model-line").innerHTML = `${esc(L().model_line)}: <strong>${esc(setWord)}</strong> (p = ${res.p_scam.toFixed(3)})`;
  const hard = (groups.history.length > 0) + (groups.receiving.length > 0);
  const rule = res.conformal_set === "{fine}" ? L().rule_fine
    : res.action === "hold" ? L().rule_hold : hard + (groups.phone.length > 0) ? L().rule_one : L().rule_none;
  $("#rule-line").textContent = rule;
  const word = $("#decision");
  word.textContent = L()[`action_${res.action}`];
  word.dataset.action = res.action;
  $("#analyst").textContent = res.requires_analyst ? L().analyst : "";
  $("#speed").textContent = `${Math.max(1, Math.round(res.latency_ms))} ms · model ${res.model_version.slice(0, 8)} · ${res.policy_version}`;
  const verdict = $("#verdict");
  verdict.hidden = false;
  if (animate) {
    verdict.classList.add("pending");
    requestAnimationFrame(() => requestAnimationFrame(() => verdict.classList.remove("pending")));
  }
  renderEvidence();
}

function renderPath() {
  const nodes = current?.money_path;
  $("#path").hidden = !nodes;
  if (!nodes) return;
  $("#path-list").innerHTML = nodes.map((n) => `<li><strong>${esc(pick(n.name))}</strong><span>${esc(pick(n.role))}</span></li>`).join("");
}

// --- tabs ----------------------------------------------------------------------

function renderEvidence() {
  const panel = $("#panel-evidence");
  const contributions = result?.explanation?.contributions;
  if (!contributions) { panel.innerHTML = `<p>${esc(L().no_evidence)}</p>`; return; }
  const max = Math.max(...contributions.map((c) => Math.abs(c.shap)), 1e-9);
  const side = (f) => f.endsWith("_snd") ? (lang === "hi" ? "भेजने वाला" : "payer")
    : f.endsWith("_rcv") ? (lang === "hi" ? "पाने वाला" : "payee") : (lang === "hi" ? "मिलाकर" : "combined");
  const fmt = (v) => v === null ? "—" : Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
  const TOP = 10;  // the strongest contributions first; the rest on request
  const showAll = panel.dataset.all === "1";
  const moreLabel = showAll
    ? (lang === "hi" ? `सबसे असरदार ${TOP} दिखाएँ` : `Show the strongest ${TOP}`)
    : (lang === "hi" ? `सभी ${contributions.length} संकेत दिखाएँ` : `Show all ${contributions.length} signals`);
  panel.innerHTML = `<table class="evidence"><thead><tr>
      <th>${esc(L().feature)}</th><th></th><th class="num">${esc(L().value)}</th><th>${esc(L().effect)}</th><th>${esc(L().risky)}</th>
    </tr></thead><tbody>${contributions.slice(0, showAll ? undefined : TOP).map((c) => {
      const base = c.feature.replace(/_(snd|rcv)$/, "");
      const w = (Math.abs(c.shap) / max) * 50;
      return `<tr class="${c.risky ? "risky" : ""}"><td>${esc(SIGNAL_NAMES[lang][base] ?? base)}</td>
        <td class="side">${esc(side(c.feature))}</td><td class="num">${esc(fmt(c.value))}</td>
        <td><div class="bar" title="${c.shap.toFixed(4)}"><span class="${c.shap > 0 ? "up" : "down"}" style="width:${w.toFixed(1)}%"></span></div></td>
        <td>${c.risky ? `<span class="flag">✓</span><span class="visually-hidden">${esc(L().risky)}</span>` : ""}</td></tr>`;
    }).join("")}</tbody></table>
    <button type="button" class="text-toggle" id="evidence-more" aria-expanded="${showAll}">${esc(moreLabel)}</button>
    <p>${lang === "hi" ? "लाल पट्टी स्कोर को धोखाधड़ी की ओर ले जाती है, हरी उससे दूर। यह धोखाधड़ी का सबूत नहीं है।"
      : "Red pushes the score towards scam, green away from it. A contribution explains the score; it is not proof of fraud."}</p>`;
}

function renderRobust() {
  const panel = $("#panel-robust");
  const a = model?.attacks;
  if (!a) { panel.innerHTML = `<p>${esc(L().robust_missing)}</p>`; return; }
  const names = {
    en: { split_2: "Split into 2 payments", split_4: "Split into 4 payments", split_10: "Split into 10 payments",
          extra_hop: "One more mule account", no_probes: "No tiny test payments", all: "Split + extra mule + no tests" },
    hi: { split_2: "2 भुगतानों में बाँटा", split_4: "4 भुगतानों में बाँटा", split_10: "10 भुगतानों में बाँटा",
          extra_hop: "एक और म्यूल खाता", no_probes: "कोई परीक्षण भुगतान नहीं", all: "बाँटना + म्यूल + कोई परीक्षण नहीं" },
  }[lang];
  const pct = (x) => `${(x * 100).toFixed(1)}%`;
  panel.innerHTML = `<p>${esc(L().robust_intro)}</p>
    <table class="robust"><thead><tr><th>${esc(L().attack)}</th><th class="num">${esc(L().caught)}</th><th class="num">${esc(L().change)}</th><th></th></tr></thead>
    <tbody><tr><td>${lang === "hi" ? "कोई हमला नहीं" : "No attack"}</td><td class="num">${pct(a.baseline_catch_rate)}</td><td class="num">—</td><td></td></tr>
    ${a.attacks.map((r) => `<tr><td>${esc(names[r.name] ?? r.name)}</td><td class="num">${pct(r.catch_rate)}</td>
      <td class="num">${r.drop_pts > 0 ? "−" : "+"}${Math.abs(r.drop_pts).toFixed(1)} pts</td>
      <td class="tag">${r.held_out_of_training ? esc(L().held_out) : ""}</td></tr>`).join("")}</tbody></table>
    <p>${lang === "hi" ? `${a.n_scams} टेस्ट धोखाधड़ी, सिंथेटिक डेटा।` : `${a.n_scams} test scams, synthetic data.`}</p>`;
}

function renderModelCard() {
  const panel = $("#panel-model");
  if (!model) { panel.innerHTML = `<p>${esc(L().error_models)}</p>`; return; }
  const m = model.metrics ?? {};
  const row = (k, v) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`;
  panel.innerHTML = `<div class="card-grid">
    <div><h2>${lang === "hi" ? "मॉडल" : "Model"}</h2><dl>
      ${row("XGBoost", `${model.feature_contract.columns.length} ${lang === "hi" ? "संकेत" : "signals"}`)}
      ${row("Test AUROC", m.test_auroc?.toFixed(4) ?? "—")}
      ${row("Test AUPRC", m.test_auprc?.toFixed(4) ?? "—")}
      ${row(lang === "hi" ? "1% झूठी चेतावनी पर पकड़" : "Caught at 1% false alarms", m.test_recall_at_1pct_fpr ? `${(m.test_recall_at_1pct_fpr * 100).toFixed(1)}%` : "—")}
      ${row(lang === "hi" ? "विरोधी प्रशिक्षण" : "Adversarial training", (m.adversarial_attacks ?? []).join(", ") || "—")}
    </dl></div>
    <div><h2>${lang === "hi" ? "नियम" : "Rules"}</h2><dl>
      ${row(lang === "hi" ? "सामान्य, अगर p ≤" : "Normal if p ≤", model.conformal.fine_if_p_at_most.toFixed(5))}
      ${row(lang === "hi" ? "धोखाधड़ी, अगर p ≥" : "Scam if p ≥", model.conformal.scam_if_p_at_least.toFixed(4))}
      ${row(lang === "hi" ? "रोकने के लिए" : "To hold", lang === "hi" ? "दो स्वतंत्र समूह" : "two independent groups")}
      ${row(lang === "hi" ? "समय सीमा" : "Latency budget", `${model.latency_slo_ms} ms`)}
      ${row(lang === "hi" ? "संस्करण" : "Version", `${model.model_version.slice(0, 8)} · ${model.policy_version}`)}
    </dl></div>
    <div><h2>${esc(L().limits_title)}</h2><ul class="limits">${L().limits.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
  </div>`;
}

// --- try it --------------------------------------------------------------------

const SLIDERS = [
  { key: "amount", min: 1000, max: 500000, step: 1000, value: 50000 },
  { key: "n_t", min: 0, max: 100, step: 1, value: 56 },
  { key: "e_t", min: 0, max: 8, step: 0.01, value: 0.01 },
  { key: "z_t", min: -2, max: 9, step: 0.1, value: 0 },
  { key: "pi_t", min: 0, max: 5, step: 1, value: 0 },
  { key: "d_R", min: 0, max: 3, step: 1, value: 2 },
  { key: "v_t", min: 0, max: 20, step: 1, value: 0 },
  { key: "ptr_t", min: 0, max: 1.5, step: 0.05, value: 0.4 },
];

function renderSliders() {
  const box = $("#sliders");
  const prev = Object.fromEntries([...box.querySelectorAll("input")].map((i) => [i.name, i.value]));
  box.innerHTML = SLIDERS.map((s) => {
    const label = s.key === "amount" ? L().amount : SIGNAL_NAMES[lang][s.key];
    const v = prev[s.key] ?? s.value;
    return `<label><span>${esc(label)} <output id="out-${s.key}">${esc(v)}</output></span>
      <input type="range" name="${s.key}" min="${s.min}" max="${s.max}" step="${s.step}" value="${v}"></label>`;
  }).join("");
}

$("#sliders").addEventListener("input", (e) => {
  if (e.target.matches("input[type=range]")) $(`#out-${e.target.name}`).textContent = e.target.value;
});

$("#try-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const v = (k) => Number(f.get(k));
  // The 9 base signals mirrored onto payer and payee sides (an approximation),
  // earlier same-payee payments assumed to be the same size as this one.
  const base = { n_t: v("n_t"), e_t: v("e_t"), g_t: 1, z_t: v("z_t"), pi_t: v("pi_t"), d_R: v("d_R"),
                 v_t: v("v_t"), zc_t: v("z_t") + Math.log1p(v("v_t")), ptr_t: v("ptr_t") };
  const features = {};
  for (const [k, x] of Object.entries(base)) { features[k] = x; features[`${k}_snd`] = x; features[`${k}_rcv`] = x; }
  const soft_signals = { is_screen_shared: f.has("is_screen_shared"), is_voice_active: f.has("is_voice_active"),
                         chat_stage: f.has("chat_demand") ? "payment_demand" : "none" };
  try {
    const res = await score({ features, amount_inr: v("amount"), soft_signals }, true);
    $("#story").textContent = lang === "hi" ? `आपका भुगतान: ${rupees(v("amount"))}` : `Your payment: ${rupees(v("amount"))}`;
    $("#path").hidden = true;
    renderBoard(res);
    $("#story").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  } catch (err) {
    $("#rule-line").textContent = err.message;
  }
});

// --- tabs behaviour (ARIA tabs with arrow keys) ---------------------------------

const tabs = [...document.querySelectorAll('[role="tab"]')];
function selectTab(tab) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
  }
  tab.focus();
}
tabs.forEach((tab, i) => {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (e) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (d) { e.preventDefault(); selectTab(tabs[(i + d + tabs.length) % tabs.length]); }
  });
});

// --- scenarios, language, phone link ------------------------------------------------

function renderScenarioBar() {
  $("#scenario-bar").innerHTML = scenarios.map((s) =>
    `<button type="button" data-key="${esc(s.key)}" aria-pressed="${s.key === current?.key}">${esc(pick(s.label))}<small>${esc(rupees(s.amount_inr))}</small></button>`).join("");
}

function choose(key) {
  current = scenarios.find((s) => s.key === key) ?? scenarios[0];
  renderScenarioBar();
  resetBoard();
  send({ type: "load", key: current.key });
}

function setLang(next, { tellPhone = true } = {}) {
  lang = next;
  rememberLang(lang);
  document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
  document.querySelectorAll("[data-i18n]").forEach((el) => { const s = L()[el.dataset.i18n]; if (typeof s === "string") el.textContent = s; });
  if (current) { renderScenarioBar(); $("#story").textContent = pick(current.story); renderPath(); }
  if (result) renderBoard(result, { animate: false }); else renderEvidence();
  renderRobust(); renderModelCard(); renderSliders();
  if (tellPhone) send({ type: "lang", lang });
}

document.addEventListener("click", (e) => {
  if (e.target.closest("#evidence-more")) {
    const panel = $("#panel-evidence");
    panel.dataset.all = panel.dataset.all === "1" ? "0" : "1";
    renderEvidence();
    $("#evidence-more").focus();
    return;
  }
  const sc = e.target.closest("#scenario-bar [data-key]");
  if (sc) choose(sc.dataset.key);
  const lb = e.target.closest("[data-lang]");
  if (lb) setLang(lb.dataset.lang);
});

window.addEventListener("message", (e) => {
  if (e.origin !== location.origin || !e.data?.maya) return;
  if (e.data.type === "loaded") {
    if (!phoneReady) { phoneReady = true; send({ type: "lang", lang }); if (current && e.data.key !== current.key) send({ type: "load", key: current.key }); }
  }
  if (e.data.type === "decision" && e.data.key === current?.key) {
    $("#story").textContent = pick(current.story);
    renderPath();
    renderBoard(e.data.result);
  }
  if (e.data.type === "lang" && e.data.lang !== lang) setLang(e.data.lang, { tellPhone: false });
});

(async function start() {
  try {
    [scenarios, model] = await Promise.all([getScenarios(), getModel().catch(() => null)]);
  } catch {
    $("#story").textContent = L().error_network;
    return;
  }
  current = scenarios.find((s) => s.key === "investment") ?? scenarios[0];
  setLang(lang, { tellPhone: false });
  choose(current.key);
})();
