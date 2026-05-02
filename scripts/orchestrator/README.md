# UHM Ticket Orchestrator (Kimi K2.6 + Codex audit)

Pipes ticket specs through Moonshot's Kimi K2.6 (heavy-lift coder via
OpenRouter) and the OpenAI Codex CLI (auditor) into draft PRs Brian reviews.
Designed around `/tmp/uhm_issues/` and the Brian-domain frontend tickets.

## Threat model — what Kimi sees

Kimi is an external service. The scrubber in `scrub.py` is the single chokepoint
that builds outbound payloads. Three layers, all enforced in code:

1. **Deny-list (hard fail).** `.env*`, `*.pem`, `*.key`, `secrets.*`,
   `*.config`, `serviceAccountKey*.json`, `credentials*`, `.npmrc`, `.aws/*`,
   `.ssh/*`. Match → `ScrubError` → dispatch aborts.
2. **Allow-list per ticket.** `tickets.yml#allowed_files` is the only source of
   truth. No globs, no directory walks reach Kimi.
3. **Regex redaction (intentionally narrow).** OpenAI/GitHub/AWS/Anthropic/
   OpenRouter/Moonshot keys, JWTs, postgres URLs, **private** IPv4 only
   (RFC 1918), URLs with **inline credentials**, AWS-signed URLs, and
   `*.internal` / `*.local` / `*.localhost` / `*.intra` URLs.
   **Public URLs and public IPs are intentionally NOT redacted** — full-file
   output mode round-trips placeholders into the rewritten source, so broad
   URL redaction broke `data-quality.astro` regeneration in the Apr 2026
   calibration. Counts logged to `logs/<id>/redactions.json`.
4. **Strategy strip on ticket markdown.** Sections under `Strategy|Roadmap|
   Future|Vulnerab|Legal|Internal|Notes|Priority|Source|Context` headings are
   removed. Used as a fallback only when no `kimi_brief` is set.
5. **Mechanical prompt template.** Each ticket has a hand-authored
   `kimi_brief` — neutral, no proper names, no political context. Kimi never
   sees the original ticket markdown unless you explicitly leave `kimi_brief`
   blank.

The scrubber's poisoned-input tests in `tests/test_scrub.py` run before every
wave dispatch. If they fail, the dispatcher refuses to start.

## Budget guardrails

- Per Kimi call: ≤ 25K input tokens, ≤ 10K output tokens.
- Per ticket: ≤ $0.50 cumulative spend (initial + retries).
- Per wave: projected spend ≤ $5.00 without `--budget-override`.
- Live watchdog: pause when wave spend crosses $3.00.
- Pricing baked in (per-million tokens, in / out, OpenRouter):
  - `moonshotai/kimi-k2`: $0.55 / $2.20  ← **default** (non-thinking)
  - `moonshotai/kimi-k2.5`: $0.74 / $3.49
  - `moonshotai/kimi-k2.6`: $0.74 / $3.49 (thinking; chews max_tokens budget)
  - `moonshotai/kimi-k2-thinking`: $0.60 / $2.50
- Override the model with `KIMI_MODEL=...` env var.

The dispatcher reads OpenRouter's returned `usage` block and accumulates
`spent_usd` in `logs/<id>/usage.json`.

## Auth

| Service | Where it lives |
|---|---|
| OpenRouter (Kimi) | `OPENROUTER_API_KEY` env var |
| Codex CLI | Brian's existing ChatGPT Pro session (`codex login`) |
| GitHub PR creation | `gh` CLI |

## Operator commands

```bash
# Pre-flight: dry-run a single ticket — builds the scrubbed payload and writes
# everything to logs/<id>/ without making any API call. Eyeball before live.
uv run --with pyyaml python scripts/orchestrator/dispatch.py \
  --ticket G1a --print-payload

# Live single ticket: scrub → Kimi → apply diff → pnpm build → Codex → log
uv run --with pyyaml python scripts/orchestrator/dispatch.py --ticket G1a

# Whole wave (all pending tickets at this wave level, sequential)
# NOTE: not safe to run two --wave invocations concurrently — they share
# /tmp/uhm_work/<id> and kimi/<id> branches.
uv run --with pyyaml python scripts/orchestrator/dispatch.py --wave 1
```

