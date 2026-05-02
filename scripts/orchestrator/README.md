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
3. **Regex redaction.** OpenAI/GitHub/AWS/Anthropic/OpenRouter/Moonshot keys,
   JWTs, IPv4 addresses, absolute URLs, postgres URLs all replaced with
   `[REDACTED_*]`. Counts logged to `logs/<id>/redactions.json`.
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

- Per Kimi call: ≤ 25K input tokens, ≤ 4K output tokens.
- Per ticket: ≤ $0.05 cumulative spend (initial + retries).
- Per wave: projected spend (per-ticket cap × ticket count) ≤ $0.30 without
  `--budget-override`.
- Live watchdog: pause when wave spend crosses $0.20.
- Pricing baked in: Kimi K2.6 on OpenRouter at $0.74/M input, $3.49/M output.

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

# Whole wave (all pending tickets at this wave level, parallel-safe)
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

## What's out of scope

- Pipeline tickets (Scott's domain).
- Auto-merge — every PR is draft; Brian reviews and merges by hand.
- Anything that requires editing `.env`, Railway config, or other secrets.
