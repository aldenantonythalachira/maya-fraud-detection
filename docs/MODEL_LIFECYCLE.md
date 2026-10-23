# Artifact lifecycle and model gates

`bootstrap_demo.py` generates synthetic seed-42 smoke data, batch features, an
XGBoost model, disjoint-day marginal calibration and an artifact manifest.
Training uses the train period; early stopping/threshold selection use the earlier
half of validation days; calibration uses the later half; test days tune neither.
Generated artifacts are ignored by Git. A rebuilt model does not replace the
recorded versions in old reviews. Use new database names for code/artifact versions.

`model_manifest.py` records artifact hashes, feature columns, Python version,
validation contract and calibration report. Startup refuses model/calibration
hash mismatches when a manifest exists. Hashes are not cryptographic signatures.
Legacy artifacts without a manifest remain loadable for compatibility; regenerate
a complete bundle to obtain the new disjoint tuning/calibration contract.

```powershell
.\.venv\Scripts\python.exe scripts/model_health.py
.\.venv\Scripts\python.exe scripts/model_health.py --require-promotable
```

The second command deliberately fails while deployment gates remain unproven.
Current synthetic coverage passes; recall fails the deck target. Fairness and
bank-load latency remain unestablished. No automated promotion occurs.

## Candidate evaluation

1. Preserve the current source checkpoint and copy the stopped runtime database
   and complete model bundle to a separate local backup folder.
2. Generate candidate data/artifacts in a separate directory. Record seed,
   dependency lock and feature/inference/policy versions.
3. Freeze tuning before final tests. Run independent feature checks, software
   regression tests, later-day/held-out-type evaluation and benchmark comparison.
4. Record class/campaign support and uncertainty intervals; mark missing/weak
   groups inconclusive. Do not average away failed seeds or types.
5. Compare model recall, interruptions, uncertainty coverage and measured latency
   with the existing version. Review explanations and safety behavior manually.
6. Approve a local demo bundle only with its limitations attached. A bank pilot
   requires independent real traffic, fairness, privacy and security milestones.
7. Restart with a new database and approved artifact bundle; never mix artifacts
   within one score. Keep the prior complete bundle for rollback.

For ongoing drift, run the same report on newly bank-confirmed later outcomes,
track marginal and class-specific coverage and subgroup support, and recalibrate
only on a separate fresh calibration set. This repository provides the artifact
gate/report command, not a scheduled production monitor or confirmed-label feed.
No user-generated feedback is automatically used for training.

## Rollback

Stop the server; switch to a safe checkpoint using `scripts/versions.py restore`;
restore that checkpoint's complete matching artifact bundle and use its database
copy or a new database filename. Reinstall its dependency lock. Version mismatches
reject replay/authorization rather than reinterpret prior decisions. The original
stage-03 model/calibration were preserved locally in
`tmp/models-before-decision-platform/` during this work; this ignored local backup
is not available from GitHub. Rebuilding from a checkpoint is another option.
