"""Tests for dispatch.py — focused on schema plumbing and status gating.

These complement the scrubber tests in test_scrub.py. They guard against
the failure mode Codex caught in the May 2026 audit: scope_note was
introduced in tickets.yml + reaudit.py + codex_audit.py but not threaded
through dispatch.py's runtime path. The regression: future ticket dispatch
audits would silently drop the operator's scope narrowing and stamp false
NEEDS_CHANGES verdicts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dispatch import Ticket, dispatch_one  # noqa: E402


# --- scope_note schema plumbing -----------------------------------------------


def test_ticket_loads_scope_note_from_dict() -> None:
    raw = {
        "id": "TEST",
        "wave": 1,
        "status": "pending",
        "ticket_source": "/tmp/uhm_issues/TEST.md",
        "kimi_brief": "do thing",
        "acceptance": ["thing done"],
        "allowed_files": ["src/foo.ts"],
        "depends_on": [],
        "scope_note": "the brief intentionally narrowed scope X because Y",
    }
    t = Ticket.from_dict(raw)
    assert t.scope_note == "the brief intentionally narrowed scope X because Y"


def test_ticket_scope_note_defaults_empty_when_absent() -> None:
    raw = {
        "id": "TEST",
        "wave": 1,
        "status": "pending",
        "ticket_source": "/tmp/uhm_issues/TEST.md",
        "kimi_brief": "do thing",
        "acceptance": [],
        "allowed_files": [],
        "depends_on": [],
        # no scope_note key
    }
    t = Ticket.from_dict(raw)
    assert t.scope_note == ""


def test_ticket_scope_note_treats_null_as_empty() -> None:
    """yaml `scope_note: null` (or `~`) round-trips to None — coerce to ''."""
    raw = {
        "id": "TEST",
        "wave": 1,
        "status": "pending",
        "ticket_source": "/tmp/uhm_issues/TEST.md",
        "kimi_brief": "do thing",
        "acceptance": [],
        "allowed_files": [],
        "depends_on": [],
        "scope_note": None,
    }
    t = Ticket.from_dict(raw)
    assert t.scope_note == ""


# --- status gating ------------------------------------------------------------


@pytest.mark.parametrize(
    "status,fragment",
    [
        ("stub", "no kimi_brief authored yet"),
        ("held", "not eligible for dispatch"),
        ("done", "already done"),
        ("manual", "marked manual"),
    ],
)
def test_dispatch_one_refuses_non_pending_statuses(
    status: str, fragment: str
) -> None:
    """All non-pending statuses must SystemExit with a clear message — never
    burn Kimi tokens on hand-applied / shipped / blocked tickets."""
    t = Ticket(
        id="T",
        wave=1,
        status=status,
        ticket_source="/tmp/uhm_issues/T.md",
        kimi_brief="x",
        acceptance=[],
        allowed_files=[],
        depends_on=[],
    )
    with pytest.raises(SystemExit) as excinfo:
        dispatch_one(t, print_payload_only=True, allow_no_key=True)
    assert fragment in str(excinfo.value)
