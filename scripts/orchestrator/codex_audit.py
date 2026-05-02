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


PROMPT_TEMPLATE = """You are auditing an AI-generated patch against a ticket spec for the Urban Hazard Maps project (Astro + React + TailwindCSS). Be terse and adversarial.

Repo conventions (excerpt):
{conventions}

Ticket: {ticket_id}
Mechanical brief:
{brief}

Acceptance criteria:
{acceptance}

Proposed unified diff:
```
{diff}
```

Decide: does this diff satisfy the acceptance criteria, follow repo conventions, avoid introducing security or correctness regressions, and look like code a human reviewer would approve?

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
    timeout: int = 300,
) -> AuditResult:
    codex = _ensure_codex_available()
    prompt = PROMPT_TEMPLATE.format(
        conventions=conventions[:3000],
        ticket_id=ticket_id,
        brief=brief,
        acceptance="\n".join(f"- {c}" for c in acceptance),
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
