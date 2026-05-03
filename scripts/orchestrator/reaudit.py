"""Re-audit existing kimi/* PR branches against their source tickets.

Use this after a brief or audit-prompt change to re-check work that was
already merged into the kimi/<id> branches without re-spending Kimi tokens.
Reads the actual current state of each branch (HEAD), the source ticket
markdown, and the manifest entry, then runs codex_audit.audit() with the
current PROMPT_TEMPLATE.

Usage:
    uv run --with pyyaml python scripts/orchestrator/reaudit.py G1a A1 A2 B4 C1
    uv run --with pyyaml python scripts/orchestrator/reaudit.py --wave 1
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import yaml

from codex_audit import audit

REPO_ROOT = Path(__file__).resolve().parents[2]
TICKETS_YML = Path(__file__).parent / "tickets.yml"
LOGS_DIR = Path(__file__).parent / "logs"

CONVENTIONS = """
Frontend: Astro SSR + React islands, TypeScript strict, no semicolons, tabs.
Linter: Biome. CSS: plain global.css with CSS custom properties (no Tailwind,
no CSS framework). React components style via className with project-defined
CSS classes or inline style={{}} for one-offs (see HourlyChart.tsx for the
chip/button pattern).
Pipeline: Python 3.12+, ruff, mypy strict, uv.
""".strip()


def _diff_against_main(branch: str) -> str:
    # origin/main, not local main — local main may be stale and that distorts
    # the diff with phantom commits like #90's gate change.
    subprocess.run(
        ["git", "fetch", "origin", "main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    res = subprocess.run(
        ["git", "diff", f"origin/main...{branch}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout


def _load_tickets() -> list[dict]:
    with TICKETS_YML.open() as f:
        return yaml.safe_load(f)["tickets"]


def _branch_exists(branch: str) -> bool:
    """True if `branch` resolves locally OR on origin."""
    for ref in (branch, f"origin/{branch}"):
        res = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            return True
    return False


# Statuses where a kimi/<id> branch is expected to exist (open PR or in flight).
# stub/held/done are skipped — stub/held have no branch yet, done branches are
# typically deleted on merge.
DISPATCHABLE_STATUSES = {"pending"}


def reaudit(ticket_ids: list[str]) -> dict[str, str]:
    tickets = {t["id"]: t for t in _load_tickets()}
    verdicts: dict[str, str] = {}

    for tid in ticket_ids:
        if tid not in tickets:
            print(f"[{tid}] not in tickets.yml — skipping")
            continue

        t = tickets[tid]
        status = t.get("status", "pending")
        branch = f"kimi/{tid}"

        if status not in DISPATCHABLE_STATUSES:
            print(f"[{tid}] status={status} — skipping (no open kimi branch expected)")
            verdicts[tid] = "SKIPPED"
            continue
        if not _branch_exists(branch):
            print(f"[{tid}] branch {branch} not found — skipping")
            verdicts[tid] = "SKIPPED"
            continue

        source_path = Path(t["ticket_source"])
        source_text = source_path.read_text() if source_path.exists() else ""

        try:
            diff = _diff_against_main(branch)
        except subprocess.CalledProcessError as e:
            print(f"[{tid}] git diff failed: {e.stderr}")
            verdicts[tid] = "ERROR"
            continue

        if not diff.strip():
            print(f"[{tid}] empty diff — skipping (branch not ahead of main?)")
            verdicts[tid] = "EMPTY"
            continue

        print(f"[{tid}] auditing diff ({len(diff)} bytes)...")
        result = audit(
            ticket_id=tid,
            brief=t.get("kimi_brief", ""),
            acceptance=t.get("acceptance", []),
            diff=diff,
            conventions=CONVENTIONS,
            source_ticket=source_text,
            scope_note=t.get("scope_note", ""),
        )

        # Persist alongside the original audit logs
        log_dir = LOGS_DIR / tid
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "audit_reaudit.txt").write_text(result.feedback)

        verdicts[tid] = result.verdict
        print(f"[{tid}] {result.verdict}")
        print(result.feedback)
        print("---")

    return verdicts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ids", nargs="*", help="Ticket ids to re-audit")
    parser.add_argument("--wave", type=int, help="Re-audit all tickets in this wave")
    args = parser.parse_args()

    if args.wave:
        all_tickets = _load_tickets()
        ids = [t["id"] for t in all_tickets if t.get("wave") == args.wave]
    else:
        ids = args.ids

    if not ids:
        parser.error("Pass ticket ids or --wave N")

    verdicts = reaudit(ids)
    print()
    print("Summary:")
    print(json.dumps(verdicts, indent=2))


if __name__ == "__main__":
    main()
