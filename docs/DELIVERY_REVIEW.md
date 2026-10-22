# Delivery review — 22 October 2026

## Stage 0: baseline

Starting branch: `codex/interactive-wallet`, d1a01ff; clean working tree.
Implementation branch: `codex/decision-platform`. Recovery tags 00–03 exist.
No default branch changes or merges are authorized by this brief.

Baseline: policy self-test 20/20; pip check clean. Full suite started before edits.
Model SHA256: dde9596c9f0aa9e10edd793f934b48667582235b71d856f08c09e90446e26dce.
Calibration SHA256: 3ac42dfda9c5220ad60440f78a1311eeb6723f4793808ce8b5d382ef30b7314e.

The complete source deck was reviewed in this conversation. It promises more than
the working local demo. No new voice/stage/utility weights will be invented.
The brief permits retaining legacy graph semantics when a validated, complete
training migration cannot be established; this release explicitly takes that
compatibility path. Research gaps remain on the checklist.

## Stage 1: wallet

Scope: simplify payer copy; retain consent/status/error information; separate
inspection from payment and operational controls. Acceptance: free-form payment,
receipt/history, keyboard operation and 360/390/768/desktop browser inspection.

## Stage 2: evidence and execution

Scope: exact feature lineage, unique evaluation traces, stage failures/timing,
bound approval, durable role notifications and restricted sharing. Acceptance:
feature oracle, roles/expiry/revocation, stale approvals, failure/retry/restart,
conservation and replay checks. Preserve the four-field policy contract.

## Stage 3: evaluation and handoff

Scope: honest manifest, held-out evaluation command, baseline comparison, verified
bundle, threat model, diagrams, release checklist and recovery instructions.
Acceptance: reproducible scripts and no claims beyond recorded measurements.
