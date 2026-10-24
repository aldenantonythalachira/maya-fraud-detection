"use client";

import { useEffect, useState, type ReactNode } from "react";
import {
  fetchTrace,
  fetchCircuitBreaker,
  fetchMetrics,
  extractClaim,
  requestReview,
  SCENARIOS,
  type Scenario,
  type Transaction,
  type TraceResponse,
  type CircuitBreakerResponse,
  type Metrics,
  type ReviewResponse,
} from "@/lib/api";

const ANALYST_NOTE =
  "Analyst Note: User usually pays merchants under ₹5,000. This is a ₹3 Lakh transfer to a new account (d_R=1). High risk of social engineering.";

const METRIC_LABELS: Record<string, string> = {
  xgbAuroc: "XGBoost AUROC",
  auprc: "AUPRC",
  qhat: "Conformal q̂",
  alpha: "Alpha",
  datasetSize: "Dataset Size",
  gnnAuroc: "GNN AUROC",
  fedavgAuroc: "FedAvg AUROC",
  redTeamDrop: "Red-Team Drop",
};

function formatMetric(key: string, value: number | null): string {
  if (value === null) return "N/A";
  if (key === "xgbAuroc" || key === "auprc" || key === "gnnAuroc" || key === "fedavgAuroc") {
    return `${(value * 100).toFixed(2)}%`;
  }
  if (key === "redTeamDrop") return `${value.toFixed(1)} pts`;
  if (key === "qhat") return value.toFixed(6);
  if (key === "alpha") return value.toFixed(2);
  return value.toLocaleString("en-IN");
}

function Icon({ name }: { name: string }) {
  const props = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "h-4 w-4",
  };
  switch (name) {
    case "input":
      return (
        <svg {...props}>
          <path d="M4 4h16v16H4z" />
          <path d="M4 9h16" />
          <path d="M9 4v5" />
        </svg>
      );
    case "triage":
      return (
        <svg {...props}>
          <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" />
        </svg>
      );
    case "conformal":
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="9" />
          <circle cx="12" cy="12" r="4" />
          <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
        </svg>
      );
    case "shap":
      return (
        <svg {...props}>
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.35-4.35" />
        </svg>
      );
    case "policy":
      return (
        <svg {...props}>
          <path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      );
    case "final":
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="9" />
          <path d="m8 12 3 3 5-6" />
        </svg>
      );
    case "analyst":
      return (
        <svg {...props}>
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21c0-4 3.6-6 8-6s8 2 8 6" />
        </svg>
      );
    default:
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="9" />
        </svg>
      );
  }
}

type BadgeTone = "red" | "amber" | "emerald" | "slate";

type NumKey = "amount" | "d_R" | "z_t" | "e_t" | "g_t" | "pi_t";

type SandboxForm = {
  amount: number;
  d_R: number;
  z_t: number;
  e_t: number;
  g_t: number;
  pi_t: number;
  is_screen_shared: boolean;
  chat_stage: string;
  intent_claim: string;
  payment_direction: string;
  mulehunter_status: string;
};

const NUM_FIELDS: { label: string; key: NumKey }[] = [
  { label: "Amount", key: "amount" },
  { label: "Mule Hops (d_R)", key: "d_R" },
  { label: "z_t", key: "z_t" },
  { label: "e_t", key: "e_t" },
  { label: "g_t", key: "g_t" },
  { label: "pi_t", key: "pi_t" },
];

