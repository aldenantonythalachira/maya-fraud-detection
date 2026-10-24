export type Transaction = {
  amount: number;
  d_R: number;
  z_t: number;
  is_screen_shared: boolean;
  e_t?: number;
  g_t?: number;
  pi_t?: number;
  chat_stage?: string;
  intent_claim?: string;
  payment_direction?: string;
  mulehunter_status?: string | null;
};

export type EvidenceSource = {
  signal: string;
  source: string;
  source_id: string | null;
};

export type Decision = {
  action: "release" | "nudge" | "hold";
  reasons: string[];
  auto_release_minutes: number;
  requires_analyst: boolean;
};

export type FinalDecision = {
  action: "release" | "nudge" | "hold";
  auto_release_minutes: number;
  requires_analyst: boolean;
};

export type TraceResponse = {
  triage: { path: "fast" | "slow" | "intent"; reason: string };
  features: Record<string, number>;
  conformal_set: string;
  shap_reasons: string[];
  signals_fired: { hard: string[]; soft: string[] };
  final_decision: FinalDecision;
  evidence_sources: EvidenceSource[];
  decision_signature: string;
};

export async function scoreTransaction(data: Transaction): Promise<Decision> {
  const res = await fetch("http://127.0.0.1:8000/api/score", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": "sk_live_maya_enterprise" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function fetchTrace(data: Transaction): Promise<TraceResponse> {
  const res = await fetch("http://127.0.0.1:8000/api/score-trace", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": "sk_live_maya_enterprise" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export type AtRiskTransaction = {
  amount: number;
  time: string;
};

export type CircuitBreakerResponse = {
  victims_alerted: number;
  at_risk_transactions: AtRiskTransaction[];
  status: string;
};

export async function fetchCircuitBreaker(
  muleId: string,
): Promise<CircuitBreakerResponse> {
  const res = await fetch("http://127.0.0.1:8000/api/circuit-breaker", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": "sk_live_maya_enterprise" },
    body: JSON.stringify({ reported_mule_id: muleId }),
  });
  return res.json();
}

export type Scenario = {
  name: string;
  description: string;
  payload: Transaction;
};

export const SCENARIOS: Scenario[] = [
  {
    name: "1. Normal Transfer (Mom, ₹40k)",
    description: "Routine rent help to a trusted contact.",
    payload: {
      amount: 40000,
      d_R: 3,
      z_t: 0.4,
      e_t: 0.1,
      g_t: 0.0,
      pi_t: 0,
      is_screen_shared: false,
      chat_stage: "none",
    },
  },
  {
    name: "2. Investment Scam (₹3L)",
    description: "IPO 'allotment fee' to a fresh payee promising big returns.",
    payload: {
      amount: 300000,
      d_R: 1,
      z_t: 3.0,
      e_t: 1.5,
      g_t: 1.0,
      pi_t: 0,
      is_screen_shared: false,
      chat_stage: "none",
      mulehunter_status: "mule",
    },
  },
  {
    name: "3. Fake Police Call (Priya Alert + Screen Share)",
    description: "Screen-shared call demanding a 'verification deposit'.",
    payload: {
      amount: 75000,
      d_R: 1,
      z_t: 2.0,
      e_t: 2.0,
      g_t: 1.0,
      pi_t: 0,
      is_screen_shared: true,
      chat_stage: "payment_demand",
      intent_claim: "pay_fee",
      payment_direction: "outgoing",
    },
  },
  {
    name: "4. Unclear Case (Voice only)",
    description: "Voice-only second-hand phone purchase from a stranger.",
    payload: {
      amount: 5000,
      d_R: 3,
      z_t: 0.05,
      e_t: 0.2,
      g_t: 1.0,
      pi_t: 0,
      is_screen_shared: false,
      chat_stage: "escalated",
    },
  },
  {
    name: "5. Jev Fast-Path (₹500)",
    description: "Tiny payment auto-released by System-1 without a full check.",
    payload: {
      amount: 500,
      d_R: 3,
      z_t: 0.005,
      e_t: 0.1,
      g_t: 0.0,
      pi_t: 0,
      is_screen_shared: false,
      chat_stage: "none",
    },
  },
  {
    name: "6. Intent Contradiction (Refund Scam)",
    description: "Claims to be receiving a refund while actually sending money out.",
    payload: {
      amount: 50000,
      d_R: 3,
      z_t: 1.0,
      e_t: 0.5,
      g_t: 1.0,
      pi_t: 0,
      is_screen_shared: false,
      chat_stage: "payment_demand",
      intent_claim: "receive_refund",
      payment_direction: "outgoing",
      mulehunter_status: "mule",
    },
  },
];

export type Metrics = {
  xgbAuroc: number;
  auprc: number;
  qhat: number;
  alpha: number;
  datasetSize: number;
  gnnAuroc: number | null;
  fedavgAuroc: number | null;
  redTeamDrop: number | null;
};

export async function fetchMetrics(): Promise<Metrics> {
  const res = await fetch("http://127.0.0.1:8000/api/metrics");
  return res.json();
}

export type ClaimRequest = {
  chat_message: string;
};

export type ClaimResponse = {
  intent_claim: string;
  processed_in_memory: boolean;
};

export async function extractClaim(
  data: ClaimRequest,
): Promise<ClaimResponse> {
  const res = await fetch("http://127.0.0.1:8000/api/extract-claim", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": "sk_live_maya_enterprise" },
    body: JSON.stringify(data),
  });
  return res.json();
}

export type ReviewRequest = { trace_id: string; reason: string };
export type ReviewResponse = {
  status: string;
  reference_id: string;
  message: string;
};

export async function requestReview(
  data: ReviewRequest,
): Promise<ReviewResponse> {
  const res = await fetch("http://127.0.0.1:8000/api/request-review", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": "sk_live_maya_enterprise" },
    body: JSON.stringify(data),
  });
  return res.json();
}
