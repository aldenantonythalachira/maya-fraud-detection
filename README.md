# MAYA

Synthetic UPI scam-journey detector and interactive dummy wallet. The core uses
past-only payment/recipient features, XGBoost, conformal prediction and a
two-group intervention policy. No real payments or external fraud reports occur.

## Interactive wallet (Python 3.12)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe scripts/bootstrap_demo.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe src/policy.py --self-test
.\.venv\Scripts\python.exe run_demo.py
```

Open http://127.0.0.1:8000. The wallet generates seeded histories, computes actual
model decisions, records evidence and settles balanced dummy transfers. Open
**How it works** for the live execution trace, feature lineage, graph, SHAP,
replay, simulator clock and recipient view. No real money or UPI PIN is used.

See [the demo runbook](docs/DEMO_RUNBOOK.md) and
[version recovery](docs/VERSION_RECOVERY.md). Use `scripts/versions.py list`
to see published `maya/*` checkpoints; restore creates a new branch and refuses
uncommitted local edits. Both implementation progress and limitations are in
`docs/WORK_LOG.md`.

On macOS/Linux use `.venv/bin/python` for the interpreter. The core requirements
exclude the optional PyTorch/GNN experiment; `requirements.txt` retains the full
experimental dependencies.

## Rebuild a small synthetic baseline

Run from the repository root. These are smoke artifacts, not the submitted B4
experiment or evidence of real-world accuracy.

```text
python src/journey_generator.py --smoke --out-dir data
python src/features.py --days 30
python src/train_xgb.py
python src/conformal.py
```

Generated CSVs, model JSON and simulator databases are ignored by Git. Bootstrap
replaces model/data files; skip it to preserve exact replay of existing reviews.
Validate generator output
(`campaign_split_violations=0`, `ref_integrity=True`) and feature output (all
sample maximum differences are zero). The old UI pins scenario prediction sets;
live model scores shown alongside them do not drive those scenario decisions.
That legacy UI remains at `streamlit run ui/app.py`. The new wallet has no pinned
scenario verdicts. Its graph features preserve the baseline's report-outward
traversal convention; this is explicitly labeled rather than silently changed.

## Team workflow

Branch from the current shared base, implement one reviewable stage, run its
checks, and open a pull request. Do not push directly to `main`. Merge only after
team review. Keep generated datasets, model files and credentials out of commits.
See `docs/WORK_LOG.md` for repository decisions and validation.

## Finale direction

Preserve the baseline detector; add a simulated payment review, narrow
claim-to-operation comparison with abstention, review invalidation when payment
details change, and immutable evidence replay. See the planning log for scope.
All holds require independent signal groups, including at least one history or
recipient group; a scam-only prediction does not override that requirement.
