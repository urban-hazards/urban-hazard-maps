r"""Entry point for the Kimi+Codex ticket orchestrator.

Reads tickets.yml, runs the per-ticket pipeline:

  build payload (scrub) -> Kimi -> apply diff -> verify build -> Codex audit
                       \-> retry once on build/codex failure -> draft PR

Hard guardrails:
- Per-call: 25K input / 4K output max.
- Per-ticket: $0.05 cumulative cap.
- Per-wave: refuses to start if projected spend > $0.30 without --budget-override.
- Live watchdog: pauses at $0.20 wave spend.
- Scrubber tests must pass before any wave dispatch.

See scrub.py for the security gateway.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from codex_audit import audit  # noqa: E402
from kimi_client import (  # noqa: E402
    PER_CALL_INPUT_TOKEN_CEILING,
    BudgetExceeded,
    KimiClient,
    KimiError,
    TicketBudget,
)
from scrub import (  # noqa: E402
    Payload,
    ScrubError,
    build_payload,
    payload_token_count,
)
from verify import apply_unified_diff, run_frontend_build  # noqa: E402
from worktree import cleanup_worktree, create_worktree, diff_against_base, reset_worktree  # noqa: E402

REPO_ROOT = HERE.parent.parent
LOGS = HERE / "logs"
WAVE_LIVE_WATCHDOG_USD = 3.00
WAVE_PROJECTED_CAP_USD = 5.00
PER_TICKET_RETRY_LIMIT = 2

KIMI_SYSTEM = """You are a careful frontend engineer working on the Boston Urban Hazard Maps repo (Astro SSR + React + TailwindCSS + TypeScript with no semicolons, tabs for indentation, Biome lint).

Output protocol — strict, no exceptions:
- For every file you modify or create, emit a single block in this exact form:

    <<<FILE: relative/path/to/file.ext>>>
    ... complete new file contents go here ...
    <<<END>>>

