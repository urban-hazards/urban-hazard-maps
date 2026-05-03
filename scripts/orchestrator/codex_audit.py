"""Wrapper around the codex CLI for auditing Kimi-produced diffs.

Shells out to `codex exec` (codex-cli 0.125.0). Codex reads the structured
prompt on stdin and returns plain text. We grep for APPROVED / NEEDS_CHANGES
markers in its response.

Codex auth is via Brian's existing ChatGPT Pro plan — no API key handling here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class AuditResult:
    verdict: str            # "APPROVED" | "NEEDS_CHANGES" | "ERROR"
    feedback: str           # raw Codex response (trimmed)
    raw_stdout: str
    raw_stderr: str


_VERDICT_RE = re.compile(r"\b(APPROVED|NEEDS_CHANGES)\b")


PROMPT_TEMPLATE = """You are auditing an AI-generated patch against a ticket spec for the Urban Hazard Maps project (Astro SSR + React islands; plain CSS via global.css with custom properties — NO Tailwind, NO CSS framework). Be terse and adversarial.

When auditing styling, REJECT any patch that uses utility-class CSS frameworks (Tailwind, UnoCSS, etc.) — this project does not have a processor for those classes and they will render as no-ops. Components style via className with project-defined CSS classes (see global.css) or inline `style={{}}` for one-offs.

When a patch regenerates an existing file in full (rather than a focused edit), diff the regenerated file against the original and flag ANY change OUTSIDE the scope the brief authorized. Transcription errors (lost characters, mangled selectors, dropped semicolons in CSS, paraphrased comments) are common in full-file output mode and acceptance criteria do not catch them. Treat unintended changes as failures.

Repo conventions (excerpt):
{conventions}

Ticket: {ticket_id}

ORIGINAL ticket source — this is the ground truth. The diff must satisfy
every acceptance bullet here, not just the narrowed brief below. If items
were silently dropped, call them out:
---
{source_ticket}
---

Mechanical brief that was sent to the patch generator (may be narrower than
the source ticket on purpose, but call out any silently-dropped scope):
{brief}

Narrowed acceptance criteria sent to the generator:
{acceptance}

Scope note from the orchestrator operator (explains intentional narrowing
of scope vs the source ticket — what was deferred and why). If this is
non-empty, treat the items it lists as out-of-scope-by-design rather than
silent drops, and verdict only on the in-scope work:
---
{scope_note}
---

Proposed unified diff:
```
{diff}
```

Decide: does this diff satisfy the in-scope work (source ticket
acceptance MINUS the items the scope_note explicitly defers), follow repo
conventions, avoid introducing security or correctness regressions, and
look like code a human reviewer would approve? If the brief silently
dropped scope that the scope_note does NOT cover, that is grounds for
NEEDS_CHANGES.

Output exactly one of:
- `APPROVED` — short rationale on the next line, max 2 sentences.
- `NEEDS_CHANGES` — bullet list of concrete fixes, each one actionable.

Do not output anything else.
"""


def _ensure_codex_available() -> str:
    path = shutil.which("codex")
    if not path:
        raise RuntimeError("codex CLI not on PATH (expected /opt/homebrew/bin/codex)")
    return path


def audit(
    *,
    ticket_id: str,
    brief: str,
    acceptance: list[str],
    diff: str,
    conventions: str,
    source_ticket: str = "",
    scope_note: str = "",
    timeout: int = 300,
) -> AuditResult:
    codex = _ensure_codex_available()
    prompt = PROMPT_TEMPLATE.format(
        conventions=conventions[:3000],
        ticket_id=ticket_id,
        source_ticket=source_ticket[:8000] or "(no source ticket file provided)",
        brief=brief,
        acceptance="\n".join(f"- {c}" for c in acceptance),
        scope_note=scope_note.strip() or "(no scope_note set — full source ticket scope expected)",
        diff=diff[:50_000],
    )
    try:
        proc = subprocess.run(
            [codex, "exec", "--skip-git-repo-check", "-"],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return AuditResult(
            verdict="ERROR",
            feedback=f"codex timeout after {timeout}s",
            raw_stdout=e.stdout or "",
            raw_stderr=e.stderr or "",
        )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    verdict_match = _VERDICT_RE.search(stdout)
    verdict = verdict_match.group(1) if verdict_match else "ERROR"

    return AuditResult(
        verdict=verdict,
        feedback=stdout.strip(),
        raw_stdout=stdout,
        raw_stderr=stderr,
    )
