// Everyday-user app: one payment, checked by Maya before it leaves.
import { getScenarios, rupees, score, signalGroups } from "/static/api.js";
import { REASONS, initialLang, rememberLang, t } from "/static/i18n.js";

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const params = new URLSearchParams(location.search);
const EMBEDDED = params.get("embed") === "1";
const MIN_CHECK_MS = 700;  // let the dot visibly travel before the answer lands

let lang = initialLang();
let scenarios = [];
let current = null;        // scenario object from /v1/demo/scenarios
let result = null;         // last /v1/score response
let view = "pay";          // pay | checking | outcome | nudge-yes | calling | cancelled | sent | error
let errorKind = "network";
let confirmedAfterWarning = false;
let timer = null, holdEndsAt = 0;

if (EMBEDDED) document.body.classList.add("embedded");

// --- helpers -------------------------------------------------------------------

const L = () => t(lang);
const pick = (obj) => (obj && typeof obj === "object" ? obj[lang] ?? obj.en : obj);
const money = (amt) => rupees(amt);
// From the English name (Devanagari letters can't be split into initials):
// first and last word, ignoring "(…)" and abbreviations like "R.".
const initials = (payee) => {
  const words = String(payee?.en ?? payee).replace(/\(.*?\)/g, "").trim().split(/\s+/).filter((w) => !w.endsWith("."));
  return (words.length > 1 ? words[0][0] + words[words.length - 1][0] : words[0]?.[0] ?? "?").toUpperCase();
};

function amountMarkup(amt) {
  const text = money(amt);
  return `<span class="sym" aria-hidden="true">₹</span>${esc(text.replace("₹", ""))}<span class="visually-hidden"> rupees</span>`;
}

/** Plain-language reasons: model reasons first, then the phone's own signals. */
function reasonList() {
  const groups = signalGroups(result);
  const keys = [...(result.reason_features ?? [])];
  if (groups.receiving.includes("mulehunter")) keys.push("mulehunter");
  for (const k of groups.phone) keys.push(k);
  return [...new Set(keys)].map((k) => REASONS[lang][k]).filter(Boolean).slice(0, 4);
}

function phoneSignals() {
  const soft = current?.soft_signals ?? {};
  const items = [];
  if (soft.is_screen_shared) items.push(L().phone_screen);
  if (soft.is_voice_active) items.push(L().phone_voice);
  if (soft.chat_stage === "payment_demand" || soft.chat_stage === "escalated") items.push(L().phone_chat);
  return items;
}

function stopTimer() { if (timer) { clearInterval(timer); timer = null; } }