- Use the COMPLETE new file contents, not a diff. If you change one line in a 100-line file, output all 100 lines with that one line changed.
- Each file gets exactly one block. Multiple files = multiple blocks, back to back.
- The path between FILE: and >>> must be the relative path I gave you in the allow-list.
- No prose before, between, or after the blocks. No markdown fences. No commentary. No "here is the file" prefaces.
- If a file is unchanged, do NOT emit a block for it.
- Keep edits minimal and scoped to files I listed. Do not touch any other file."""

FILE_BLOCK_RE = re.compile(r"<<<FILE:\s*(.+?)>>>\n(.*?)\n<<<END>>>", re.DOTALL)


def parse_file_blocks(text: str, allowed: set[str]) -> tuple[dict[str, str], list[str]]:
    """Returns ({path: contents}, [errors])."""
    matches = FILE_BLOCK_RE.findall(text)
    if not matches:
        return {}, ["no <<<FILE: ...>>> blocks found in response"]
    files: dict[str, str] = {}
    errors: list[str] = []
    for path, contents in matches:
        path = path.strip()
        if path not in allowed:
            errors.append(f"file {path!r} not in allow-list")
            continue
        files[path] = contents
    return files, errors


def write_files_to_worktree(worktree: Path, files: dict[str, str]) -> tuple[bool, str]:
    for rel, contents in files.items():
        target = worktree / rel
        if not str(target.resolve()).startswith(str(worktree.resolve())):
            return False, f"path escape: {rel!r}"
        target.parent.mkdir(parents=True, exist_ok=True)
        # Ensure trailing newline so editor diffs and biome are happy
        if contents and not contents.endswith("\n"):
            contents = contents + "\n"
        target.write_text(contents, encoding="utf-8")
    add = subprocess.run(
        ["git", "add", "-A"], cwd=str(worktree), text=True, capture_output=True, check=False
    )
    if add.returncode != 0:
        return False, add.stderr.strip()
    return True, ""


@dataclass
class Ticket:
    id: str
    wave: int
    status: str
    ticket_source: str
    kimi_brief: str
    acceptance: list[str]
    allowed_files: list[str]
    depends_on: list[str]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Ticket":
        return cls(
            id=raw["id"],
            wave=int(raw.get("wave", 1)),
            status=raw.get("status", "pending"),
            ticket_source=raw.get("ticket_source", ""),
            kimi_brief=raw.get("kimi_brief", "") or "",
            acceptance=list(raw.get("acceptance") or []),
            allowed_files=list(raw.get("allowed_files") or []),
            depends_on=list(raw.get("depends_on") or []),
        )


def load_manifest(path: Path) -> list[Ticket]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Ticket.from_dict(t) for t in raw["tickets"]]


def claude_md_excerpt() -> str:
    p = REPO_ROOT / "CLAUDE.md"
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")[:3000]


def render_user_prompt(payload: Payload) -> str:
    parts = [
        f"# Ticket {payload.ticket_id}",
        "",
        "## Mechanical brief",
        payload.instructions.strip(),
        "",
        "## Acceptance criteria",
        *(f"- {c}" for c in payload.acceptance),
        "",
        "## Allowed files",
    ]
    for path, contents in payload.files.items():
        parts.append("")
        parts.append(f"### {path}")
        if contents:
            parts.append("```")
            parts.append(contents)
            parts.append("```")
        else:
            parts.append("(file does not exist yet — create it)")
    parts.append("")
    parts.append(
        "Now output one <<<FILE: path>>>...<<<END>>> block per modified or "
        "created file. Complete file contents only — no diffs, no fences, "
        "no prose."
    )
    return "\n".join(parts)


def run_scrubber_tests() -> None:
    proc = subprocess.run(
        ["uv", "run", "--with", "pytest", "python", "-m", "pytest",
         str(HERE / "tests" / "test_scrub.py"), "-q"],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr + "\n")
        raise SystemExit("scrubber tests failed — refusing to dispatch")


def write_log(ticket_id: str, name: str, content: str | dict) -> Path:
    d = LOGS / ticket_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    if isinstance(content, dict):
        p.write_text(json.dumps(content, indent=2, default=str), encoding="utf-8")
    else:
        p.write_text(content, encoding="utf-8")
    return p


def dispatch_one(ticket: Ticket, *, print_payload_only: bool, allow_no_key: bool) -> dict:
    if ticket.status == "stub":
        raise SystemExit(f"ticket {ticket.id} has no kimi_brief authored yet")
    if ticket.status == "held":
        raise SystemExit(f"ticket {ticket.id} is held; not eligible for dispatch")
    if ticket.status == "done":
        raise SystemExit(f"ticket {ticket.id} already done; skip or change status")

    payload = build_payload(
        ticket_id=ticket.id,
        kimi_brief=ticket.kimi_brief or None,
        ticket_source=ticket.ticket_source if not ticket.kimi_brief else None,
        acceptance=ticket.acceptance,
        allowed_files=ticket.allowed_files,
        repo_root=REPO_ROOT,
    )
    write_log(ticket.id, "payload.json", payload.to_logged_dict())
    write_log(ticket.id, "redactions.json", {
        "redactions": [r.__dict__ for r in payload.redactions],
        "stripped_sections": payload.stripped_sections,
    })

    user_prompt = render_user_prompt(payload)
    write_log(ticket.id, "kimi_user_prompt.txt", user_prompt)
    write_log(ticket.id, "kimi_system_prompt.txt", KIMI_SYSTEM)

    approx_input = payload_token_count(payload) + 800   # +800 for system prompt
    if approx_input > PER_CALL_INPUT_TOKEN_CEILING:
        raise SystemExit(
            f"ticket {ticket.id}: approx input tokens {approx_input} > ceiling "
            f"{PER_CALL_INPUT_TOKEN_CEILING}. Narrow allowed_files."
        )

    summary: dict = {
        "ticket_id": ticket.id,
        "approx_input_tokens": approx_input,
        "redaction_counts": {r.name: r.count for r in payload.redactions},
        "stripped_sections": payload.stripped_sections,
    }

    if print_payload_only:
        summary["mode"] = "print-payload (no Kimi call)"
        write_log(ticket.id, "summary.json", summary)
        return summary

    if not os.environ.get("OPENROUTER_API_KEY"):
        if allow_no_key:
            summary["mode"] = "missing OPENROUTER_API_KEY (skipped)"
            write_log(ticket.id, "summary.json", summary)
            return summary
        raise SystemExit("OPENROUTER_API_KEY not set; export it or use --print-payload")

    client = KimiClient()
    budget = TicketBudget(ticket_id=ticket.id)
    worktree = create_worktree(REPO_ROOT, ticket.id)

    feedback_for_kimi = ""
    final_diff = ""
    final_audit = None
    iteration = 0

    while iteration <= PER_TICKET_RETRY_LIMIT:
        iteration += 1
        prompt = user_prompt
        if feedback_for_kimi:
            prompt += "\n\n## Reviewer feedback from previous attempt — address these:\n" + feedback_for_kimi

        try:
            content, usage = client.call(
                ticket_budget=budget,
                system=KIMI_SYSTEM,
                user=prompt,
                approx_input_tokens=approx_input,
            )
        except (BudgetExceeded, KimiError) as e:
            raw = getattr(client, "_last_raw_payload", None)
            if raw is not None:
                write_log(ticket.id, f"kimi_raw_{iteration}.json", raw)
            summary["error"] = f"kimi: {e}"
            summary["spent_usd"] = round(budget.spent_usd, 6)
            write_log(ticket.id, "usage.json", budget.as_dict())
            break

        write_log(ticket.id, f"kimi_response_{iteration}.txt", content)
        write_log(ticket.id, "usage.json", budget.as_dict())

        files, parse_errors = parse_file_blocks(content, set(ticket.allowed_files))
        if parse_errors:
            write_log(ticket.id, f"parse_errors_{iteration}.txt", "\n".join(parse_errors))
        if not files:
            feedback_for_kimi = (
                "Your response contained no valid <<<FILE: path>>>...<<<END>>> blocks. "
                "Re-emit, with one block per file, complete contents inside, no prose, "
                "no fences, no commentary. Path must match the allow-list exactly."
            )
            continue

        ok, msg = write_files_to_worktree(worktree, files)
        if not ok:
            feedback_for_kimi = f"file write failed: {msg}\nRe-emit using the protocol exactly."
            write_log(ticket.id, f"apply_error_{iteration}.txt", msg)
            continue

        build = run_frontend_build(worktree)
        write_log(ticket.id, f"build_{iteration}.json", {
            "ok": build.ok, "stage": build.stage,
            "stdout_tail": build.stdout_tail, "stderr_tail": build.stderr_tail,
        })
        if not build.ok:
            feedback_for_kimi = (
                f"pnpm {build.stage} failed:\n{build.stderr_tail}\n"
                f"Fix the diff so the build is clean."
            )
            reset_worktree(worktree)
            continue

        final_diff = diff_against_base(worktree)
        audit_result = audit(
            ticket_id=ticket.id,
            brief=payload.instructions,
            acceptance=payload.acceptance,
            diff=final_diff,
            conventions=claude_md_excerpt(),
        )
        write_log(ticket.id, f"audit_{iteration}.txt", audit_result.feedback)
        final_audit = audit_result

        if audit_result.verdict == "APPROVED":
            break
        if audit_result.verdict == "NEEDS_CHANGES":
            feedback_for_kimi = audit_result.feedback
            # Only roll back if we have retries left. Otherwise keep the last
            # working diff in the worktree so the human reviewer can pick up
            # from it — losing it forces a re-dispatch.
            if iteration <= PER_TICKET_RETRY_LIMIT:
                reset_worktree(worktree)
                continue
            break
        # ERROR verdict — bail to manual review
        break

    summary.update({
        "spent_usd": round(budget.spent_usd, 6),
        "iterations": iteration,
        "audit_verdict": final_audit.verdict if final_audit else None,
        "diff_bytes": len(final_diff),
        "worktree": str(worktree),
    })
    write_log(ticket.id, "summary.json", summary)
    return summary




def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticket", help="Run a single ticket id.")
    parser.add_argument("--wave", type=int, help="Run all pending tickets in this wave.")
    parser.add_argument("--print-payload", action="store_true",
                        help="Build and log the scrubbed payload but skip the Kimi call.")
    parser.add_argument("--budget-override", action="store_true",
                        help="Allow waves whose projected spend exceeds the cap.")
    parser.add_argument("--allow-no-key", action="store_true",
                        help="Continue (with warning) when OPENROUTER_API_KEY is missing — print-payload only.")
    parser.add_argument("--manifest", default=str(HERE / "tickets.yml"))
    args = parser.parse_args(argv)

    if not args.ticket and args.wave is None:
        parser.error("specify --ticket <id> or --wave <n>")

    # Pre-flight: scrubber tests must pass for any path that hits Kimi.
    if not args.print_payload:
        run_scrubber_tests()

    tickets = load_manifest(Path(args.manifest))

    if args.ticket:
        target = next((t for t in tickets if t.id == args.ticket), None)
        if not target:
            parser.error(f"unknown ticket {args.ticket!r}")
        summary = dispatch_one(target, print_payload_only=args.print_payload, allow_no_key=args.allow_no_key)
        print(json.dumps(summary, indent=2, default=str))
        return 0

    wave_tickets = [t for t in tickets if t.wave == args.wave and t.status == "pending"]
    skipped_done = [t.id for t in tickets if t.wave == args.wave and t.status == "done"]
    if skipped_done:
        print(f"skipping already-done in wave {args.wave}: {', '.join(skipped_done)}")
    if not wave_tickets:
        print(f"no pending tickets in wave {args.wave}")
        return 0

    projected = len(wave_tickets) * 0.05
    if projected > WAVE_PROJECTED_CAP_USD and not args.budget_override:
        parser.error(
            f"wave {args.wave}: projected ${projected:.2f} exceeds cap "
            f"${WAVE_PROJECTED_CAP_USD:.2f}. Pass --budget-override to proceed."
        )

    wave_total = 0.0
    summaries = []
    for t in wave_tickets:
        s = dispatch_one(t, print_payload_only=args.print_payload, allow_no_key=args.allow_no_key)
        summaries.append(s)
        wave_total += float(s.get("spent_usd", 0.0))
        if wave_total > WAVE_LIVE_WATCHDOG_USD:
            print(f"watchdog: wave spend ${wave_total:.4f} crossed ${WAVE_LIVE_WATCHDOG_USD:.2f}")
            print("pausing — re-run remaining tickets manually with --ticket if you want to continue")
            break

    print(json.dumps({"wave": args.wave, "spent_usd": round(wave_total, 6), "summaries": summaries}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