## Layout

```
scripts/orchestrator/
├── tickets.yml              # manifest
├── scrub.py                 # security gateway
├── kimi_client.py           # OpenRouter wrapper + budget caps
├── codex_audit.py           # codex CLI wrapper
├── worktree.py              # git worktree-per-ticket
├── verify.py                # pnpm install + build smoke
├── dispatch.py              # entry point
├── tests/test_scrub.py      # poisoned-fixture tests
├── logs/                    # per-ticket payload, usage, audit (gitignored)
└── README.md
```

## Per-ticket flow

```
tickets.yml entry
  └─ scrub.build_payload()    ← deny-list, allow-list, regex, strategy strip
  └─ logs/<id>/payload.json
  └─ Kimi K2.6 (OpenRouter)   ← mechanical brief + scrubbed file contents
  └─ git apply diff in /tmp/uhm_work/<id> on branch kimi/<id>
  └─ pnpm install + pnpm build smoke
       ├ fail → 1 retry to Kimi with build error
       └ ok → codex audit
              ├ APPROVED → push branch, draft PR
              ├ NEEDS_CHANGES → 1 retry to Kimi (max 2 iterations total)
              └ ERROR → mark MANUAL, leave branch for Brian
```

## Adding a new ticket

1. Drop the human-readable spec in `/tmp/uhm_issues/<id>.md`.
2. Add an entry to `tickets.yml` with:
   - `kimi_brief:` — write this by hand. Mechanical voice. No proper names,
     no narrative, no rationale. Imagine you're writing acceptance tests
     someone will execute blind.
   - `acceptance:` — concrete pass/fail predicates (filenames, build clean,
     visible UI strings).
   - `allowed_files:` — every file Kimi may read or modify. The manifest is
     the only place this list is set.
3. Dry-run with `--print-payload` and review `logs/<id>/payload.json`. Confirm
   no leakage of strategy, names, or unscoped files.
4. Live run with `--ticket <id>`.

## Process — what does what

The pipeline is intentionally three layers, with Claude (the orchestrator
operator) in the middle as a sanity check, NOT a passive merger:

1. **Claude authors** the `kimi_brief` and `allowed_files` for each ticket,
   deciding what scope to send to Kimi.
2. **Kimi K2 generates** the patch (full-file output mode).
3. **Claude reviews** the diff against the **source ticket** in
   `/tmp/uhm_issues/<id>.md` — not just the narrowed brief — and corrects
   small issues by hand (typos, missed acceptance bullets, stylistic drift).
4. **Codex audits** the result against the source ticket and the diff. The
   audit prompt now explicitly receives the source ticket so it can flag
   silently-dropped scope.
5. **Claude opens a draft PR** that honestly describes what was shipped vs
   deferred — never "Closes ticket X" if X has dropped acceptance items.
6. **Brian reviews and merges**.

Skipping step 3 (which the Apr 2026 calibration did) makes Codex tautological:
it audits Kimi's narrowed scope and stamps it APPROVED, then the PR claims
ticket-completion based on that stamp. The brief becomes the ground truth and
the source spec is forgotten.

## File-size sweet spot

Empirically (May 2026 calibration on 4 frontend tickets):

| File size | Full-file mode | Notes |
|---|---|---|
| < 200 lines | ✅ converges in 1 iter | A1, B4, G1a, A2's small files |
| 200–500 lines | ⚠️ 1–3 iters, occasional transcription nits | A2's `index.astro` (270 lines) — needed Codex feedback for a CSS selector typo |
| 500–1000 lines | ❌ K2 starts dropping characters | Caught: `border-radius: 2px;` → `border-radius: px;` on a 600-line `data-quality.astro` |
| > 1000 lines | ❌ output truncates at max_tokens | `HeatMap.tsx` (1,100 lines) — never reaches `<<<END>>>` |

Tickets that require modifying files > 500 lines should be done by hand or refactored into smaller-file edits (e.g. extract a new component, then dispatch a small ticket that wires it).

## What's out of scope

- Pipeline tickets (Scott's domain).
- Auto-merge — every PR is draft; Brian reviews and merges by hand.
- Anything that requires editing `.env`, Railway config, or other secrets.
- Tickets that touch files > ~500 lines (see table above).
