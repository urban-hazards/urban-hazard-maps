# Plan: remove the legacy GitHub Actions workflow `.github/workflows/update.yml`

Repo: urban-hazards/urban-hazard-maps (public). Date: 2026-09-23. Author: Claude (Fable) for Brian.
Decision requested from reviewers: is deleting this file safe, and is anything else needed?

## 1. Why the workflow exists

- Added 2026-03-30 in the repo's initial commit ("needle hotspot pipeline and dashboard"),
  when the project was a single Python package at the repo root. Touched again 2026-03-31
  ("Open source release: MIT license, live data, simplified Pages deploy") and 2026-04-02
  (Scott's refactor to uv + Typer CLI).
- Its job was the whole deployment of v1: on a monthly schedule (cron `0 7 1 * *`), on manual
  dispatch, or on pushes to `main` touching `src/**`, `templates/**` or `pyproject.toml`, it
  ran the old CLI `uv run boston-needle-map run`, which fetched 311 data and rendered a static
  `docs/index.html`, then committed `docs/` back to `main` with the github-actions bot
  (`permissions: contents: write`) so GitHub Pages could serve it.

## 2. What it does today

Nothing useful. Every run since 2026-04-04 has failed at the first real step:

| Run | Trigger | Result |
|---|---|---|
| 2026-04-02 | push | success (last good run, pre-monorepo) |
| 2026-04-04 | push e60372a "Migrate to Astro SSR frontend + FastAPI backend monorepo" | failure |
| 2026-05-01, 06-01, 07-01, 08-01 | schedule | failure |
| 2026-09-01 | (no run recorded) | — |

Failure reason (2026-08-01 log): `error: No pyproject.toml found in current directory or any
parent directory` from `uv sync` at the repo root. Exit code 2.

Why it broke: the 2026-04-04 monorepo migration
- moved the Python project to `pipeline/` (root `pyproject.toml` gone),
- renamed the CLI entry point to `boston-pipeline` (`pipeline/pyproject.toml` `[project.scripts]`),
- deleted `docs/index.html` (the only artifact the workflow verifies and commits),
- removed root `src/` and `templates/` (the workflow's push-path filters now match nothing).

## 3. What replaced it

- Production is Railway: an Astro SSR frontend service and a pipeline cron service that runs
  `boston-pipeline` daily at 07:00 UTC and writes JSON to an S3-compatible bucket. Documented
  in CLAUDE.md ("Deployment: Railway (two services)").
- GitHub Pages is not enabled for the repo: `GET /repos/urban-hazards/urban-hazard-maps/pages`
  returns 404. `docs/` today holds wiki/design/ADR markdown only, no built site.
- PR CI lives in `.github/workflows/pr.yml` (lint, format, mypy, pipeline tests, frontend
  build/check, scraper tests, secret scan). Independent of `update.yml`.

## 4. Why deletion is safe

1. No consumer. Nothing reads `docs/index.html`; Pages is off; the site is served by Railway.
2. It cannot succeed without recreating the v1 layout. Fixing it would mean running the
   pipeline in Actions, which needs the S3 credentials in GitHub secrets and would duplicate
   the Railway cron. That is a new design decision, not a repair.
3. Removing it removes a standing `contents: write` token grant on a public repo for a job
   that has done nothing but fail for five months. Smaller attack surface.
4. It stops the monthly "Some jobs were not successful" email.
5. Reversible: the file is in git history (`git show 583e80a:.github/workflows/update.yml`).

## 5. Proposed change (one PR)

- `git rm .github/workflows/update.yml`.
- README.md lines ~73–93 still document the old `boston-needle-map` CLI (`serve`, `run`,
  `cache-clear`, `dump-json`). Replace with the current commands from CLAUDE.md
  (`uv run boston-pipeline …` from `pipeline/`, `pnpm dev` from `frontend/`).
- No code, config, or secret changes. PR CI must stay green.

## 6. What I checked and did not find

- No other workflow, script, or doc references `update.yml` or the `github-actions[bot]`
  commit convention.
- No branch protection rule or required status check named after this workflow
  (PR #154 merged today with only `pr.yml` checks required).
- No Railway or external system polls `docs/` in this repo.

## Questions for reviewers

1. Is anything in section 4 wrong or unverified? What would you check before deleting?
2. Is there any reason to keep a monthly Actions job at all (e.g. as an independent
   canary if the Railway cron dies)? If so, what would it minimally look like, and should it
   be a separate follow-up rather than blocking this deletion?
3. Any risk in the README rewrite, or in deleting a workflow that has `workflow_dispatch`
   inputs someone might rely on?
4. Verdict: SAFE TO DELETE / NOT SAFE / SAFE WITH CONDITIONS (state them).


## Reviews (2026-09-23)

### Gemini via agy

1. **Section 4 verification**: The claims are logically sound and supported by the workflow failure logs. The assertion that "GitHub Pages is off" cannot be verified purely from the attached source files. However, this is irrelevant—since the workflow has failed on `uv sync` for five months, it is not updating Pages anyway. I would check the repository settings to confirm Pages is actually disabled before merging, just to be thorough.

2. **Keeping a monthly job**: There is no reason to keep *this* specific job. It is broken and attempts to run a deprecated architecture. If a canary is needed to monitor Railway or S3, it should be a new, lightweight workflow (e.g., a script that checks S3 object timestamps or pings a Railway health endpoint). This should be handled in a separate follow-up PR and should not block the deletion of this file.

3. **Risks (workflow_dispatch & README)**: There is zero risk in deleting the `workflow_dispatch` trigger. It has been broken since April, meaning nobody is successfully relying on it. Regarding the README rewrite, there is a risk of introducing inaccuracies. The plan proposes replacing the old CLI instructions with commands for `pipeline/` and `frontend/`. However, the attached README snippet (lines 67-68) explicitly references a `backend/` directory for the `serve` command. Blindly replacing all `boston-needle-map` references with `boston-pipeline` and omitting the backend will break the documentation. The rewrite must accurately document all three components (`frontend`, `backend`, and `pipeline`).

**Verdict**: SAFE WITH CONDITIONS (ensure the README update correctly documents the `backend` commands, not just `pipeline` and `frontend`).


### DeepSeek 4.1 Flash via OpenRouter ($0.0015)

## Answers

**Q1 — Is section 4 wrong or unverified?**

Section 4 is mostly sound but has unverified claims:

- **"No consumer"** — verified for `docs/index.html` (Pages 404, Railway serves the site). But the plan never checks whether the *S3 bucket* or any downstream dashboard ingests the `github-actions[bot]` commit pattern. It asserts "No Railway or external system polls `docs/`" without showing the check. Weak.
- **"Reversible"** — the cited SHA `583e80a` is not verified against the attached files. If that commit predates the 2026-04-02 uv refactor, `git show` returns the *older* version, not the current one. The current file is attached, so this is cosmetic, but the claim as written is unverified.
- **"No branch protection rule"** — asserted from PR #154, not shown. Acceptable but should be re-confirmed via `gh api repos/.../branches/main/protection` before merge.
- **Section 2 table** — the 2026-09-01 "no run recorded" row is odd. A monthly cron that has fired every month since May should have fired 09-01. Either the schedule was already disabled, or the table is incomplete. This is the single most important unverified item: if the workflow is *already* not running, the "stops the monthly email" rationale (4.4) is moot, and if it *is* running, the table is wrong.

**Q2 — Keep a monthly canary?**

No. A canary that duplicates the Railway cron requires S3 creds in GitHub secrets, re-introduces `contents: write`, and would need its own alerting to be useful. If Railway cron reliability is a concern, that is a separate observability task (Railway healthcheck / dead-man's-switch), not a reason to keep a broken workflow. Follow-up, not blocker.

**Q3 — README rewrite / `workflow_dispatch` risk**

The README rewrite is necessary and low-risk, but the plan understates it: lines 60–100 reference `backend/` and `boston-needle-map`, while the repo root has `pipeline/` and `frontend/` and no `backend/`. The rewrite must fix the directory names too, not just the CLI name. `workflow_dispatch` inputs: the `years` input has a corrupted default (`'[CREDIT_CARD]'` — clearly a redaction artifact in the attached file). No evidence anyone uses it; the workflow has failed on every dispatch since April. No risk.

**Q4 — Verdict**

**SAFE WITH CONDITIONS:** (a) confirm the 2026-09-01 run status and correct the table; (b) re-verify branch protection via API; (c) rewrite README to fix `backend/`→`pipeline/` and `frontend/`, not just the CLI name; (d) confirm no S3/downstream consumer of the bot commit pattern.

**Verdict: SAFE WITH CONDITIONS — deletion is correct, but the plan's evidence for "no consumer" and the run-history table are incomplete.**

## Conditions verified after review

| Condition | Result |
|---|---|
| Sept 1 run missing — is the schedule already off? | Yes. GitHub API reports the workflow `state: disabled_inactivity` (auto-disabled after the 2026-08-01 failure). No further emails would have come anyway; deletion is housekeeping plus removing the write grant. |
| Branch protection / required checks named after this workflow | None. `main` has no classic protection; the repo ruleset "main" requires only `All Checks Pass` from pr.yml. |
| README references `backend/` | `backend/` was removed in the 2026-04-06 commit "Remove FastAPI backend, fix pipeline, add cron deployment" (0 tracked files). The README's How-it-works, Setup, Usage, Development and Structure sections were all stale and are rewritten from CLAUDE.md in this PR. |
| Downstream consumer of the `github-actions[bot]` commit pattern | Four bot commits exist, all 2026-04-02 ("Update needle hotspot data"). Nothing in the repo, Railway config, or services reads `docs/` or those commits. |
| `[CREDIT_CARD]` in the workflow_dispatch description (Flash) | Artifact of the OpenRouter client's PII masking of the digit run "2023 2024 2025 2026" in the brief. The file itself is unaffected. |

**Decision: delete.** Reversible via `git show 583e80a:.github/workflows/update.yml`.
