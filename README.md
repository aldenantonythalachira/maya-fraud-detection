# 🛡️ MAYA: The Stripe Radar for Indian UPI

> **🏆 Finalist: Amazon AI Cybersecurity Hackathon (Top 30 out of 5000)**  
> ** Hosted at IIT Delhi**

**Maya** is an enterprise-grade, full-stack, mathematically rigorous fraud detection engine designed specifically for the Indian UPI ecosystem. Unlike traditional systems that reactively blacklist accounts or blindly block users, Maya uses a **Two-Signal Rule**, **Conformal Prediction**, and **Graph Topology** to stop scams without ruining the experience for legitimate users.

---

## 📉 The Problem
Indians lost **₹22,931 crore** to cyber fraud in 2025. The RBI’s current solution is a flat 1-hour hold for everyone—which frustrates normal users. Scammers use AI to write scripts, clone voices, and build trust over multiple days. Traditional text-based detectors fail because scammers just reword their scripts using ChatGPT.

## 💡 The Solution: Maya
Maya doesn't just read text; she reads the **journey** and the **graph topology**. 

1. **The Jev Fast-Path:** 90% of safe transactions bypass the heavy ML model and resolve in < 1ms.
2. **The XGBoost + Conformal Engine:** High-risk transactions hit a 211-tree XGBoost model, wrapped in Conformal Prediction (Qhat) to mathematically guarantee a 90% confidence set.
3. **Tree SHAP:** Generates exact, mathematically verifiable reasons for every block.
4. **The Two-Signal Rule:** A payment is only blocked if **two independent signals agree** (e.g., a Graph Hop + a Soft Signal like Screen Sharing). Soft signals alone can *never* block a payment.
5. **Cryptographic Audit:** Every decision is signed with SHA-256 for RBI compliance.

---

## 🚀 Key Architecture & Features

*   **Synthetic Data Engine:** 3 million realistic UPI transactions generated using Poisson processes and Markov chains to comply with the DPDP Act.
*   **Reverse BFS Graph Engine:** A Multi-Source Reverse Breadth-First Search that calculates the 2-hop distance from any account to a known mule.
*   **Intent Contradiction:** A bounded LLM extracts user intent. If a user claims they are receiving a refund, but the payment is *outgoing*, Maya blocks it instantly.
*   **Evidence Provenance:** Deduplicates evidence so the system doesn't double-count the same police report from different APIs (FRI, MuleHunter).
*   **The Bank API & Simulator:** A FastAPI backend secured with `X-API-Key` headers, accompanied by a `rich` terminal simulator that processes 100 transactions in 1.7 seconds, saving ₹37 Lakhs in simulated fraud.
*   **Research Challengers:** Includes a PyTorch Geometric GNN (98.36% AUROC) and a Federated Learning simulation (99.91% AUROC) to prove future scalability.

---

## 🧮 The Mathematics
Maya is built on rigorous mathematical foundations:
*   **Anomaly Detection:** \(z_t = \log(a_t) - \text{median}_{s<t} \log(a_s)\)
*   **Graph Theory:** \(d_R(v) = \min_{r \in R} \text{hops}(v, r)\)
*   **Conformal Prediction:** \(s_i = 1 - \hat{p}(y_i | x_i)\) calibrated to \(\hat{q} = 0.000246\)
*   **SHAP:** \(\sum \phi_j = \hat{p} - \mathbb{E}[\hat{p}]\) (Exact Shapley values)

---

## 🛠️ Quick Start

### 1. Run the Backend API
```bash
cd ~/maya
python3 -m uvicorn api.main:app --reload

2. Run the Next.js Frontend
bash
cd ~/maya/frontend
npm run dev
# Open http://localhost:3000
3. Run the High-Throughput Bank Simulator
bash
cd ~/maya
python3 scripts/bank_simulator.py
4. Verify the Bank API (cURL)
bash
curl -s -X POST http://127.0.0.1:8000/api/score-trace \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk_live_maya_enterprise" \
  -d '{"amount": 300000, "d_R": 1, "z_t": 3.0, "e_t": 1.5, "g_t": 1, "pi_t": 0, "is_screen_shared": false, "chat_stage": "none", "intent_claim": "none", "payment_direction": "outgoing"}' | python3 -m json.tool
