"""Poisoned-fixture tests for scrub.py.

These run BEFORE every wave dispatch. If any of them fail, the dispatcher
refuses to start.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrub import (  # noqa: E402
    DENY_GLOBS,
    Payload,
    ScrubError,
    build_payload,
    check_deny_list,
    redact,
    strip_strategy_sections,
)


# --- deny-list ----------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        ".env.production",
        "frontend/.env",
        "config/.env.production",
        "secrets.json",
        "secret.yaml",
        "config/credentials.yaml",
        "credentials",
        "deploy/serviceAccountKey.json",
        "ops/serviceAccountKey-prod.json",
        "tls/server.pem",
        "ssh/id_rsa.key",
        "config.config",
        ".npmrc",
        ".aws/credentials",
        ".ssh/id_ed25519",
    ],
)
def test_deny_list_blocks(path: str) -> None:
    with pytest.raises(ScrubError):
        check_deny_list(path)


@pytest.mark.parametrize(
    "path",
    [
        "frontend/src/components/HeatMap.tsx",
        "frontend/src/pages/index.astro",
        "pipeline/src/boston_hazard_pipeline/__init__.py",
        "scripts/orchestrator/scrub.py",
        "README.md",
    ],
)
def test_deny_list_allows_normal_paths(path: str) -> None:
    check_deny_list(path)  # should not raise


# --- redaction ----------------------------------------------------------------


def test_redacts_openai_key() -> None:
    text = "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
    out, log = redact(text)
    assert "sk-proj-abcd" not in out
    assert "[REDACTED" in out
    assert any(r.count >= 1 for r in log)


def test_redacts_github_pat() -> None:
    text = "token: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"
    out, _ = redact(text)
    assert "ghp_aBcD" not in out


def test_redacts_aws_keys() -> None:
    text = "id=AKIAIOSFODNN7EXAMPLE secret=AKIA0000000000000000"
    out, log = redact(text)
    assert "AKIA" not in out
    assert sum(r.count for r in log if r.name == "aws_access_key") >= 1


def test_redacts_jwt() -> None:
    fake_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.SignaturePartHere1234"  # gitleaks:allow
    out, _ = redact(f"Authorization: Bearer {fake_jwt}")
    assert "eyJhbGciOi" not in out


def test_redacts_ipv4() -> None:
    text = "host: 192.168.1.42 port: 5432"
    out, _ = redact(text)
    assert "192.168.1.42" not in out


def test_redacts_absolute_urls() -> None:
    text = "fetch('https://internal.example.com/admin/api/v1/users')"
    out, _ = redact(text)
    assert "internal.example.com" not in out


def test_redacts_postgres_url() -> None:
    text = "DATABASE_URL=postgresql://user:hunter2@db.internal:5432/prod"
    out, _ = redact(text)
    assert "hunter2" not in out
    assert "db.internal" not in out


def test_redacts_anthropic_key() -> None:
    text = "key=sk-ant-api03-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABCDEF"
    out, _ = redact(text)
    assert "sk-ant-api03-aBcDeFgH" not in out


# --- strategy stripping -------------------------------------------------------


def test_strips_strategy_section() -> None:
    md = """# Title

## Problem
Real problem text.

## Strategy
Internal political angle that must NOT leak.

## Acceptance
- Build passes
"""
    out, dropped = strip_strategy_sections(md)
    assert "political angle" not in out
    assert "Strategy" in dropped
    assert "Real problem text" in out
    assert "Build passes" in out


def test_strips_notes_and_priority_and_source() -> None:
    md = """# G1a

## Problem
Add an overlay.

## Source
- Recording 24:01

## Acceptance
- ships

## Priority
Low.

## Notes
"He's a monster" — Brian on Officer Gerro.
"""
    out, dropped = strip_strategy_sections(md)
    assert "monster" not in out
    assert "Recording 24:01" not in out
    assert "Low." not in out
    assert {"Source", "Priority", "Notes"}.issubset(set(dropped))


# --- end-to-end ---------------------------------------------------------------


def test_build_payload_blocks_dotenv_in_allowed_files(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=hunter2\n")
    with pytest.raises(ScrubError):
        build_payload(
            ticket_id="X",
            kimi_brief="patch this",
            ticket_source=None,
            acceptance=["builds"],
            allowed_files=[".env"],
            repo_root=tmp_path,
        )


def test_build_payload_blocks_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ScrubError):
        build_payload(
            ticket_id="X",
            kimi_brief="patch this",
            ticket_source=None,
            acceptance=["builds"],
            allowed_files=["../etc/passwd"],
            repo_root=tmp_path,
        )


def test_build_payload_redacts_keys_in_source_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.ts").write_text(
        "export const KEY = 'sk-proj-abcdefghijklmnopqrstuvwxyz0123456789'\n"
    )
    payload = build_payload(
        ticket_id="X",
        kimi_brief="patch the config",
        ticket_source=None,
        acceptance=["builds"],
        allowed_files=["src/config.ts"],
        repo_root=tmp_path,
    )
    contents = payload.files["src/config.ts"]
    assert "sk-proj-abcdefghij" not in contents
    assert "[REDACTED" in contents


def test_build_payload_uses_kimi_brief_over_source(tmp_path: Path) -> None:
    md = tmp_path / "ticket.md"
    md.write_text("# Politically sensitive narrative\nDon't telegraph this.\n")
    payload = build_payload(
        ticket_id="X",
        kimi_brief="Add a toggle to the filter UI.",
        ticket_source=str(md),
        acceptance=["builds"],
        allowed_files=[],
        repo_root=tmp_path,
    )
    assert payload.instructions == "Add a toggle to the filter UI."
    assert "telegraph" not in payload.instructions
    assert "Politically sensitive" not in payload.instructions