function tick() {
  const el = $("#timer");
  if (!el) return stopTimer();
  const left = Math.max(0, holdEndsAt - Date.now());
  const m = Math.floor(left / 60000), s = Math.floor((left % 60000) / 1000);
  el.textContent = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function post(message) {
  if (EMBEDDED && window.parent !== window) window.parent.postMessage({ maya: true, ...message }, location.origin);
}

// --- rendering --------------------------------------------------------------------

function flight(state) {
  const label = view === "checking" ? L().checking : "";
  return `<div class="flight" data-state="${state}" aria-hidden="true">
      <span class="end">${lang === "hi" ? "आप" : "You"}</span>
      <div class="track"><span class="run"></span><span class="dot"></span></div>
      <span class="end">${esc(initials(current.payee))}</span>
      <span class="checking-label">${esc(label)}</span>
    </div>`;
}

function header() {
  return `<div class="payee">
      <div class="avatar" aria-hidden="true">${esc(initials(current.payee))}</div>
      <div><p class="payee-label">${esc(L().paying)}</p>
        <p class="payee-name">${esc(pick(current.payee))}</p>
        <p class="payee-upi">${esc(current.upi)}</p></div>
    </div>
    <p class="amount">${amountMarkup(current.amount_inr)}</p>
    <p class="note">${esc(pick(current.note))}</p>
    <p class="from">${esc(L().from_account)}</p>`;
}

function outcomePanel() {
  const a = result.action;
  const why = reasonList();
  const whyBlock = why.length
    ? `<div class="why"><h3>${esc(L().why)}</h3><ul>${why.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>` : "";
  if (a === "hold") {
    return `<section class="outcome hold" aria-labelledby="o-title">
        <h2 id="o-title">${esc(L().hold_title)}</h2>
        <time class="timer" id="timer" role="timer" aria-live="off">60:00</time>
        <p>${esc(L().hold_body)}</p>
        ${result.requires_analyst ? `<p class="analyst">${esc(L().hold_analyst)}</p>` : `<p>${esc(L().hold_auto)}</p>`}
        ${whyBlock}
        <p class="helpline">${esc(L().helpline).replace("1930", '<a href="tel:1930">1930</a>')}</p>
      </section>
      <div class="actions">
        <button class="primary" data-act="call">${esc(L().call_trusted)}</button>
        <button class="secondary" data-act="cancel">${esc(L().cancel_payment)}</button>
      </div>`;
  }
  if (a === "nudge") {
    return `<section class="outcome nudge" aria-labelledby="o-title">
        <h2 id="o-title">${esc(L().nudge_title)}</h2>
        <p class="question">${esc(L().nudge_question)}</p>
        ${whyBlock}
      </section>
      <div class="actions">
        <button class="primary" data-act="yes">${esc(L().nudge_yes)}</button>
        <button class="secondary" data-act="no">${esc(L().nudge_no)}</button>
      </div>`;
  }
  return "";  // release goes straight to the receipt
}

function receipt() {
  const ref = (result?.request_id ?? "").replace(/[^0-9a-f]/gi, "").slice(0, 12).toUpperCase();
  const when = new Date().toLocaleString(lang === "hi" ? "hi-IN" : "en-IN",
    { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" });
  return `<section class="receipt" aria-labelledby="r-title">
      <div class="tick" aria-hidden="true"><svg viewBox="0 0 24 24" width="34" height="34"><path d="M5 12.5 10 17l9-10" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      <h2 id="r-title">${esc(L().sent_title(money(current.amount_inr), pick(current.payee)))}</h2>
      <dl>
        <div><dt>${lang === "hi" ? "समय" : "When"}</dt><dd>${esc(when)}</dd></div>
        <div><dt>UPI ID</dt><dd>${esc(current.upi)}</dd></div>
        <div><dt>${esc(L().ref)}</dt><dd>${esc(ref)}</dd></div>
      </dl>
      <p class="checked">${esc(confirmedAfterWarning ? L().sent_after_warning : L().sent_checked(Math.max(1, Math.round(result?.latency_ms ?? 0))))}</p>
    </section>
    <div class="actions"><button class="secondary" data-act="restart">${esc(L().start_over)}</button></div>`;
}

function render() {
  const screen = $("#screen");
  const status = $("#phone-status");
  const signals = current ? phoneSignals() : [];
  status.hidden = !signals.length || view === "sent" || view === "cancelled";
  status.innerHTML = signals.map((s) => `<li>${esc(s)}</li>`).join("");

  if (view === "error") {
    stopTimer();
    screen.innerHTML = `<section class="outcome neutral" role="alert"><h2>${esc(L().error_title)}</h2>
      <p>${esc(errorKind === "models" ? L().error_models : L().error_network)}</p></section>`;
    return;
  }
  if (!current) return;
  if (view === "sent") { stopTimer(); screen.innerHTML = receipt(); return; }
  if (view === "cancelled") {
    stopTimer();
    screen.innerHTML = `<section class="outcome neutral" aria-labelledby="c-title"><h2 id="c-title">${esc(L().cancelled_title)}</h2>
      <p>${esc(L().cancelled_body)}</p></section>
      <div class="actions"><button class="secondary" data-act="restart">${esc(L().start_over)}</button></div>`;
    return;
  }
  if (view === "calling") {
    screen.innerHTML = `<section class="calling" aria-live="polite"><div class="ring" aria-hidden="true">P</div>
      <h2>${esc(L().calling)}</h2><p class="helpline">${esc(L().calling_body)}</p></section>
      <div class="actions"><button class="secondary" data-act="end-call">${esc(L().end_call)}</button></div>`;
    return;
  }
  if (view === "nudge-yes") {
    screen.innerHTML = header() + `<section class="outcome hold" role="alert"><h2>${esc(L().nudge_title)}</h2>
      <p>${esc(L().nudge_stop).replace("1930", '<a href="tel:1930">1930</a>')}</p></section>
      <div class="actions"><button class="primary" data-act="cancel">${esc(L().cancel_payment)}</button>
      <a class="secondary" href="tel:1930">1930</a></div>`;
    return;
  }

  const state = view === "checking" ? "checking" : view === "outcome" ? result.action : "idle";
  const body = view === "pay" || view === "checking"
    ? `<div class="actions"><button class="primary" data-act="pay" ${view === "checking" ? "disabled" : ""}>${esc(L().pay(money(current.amount_inr)))}</button></div>`
    : outcomePanel();
  // The line is created where it was, then moved on the next frame, so the dot
  // visibly travels: idle -> checking on Pay, checking -> outcome on the answer.
  screen.innerHTML = header() + flight(view === "outcome" ? "checking" : "idle") + body;
  if (state !== "idle" && state !== "checking") {
    // next frame: move the dot from "checking" to its outcome position
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const f = screen.querySelector(".flight");
      if (f) f.dataset.state = state;
    }));
  } else if (state === "checking") {
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const f = screen.querySelector(".flight");
      if (f) f.dataset.state = "checking";
    }));
  }
  if (view === "outcome" && result.action === "hold") {
    if (!holdEndsAt) holdEndsAt = Date.now() + (result.auto_release_minutes || 60) * 60000;
    tick();
    if (!timer) timer = setInterval(tick, 1000);
  }
}