function Badge({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  const tones: Record<BadgeTone, string> = {
    red: "border-red-700 bg-red-900/50 text-red-200",
    amber: "border-amber-700 bg-amber-900/50 text-amber-200",
    emerald: "border-emerald-700 bg-emerald-900/50 text-emerald-200",
    slate: "border-zinc-700 bg-zinc-800 text-zinc-300",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

function Step({
  step,
  icon,
  title,
  last = false,
  children,
}: {
  step: number;
  icon: string;
  title: string;
  last?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="relative flex gap-4">
      <div className="flex flex-col items-center">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-zinc-300">
          <Icon name={icon} />
        </div>
        {!last && <div className="my-1 w-px flex-1 bg-zinc-800" />}
      </div>
      <div className={`min-w-0 flex-1 ${last ? "" : "pb-8"}`}>
        <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
          Step {step}
        </p>
        <h3 className="mb-2 text-base font-semibold text-white">{title}</h3>
        {children}
      </div>
    </div>
  );
}

export default function Home() {
  const [active, setActive] = useState<Scenario | null>(null);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [payload, setPayload] = useState<Transaction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analystAction, setAnalystAction] = useState<string | null>(null);
  const [circuit, setCircuit] = useState<CircuitBreakerResponse | null>(null);
  const [showSandbox, setShowSandbox] = useState(false);
  const [sandbox, setSandbox] = useState<SandboxForm>({
    amount: 50000,
    d_R: 3,
    z_t: 0.5,
    e_t: 0,
    g_t: 0,
    pi_t: 0,
    is_screen_shared: false,
    chat_stage: "none",
    intent_claim: "none",
    payment_direction: "outgoing",
    mulehunter_status: "clean",
  });
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [activeStoryTab, setActiveStoryTab] = useState<"pipeline" | "evidence">(
    "pipeline",
  );
  const [chatMessage, setChatMessage] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [extractMsg, setExtractMsg] = useState<string | null>(null);
  const [showReview, setShowReview] = useState(false);
  const [reviewResult, setReviewResult] = useState<ReviewResponse | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [reviewApproved, setReviewApproved] = useState(false);

  useEffect(() => {
    fetchMetrics()
      .then(setMetrics)
      .catch(() => setMetrics(null));
  }, []);

  async function runScenario(s: Scenario) {
    setActive(s);
    setPayload(s.payload);
    setLoading(true);
    setError(null);
    setAnalystAction(null);
    setShowReview(false);
    setReviewResult(null);
    setReviewApproved(false);
    try {
      setTrace(await fetchTrace(s.payload));
    } catch (e) {
      setTrace(null);
      setError(
        e instanceof Error ? e.message : "Failed to reach the scoring API.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function runSandbox() {
    setActive(null);
    setPayload(sandbox);
    setLoading(true);
    setError(null);
    setAnalystAction(null);
    setShowReview(false);
    setReviewResult(null);
    setReviewApproved(false);
    try {
      setTrace(await fetchTrace(sandbox));
    } catch (e) {
      setTrace(null);
      setError(
        e instanceof Error ? e.message : "Failed to reach the scoring API.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function runCircuit() {
    try {
      setCircuit(await fetchCircuitBreaker("mule_123"));
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Failed to reach the circuit-breaker API.",
      );
    }
  }

  async function handleExtract() {
    setExtracting(true);
    setExtractMsg(null);
    try {
      const res = await extractClaim({ chat_message: chatMessage });
      setSandbox((prev) => ({
        ...prev,
        intent_claim: res.intent_claim,
        payment_direction:
          res.intent_claim === "receive_refund"
            ? "outgoing"
            : prev.payment_direction,
      }));
      setExtractMsg(`✓ Intent extracted: ${res.intent_claim}. Text was not stored.`);
    } catch {
      setExtractMsg("Extraction failed. Please try again.");
    } finally {
      setExtracting(false);
    }
  }

  async function submitReview() {
    if (!trace) return;
    setReviewing(true);
    try {
      const res = await requestReview({
        trace_id: trace.decision_signature,
        reason: "Legitimate payment concern",
      });
      setReviewResult(res);
    } catch {
      setReviewResult({
        status: "error",
        reference_id: "",
        message: "Failed to submit review request.",
      });
    } finally {
      setReviewing(false);
    }
  }

  function setSandboxNum(key: NumKey, value: string) {
    setSandbox((prev) => ({ ...prev, [key]: value === "" ? 0 : Number(value) }));
  }

  const action = trace?.final_decision.action;
  const displayAction = reviewApproved ? "release" : action;
  const finalTone =
    displayAction === "release"
      ? "emerald"
      : displayAction === "nudge"
        ? "yellow"
        : "red";
  const finalBox =
    finalTone === "emerald"
      ? "border-emerald-700 bg-gradient-to-br from-emerald-900/50 to-emerald-950/20"
      : finalTone === "yellow"
        ? "border-yellow-700 bg-gradient-to-br from-yellow-900/50 to-yellow-950/20"
        : "border-red-700 bg-gradient-to-br from-red-900/50 to-red-950/20";

  const hasAnalyst = trace?.final_decision.requires_analyst ?? false;

  return (
    <main className="flex min-h-screen bg-zinc-950 text-white">
      {/* Left sidebar */}
      <aside className="sticky top-0 flex h-screen w-1/3 shrink-0 flex-col gap-6 overflow-y-auto border-r border-zinc-800 bg-zinc-950/60 p-6">
        <button
          type="button"
          onClick={runCircuit}
          className="w-full rounded-xl border border-red-800 bg-red-900/30 px-4 py-3 text-sm font-semibold text-red-200 transition-colors hover:bg-red-900/50"
        >
          ⚠️ Circuit Breaker
        </button>

        <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-zinc-400">
            System Metrics
          </h2>
          <div className="grid grid-cols-2 gap-3">
            {metrics ? (
              Object.entries(metrics).map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3"
                >
                  <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                    {METRIC_LABELS[key] ?? key}
                  </p>
                  <p className="mt-1 bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-lg font-bold text-transparent">
                    {formatMetric(key, value)}
                  </p>
                </div>
              ))
            ) : (
              <p className="col-span-2 text-sm text-zinc-500">
                Loading metrics…
              </p>
            )}
          </div>
        </section>

        {showSandbox ? (
          <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-zinc-400">
              Sandbox
            </h2>

            <div className="mb-4 space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-400">
                Jury Workbench
              </h3>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-700 bg-emerald-900/50 px-2.5 py-0.5 text-xs font-medium text-emerald-200">
                🔒 Private Mode: Raw text processed in memory only.
              </span>
              <textarea
                value={chatMessage}
                onChange={(e) => setChatMessage(e.target.value)}
                rows={3}
                placeholder="Paste a suspicious message here, e.g. 'Please pay ₹50,000 to claim your refund'"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-2 text-sm text-white"
              />
              <button
                type="button"
                onClick={handleExtract}
                disabled={extracting || chatMessage.trim() === ""}
                className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {extracting ? "Extracting…" : "Extract Intent & Auto-Fill"}
              </button>
              {extractMsg && (
                <p
                  className={`text-xs ${
                    extractMsg.startsWith("✓")
                      ? "text-emerald-300"
                      : "text-red-300"
                  }`}
                >
                  {extractMsg}
                </p>
              )}
            </div>

            <div className="my-4 border-t border-zinc-800" />

            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Manual Override
            </h3>

            <div className="space-y-3">
              {NUM_FIELDS.map((f) => (
                <label key={f.key} className="block">
                  <span className="mb-1 block text-xs text-zinc-400">
                    {f.label}
                  </span>
                  <input
                    type="number"
                    value={sandbox[f.key]}
                    onChange={(e) => setSandboxNum(f.key, e.target.value)}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-2 text-sm text-white"
                  />
                </label>
              ))}
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input
                  type="checkbox"
                  checked={sandbox.is_screen_shared}
                  onChange={(e) =>
                    setSandbox((prev) => ({
                      ...prev,
                      is_screen_shared: e.target.checked,
                    }))
                  }
                />
                Screen Shared
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-zinc-400">
                  Chat Stage
                </span>
                <select
                  value={sandbox.chat_stage}
                  onChange={(e) =>
                    setSandbox((prev) => ({
                      ...prev,
                      chat_stage: e.target.value,
                    }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-2 text-sm text-white"
                >
                  <option value="none">none</option>
                  <option value="escalated">escalated</option>
                  <option value="payment_demand">payment_demand</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-zinc-400">
                  Intent Claim
                </span>
                <select
                  value={sandbox.intent_claim}
                  onChange={(e) =>
                    setSandbox((prev) => ({
                      ...prev,
                      intent_claim: e.target.value,
                    }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-2 text-sm text-white"
                >
                  <option value="none">none</option>
                  <option value="receive_refund">receive_refund</option>
                  <option value="pay_fee">pay_fee</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-zinc-400">
                  Payment Direction
                </span>
                <select
                  value={sandbox.payment_direction}
                  onChange={(e) =>
                    setSandbox((prev) => ({
                      ...prev,
                      payment_direction: e.target.value,
                    }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-2 text-sm text-white"
                >
                  <option value="outgoing">outgoing</option>
                  <option value="incoming">incoming</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-zinc-400">
                  MuleHunter Status
                </span>
                <select
                  value={sandbox.mulehunter_status}
                  onChange={(e) =>
                    setSandbox((prev) => ({
                      ...prev,
                      mulehunter_status: e.target.value,
                    }))
                  }
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-2 text-sm text-white"
                >
                  <option value="clean">clean</option>
                  <option value="suspicious">suspicious</option>
                  <option value="mule">mule</option>
                </select>
              </label>
              <button
                type="button"
                onClick={runSandbox}
                disabled={loading}
                className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Simulate Custom Trace
              </button>
              <button
                type="button"
                onClick={() => setShowSandbox(false)}
                className="w-full rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 transition-colors hover:border-zinc-600"
              >
                Back to Scenarios
              </button>
            </div>
          </section>
        ) : (
          <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-zinc-400">
              Scenarios
            </h2>
            <div className="space-y-2">
              {SCENARIOS.map((s) => {
                const isActive = active?.name === s.name;
                return (
                  <button
                    key={s.name}
                    type="button"
                    onClick={() => runScenario(s)}
                    disabled={loading}
                    className={`w-full rounded-lg border p-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
                      isActive
                        ? "border-emerald-500/60 bg-emerald-900/20 ring-1 ring-emerald-500/40"
                        : "border-zinc-800 bg-zinc-950/40 hover:border-zinc-700"
                    }`}
                  >
                    <p className="text-sm font-medium text-white">{s.name}</p>
                    <p className="mt-1 text-xs text-zinc-400">{s.description}</p>
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              onClick={() => setShowSandbox(true)}
              className="mt-4 w-full rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 transition-colors hover:border-zinc-600"
            >
              Sandbox
            </button>
          </section>
        )}
      </aside>

      {/* Right content — the story */}
      <section className="flex-1 p-8 lg:p-10">
        {circuit && (
          <div className="mb-6 rounded-xl border border-red-800 bg-red-900/30 p-5">
            <p className="text-lg font-bold text-red-200">
              ⚠️ Circuit Breaker Triggered: {circuit.victims_alerted} Victims
              Alerted
            </p>
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="text-left text-zinc-400">
                  <th className="pb-1 font-medium">Amount</th>
                  <th className="pb-1 font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                {circuit.at_risk_transactions.map((t, i) => (
                  <tr key={i} className="border-t border-zinc-800">
                    <td className="py-1.5 text-zinc-200">
                      ₹{t.amount.toLocaleString("en-IN")}
                    </td>
                    <td className="py-1.5 text-zinc-200">{t.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && !error && !trace && !circuit && (
          <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900 text-zinc-500">
              <Icon name="final" />
            </div>
            <h1 className="text-xl font-semibold text-white">
              Pipeline Storyteller
            </h1>
            <p className="mt-2 max-w-sm text-sm text-zinc-400">
              Select a scenario from the sidebar to replay the full
              fraud-detection pipeline, step by step.
            </p>
          </div>
        )}

        {loading && (
          <div className="flex min-h-[60vh] items-center justify-center">
            <p className="animate-pulse text-zinc-300">Running the pipeline…</p>
          </div>
        )}

        {!loading && error && (
          <div className="rounded-lg border border-red-800 bg-red-900/30 p-4 text-sm text-red-300">
            Error: {error}
          </div>
        )}

        {!loading && !error && trace && payload && (
          <div className="mx-auto max-w-2xl">
            <div className="mb-8">
              <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                Selected scenario
              </p>
              <h1 className="mt-1 text-2xl font-bold text-white">
                {active ? active.name : "Custom Sandbox"}
              </h1>
              <p className="mt-1 text-sm text-zinc-400">
                {active ? active.description : "Manual feature input"}
              </p>
            </div>

            <div className="mb-6 flex gap-2 border-b border-zinc-800">
              <button
                type="button"
                onClick={() => setActiveStoryTab("pipeline")}
                className={`rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                  activeStoryTab === "pipeline"
                    ? "border-emerald-500 text-white"
                    : "border-transparent text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Pipeline
              </button>
              <button
                type="button"
                onClick={() => setActiveStoryTab("evidence")}
                className={`rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
                  activeStoryTab === "evidence"
                    ? "border-emerald-500 text-white"
                    : "border-transparent text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Evidence &amp; Audit
              </button>
            </div>

            {activeStoryTab === "pipeline" && (
              <>
                <Step step={1} icon="input" title="Raw Input">
              <div className="grid grid-cols-3 gap-2">
                <div className="rounded-lg bg-zinc-900 p-3">
                  <p className="text-[11px] uppercase text-zinc-500">Amount</p>
                  <p className="text-sm font-semibold text-white">
                    ₹{payload.amount.toLocaleString("en-IN")}
                  </p>
                </div>
                <div className="rounded-lg bg-zinc-900 p-3">
                  <p className="text-[11px] uppercase text-zinc-500">
                    Mule Hops (d_R)
                  </p>
                  <p className="text-sm font-semibold text-white">
                    {payload.d_R}
                  </p>
                </div>
                <div className="rounded-lg bg-zinc-900 p-3">
                  <p className="text-[11px] uppercase text-zinc-500">
                    Screen Shared
                  </p>
                  <p className="text-sm font-semibold text-white">
                    {payload.is_screen_shared ? "Yes" : "No"}
                  </p>
                </div>
              </div>
            </Step>

            <Step step={2} icon="triage" title="System-1 Triage">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  tone={
                    trace.triage.path === "fast"
                      ? "emerald"
                      : trace.triage.path === "intent"
                        ? "red"
                        : "amber"
                  }
                >
                  {trace.triage.path}
                </Badge>
                <p className="text-sm text-zinc-300">{trace.triage.reason}</p>
              </div>
            </Step>

            <Step step={3} icon="conformal" title="Conformal Prediction">
              <div className="grid grid-cols-3 gap-2">
                <div className="rounded-lg bg-zinc-900 p-3">
                  <p className="text-[11px] uppercase text-zinc-500">Qhat</p>
                  <p className="font-mono text-sm font-semibold text-white">
                    {metrics ? formatMetric("qhat", metrics.qhat) : "…"}
                  </p>
                </div>
                <div className="rounded-lg bg-zinc-900 p-3">
                  <p className="text-[11px] uppercase text-zinc-500">Alpha</p>
                  <p className="font-mono text-sm font-semibold text-white">
                    {metrics ? formatMetric("alpha", metrics.alpha) : "…"}
                  </p>
                </div>
                <div className="rounded-lg bg-zinc-900 p-3">
                  <p className="text-[11px] uppercase text-zinc-500">Set</p>
                  <p className="font-mono text-sm font-semibold text-white">
                    {trace.conformal_set}
                  </p>
                </div>
              </div>
            </Step>

            <Step step={4} icon="shap" title="Explainability (SHAP)">
              <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-300">
                {trace.shap_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </Step>

            <Step step={5} icon="policy" title="Two-Signal Policy">
              <div className="space-y-3">
                <div>
                  <p className="mb-1 text-[11px] uppercase text-zinc-500">
                    Hard signals
                  </p>
                  {trace.signals_fired.hard.length ? (
                    <div className="flex flex-wrap gap-2">
                      {trace.signals_fired.hard.map((s) => (
                        <Badge key={s} tone="red">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-500">None</p>
                  )}
                </div>
                <div>
                  <p className="mb-1 text-[11px] uppercase text-zinc-500">
                    Soft signals
                  </p>
                  {trace.signals_fired.soft.length ? (
                    <div className="flex flex-wrap gap-2">
                      {trace.signals_fired.soft.map((s) => (
                        <Badge key={s} tone="amber">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-zinc-500">None</p>
                  )}
                </div>
              </div>
            </Step>

            <Step step={6} icon="final" title="Final Action" last={!hasAnalyst}>
              <div className={`rounded-xl border p-6 ${finalBox}`}>
                <p className="text-5xl font-bold capitalize text-white">
                  {displayAction}
                </p>
                <p className="mt-2 text-sm text-zinc-300">
                  {displayAction === "hold"
                    ? `Auto-release in ${trace.final_decision.auto_release_minutes} minutes`
                    : displayAction === "release" && reviewApproved
                      ? "Released after independent analyst review"
                      : "No further action required"}
                  {trace.final_decision.requires_analyst
                    ? " · Analyst review required"
                    : ""}
                </p>
              </div>

              {!reviewApproved &&
                trace.final_decision.action === "hold" &&
                active &&
                active.name.includes("Priya") && (
                  <div className="mt-3 rounded-lg border border-rose-500/50 bg-rose-950/50 p-4 text-rose-200">
                    🚨 Priya Alert Triggered: Trusted contact notified via SMS about
                    the suspicious screen-share call.
                  </div>
                )}

              {(action === "nudge" || action === "hold") && !reviewApproved && (
                <div className="mt-3">
                  {!showReview ? (
                    <button
                      type="button"
                      onClick={() => setShowReview(true)}
                      className="rounded-lg border border-zinc-600 bg-zinc-800/60 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-zinc-700"
                    >
                      This was a mistake / Request Review
                    </button>
                  ) : (
                    <div className="rounded-lg border border-zinc-700 bg-zinc-950/50 p-4">
                      <p className="mb-3 text-sm text-zinc-300">
                        If this was a legitimate payment, you can request an
                        independent analyst to review this decision.
                      </p>
                      <div className="flex flex-wrap gap-3">
                        <button
                          type="button"
                          onClick={submitReview}
                          disabled={reviewing}
                          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
                        >
                          {reviewing ? "Submitting…" : "Submit Request"}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setReviewApproved(true);
                            setShowReview(false);
                          }}
                          className="rounded-lg border border-zinc-600 bg-zinc-800/60 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-zinc-700"
                        >
                          Simulate Analyst Approval
                        </button>
                      </div>
                      {reviewResult && (
                        <div className="mt-3 rounded-lg border border-emerald-700 bg-emerald-900/30 p-3">
                          <p className="text-sm font-semibold text-emerald-200">
                            {reviewResult.message}
                          </p>
                          {reviewResult.reference_id && (
                            <p className="mt-1 font-mono text-xs text-emerald-300">
                              Reference: {reviewResult.reference_id}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </Step>

            {hasAnalyst && (
              <Step step={7} icon="analyst" title="Analyst Review" last>
                <div className="rounded-lg border border-zinc-700 bg-zinc-950/40 p-4">
                  <p className="mb-1 text-sm font-semibold text-white">
                    AI Analyst Summary
                  </p>
                  <p className="text-sm text-zinc-300">{ANALYST_NOTE}</p>
                </div>
                <div className="mt-3 flex gap-3">
                  <button
                    type="button"
                    onClick={() => setAnalystAction("Release approved by analyst.")}
                    className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500"
                  >
                    Approve Release
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setAnalystAction("Report filed with NCRP (ref NCRP-0000123).")
                    }
                    className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-500"
                  >
                    File 1930 Report
                  </button>
                </div>
                {analystAction && (
                  <p className="mt-3 text-sm text-emerald-300">{analystAction}</p>
                )}
              </Step>
            )}
              </>
            )}

            {activeStoryTab === "evidence" && (
              <div className="space-y-4">
                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
                  <h3 className="mb-3 text-sm font-semibold text-white">
                    Intent Verification
                  </h3>
                  {payload.intent_claim === "receive_refund" &&
                  payload.payment_direction === "outgoing" ? (
                    <div className="rounded-lg border border-red-700 bg-red-900/50 p-4">
                      <p className="text-sm font-semibold text-red-200">
                        ⚠️ Intent Contradiction
                      </p>
                      <p className="mt-1 text-sm text-red-300">
                        Claimed to receive a refund but the payment direction is
                        outgoing.
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-zinc-300">No contradiction.</p>
                  )}
                  <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <div className="rounded-lg bg-zinc-950/40 p-3">
                      <p className="text-[11px] uppercase text-zinc-500">
                        Intent Claim
                      </p>
                      <p className="font-mono text-white">
                        {payload.intent_claim ?? "none"}
                      </p>
                    </div>
                    <div className="rounded-lg bg-zinc-950/40 p-3">
                      <p className="text-[11px] uppercase text-zinc-500">
                        Payment Direction
                      </p>
                      <p className="font-mono text-white">
                        {payload.payment_direction ?? "outgoing"}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
                  <h3 className="mb-3 text-sm font-semibold text-white">
                    Evidence Sources
                  </h3>
                  {trace.evidence_sources.length ? (
                    <div className="space-y-2">
                      {trace.evidence_sources.map((ev, i) => (
                        <div
                          key={i}
                          className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950/40 px-3 py-2 text-sm"
                        >
                          <span className="font-mono text-white">
                            {ev.signal}
                          </span>
                          <span className="text-zinc-500">·</span>
                          <span className="text-zinc-400">{ev.source}</span>
                          {ev.source_id && (
                            <>
                              <span className="text-zinc-500">·</span>
                              <span className="font-mono text-emerald-400">
                                {ev.source_id}
                              </span>
                            </>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-zinc-500">No evidence recorded.</p>
                  )}
                </div>

                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
                  <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="h-4 w-4"
                    >
                      <rect x="3" y="11" width="18" height="11" rx="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                    Signed Audit Record
                  </h3>
                  <p className="break-all font-mono text-xs text-emerald-300">
                    {trace.decision_signature}
                  </p>
                  <p className="mt-2 text-xs text-zinc-500">
                    SHA-256 of the final decision JSON.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
