# Repository work log

## 2026-10-20 - Finale foundation

- User approved the staged finale plan. Branch: `codex/finale-foundation`, base
  `687635e` on `main`. Workspace-level running log is `../WORK_LOG.md`.
- Audited Python/Streamlit baseline. Models/data are generated and absent from
  Git; scenario decisions are pinned rather than driven by model inference.
- Fixed unconditional holds for scam-only conformal predictions. Every hold
  now needs two signal groups, with at least one hard group. Mule verdicts count
  as recipient evidence in both non-fine prediction sets. Unknown sets fail
  explicitly rather than falling into the unsure branch.
- Added exhaustive signal-group regression checks, a core dependency manifest,
  setup instructions, and GitHub Actions checks. Optional GNN dependencies stay
  out of the core installation path.
- Updated AGENTS.md to document this intentional change from its earlier table.
- Validation pending; no new accuracy claims are made.