// --- actions --------------------------------------------------------------------

async function pay() {
  view = "checking";
  render();
  const started = performance.now();
  try {
    result = await score(current, EMBEDDED);
  } catch (err) {
    errorKind = err.status === 503 ? "models" : "network";
    view = "error";
    render();
    return;
  }
  const wait = MIN_CHECK_MS - (performance.now() - started);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  holdEndsAt = 0;
  view = "outcome";
  render();
  post({ type: "decision", key: current.key, result });
  if (result.action === "release") setTimeout(() => { if (view === "outcome") { view = "sent"; render(); } }, 1100);
  $("#o-title")?.focus?.();
}

function load(key) {
  current = scenarios.find((s) => s.key === key) ?? scenarios[0];
  result = null; view = "pay"; confirmedAfterWarning = false; holdEndsAt = 0;
  stopTimer();
  render();
  post({ type: "loaded", key: current.key });
}

function setLang(next) {
  lang = next;
  rememberLang(lang);
  document.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = L()[el.dataset.i18n]; });
  document.title = `${L().app_title} · Maya`;
  renderScenarioList();
  render();
}

function renderScenarioList() {
  $("#scenario-list").innerHTML = scenarios.map((s) =>
    `<li><button type="button" data-key="${esc(s.key)}"><strong>${esc(pick(s.label))} · ${esc(money(s.amount_inr))}</strong><span>${esc(pick(s.story))}</span></button></li>`).join("");
}

document.addEventListener("click", (e) => {
  const act = e.target.closest("[data-act]")?.dataset.act;
  const langBtn = e.target.closest("[data-lang]");
  const pickBtn = e.target.closest("#scenario-list [data-key]");
  if (langBtn) { setLang(langBtn.dataset.lang); post({ type: "lang", lang }); return; }
  if (pickBtn) { $("#scenarios").close(); load(pickBtn.dataset.key); return; }
  if (e.target.closest("#open-scenarios")) { $("#scenarios").showModal(); return; }
  if (!act) return;
  if (act === "pay") pay();
  if (act === "cancel") { view = "cancelled"; render(); }
  if (act === "call") { view = "calling"; render(); }
  if (act === "end-call") { view = "outcome"; render(); }
  if (act === "yes") { view = "nudge-yes"; render(); }
  if (act === "no") {
    confirmedAfterWarning = true;
    const btn = e.target.closest("[data-act]");
    btn.dataset.act = "pay-anyway";
    btn.textContent = L().pay_anyway(money(current.amount_inr));
  }
  if (act === "pay-anyway") { view = "sent"; render(); }
  if (act === "restart") load(current.key);
});

// The judges' demo drives the embedded app.
window.addEventListener("message", (e) => {
  if (e.origin !== location.origin || !e.data?.maya) return;
  if (e.data.type === "load") load(e.data.key);
  if (e.data.type === "lang" && e.data.lang !== lang) setLang(e.data.lang);
});

// --- start -------------------------------------------------------------------------

(async function start() {
  try {
    scenarios = await getScenarios();
  } catch {
    view = "error"; errorKind = "network";
    setLang(lang);
    return;
  }
  setLang(lang);
  load(params.get("s") ?? (EMBEDDED ? scenarios[0].key : "police"));
})();
