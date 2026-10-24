# Maya — Delivery Ledger

| Phase | Status | Files |
|---|---|---|
| Data Generator | Delivered | `src/journey_generator.py` |
| Features | Delivered | `src/features.py` |
| XGBoost + Conformal + SHAP | Delivered | `src/risk_common.py`, `src/train_xgb.py`, `src/conformal.py`, `src/reasons.py` |
| Two-Signal Policy | Delivered | `src/policy.py` |
| GNN Challenger | Simulated | `src/gnn_challenger.py` |
| FedAvg Sim | Simulated | `src/federated_sim.py` |
| FastAPI Backend | Delivered | `api/main.py` |
| Next.js Frontend | Delivered | `frontend/` |
| Evidence Provenance | Delivered | `api/main.py` (`build_evidence_sources`, `evidence_sources`) |
| Intent Contradiction | Delivered | `api/main.py` (intent short-circuit in `/api/score-trace`) |
| Jury Workbench | Delivered | `api/main.py` (`/api/extract-claim`), `frontend/src/lib/api.ts`, `frontend/src/app/page.tsx` |
| Recourse Flow | Delivered | `api/main.py` (`/api/request-review`), `frontend/src/app/page.tsx` |
| Red-Teaming (Attack Sim) | Delivered | `src/attack_sim.py` |
| Ecosystem Mocks | Delivered | `src/integrations.py` |
| Streamlit Demo UI | Delivered | `ui/app.py` |
