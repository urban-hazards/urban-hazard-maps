"""Security gateway for outbound payloads to Kimi.

Single chokepoint: build_payload() is the only function that constructs what
gets sent. Three defenses, in order: deny-list, allow-list, regex redaction.
Plus strategy-section stripping on ticket markdown when no kimi_brief is set.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


class ScrubError(Exception):
    """Raised when payload construction would expose forbidden material."""


DENY_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "secrets.*",
    "secret.*",
    "*.config",
    "serviceAccountKey*.json",
    "credentials",
    "credentials.*",
    "*credentials*",
    ".npmrc",
    ".aws/*",
    ".ssh/*",
)


REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("openai_key",       re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),                      "[REDACTED_OPENAI_KEY]"),
    ("github_pat",       re.compile(r"\bghp_[A-Za-z0-9]{30,}"),                       "[REDACTED_GITHUB_PAT]"),
    ("github_oauth",     re.compile(r"\bgho_[A-Za-z0-9]{30,}"),                       "[REDACTED_GITHUB_OAUTH]"),
    ("aws_access_key",   re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),                  "[REDACTED_AWS_KEY]"),
    ("anthropic_key",    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),                  "[REDACTED_ANTHROPIC_KEY]"),
    ("openrouter_key",   re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}"),                  "[REDACTED_OPENROUTER_KEY]"),
    ("moonshot_key",     re.compile(r"\bsk-[A-Za-z0-9]{40,}"),                        "[REDACTED_MOONSHOT_KEY]"),
    ("jwt",              re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED_JWT]"),
    # URL/IP redaction is intentionally narrow: full-file Kimi output round-trips
    # placeholders back into source files (caught Apr 2026 on A2).
    # Public URLs in client-side source ARE public — only flag actual secrets.
    ("credentialed_url", re.compile(r"https?://[^\s/@\"'<>`]+:[^\s/@\"'<>`]+@[^\s\"'<>`)]+"), "[REDACTED_CRED_URL]"),
    ("aws_signed_url",   re.compile(r"https?://[^\s\"'<>`)]*[?&](?:Signature|X-Amz-Signature)=[^\s\"'<>`)&]+(?:[^\s\"'<>`)]*)?"), "[REDACTED_SIGNED_URL]"),
    ("internal_url",     re.compile(r"https?://(?:[a-zA-Z0-9-]+\.)*(?:internal|local|localhost|intra)(?:[/:][^\s\"'<>`)]*)?"), "[REDACTED_INTERNAL_URL]"),
    ("private_ipv4",     re.compile(r"(?<!\d)(?:10\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|172\.(?:1[6-9]|2\d|3[01])\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|192\.168\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d))(?!\d)"), "[REDACTED_PRIVATE_IPV4]"),
    ("postgres_url",     re.compile(r"postgres(?:ql)?://[^\s\"'<>`]+"),               "[REDACTED_DB_URL]"),
)


STRATEGY_HEADING = re.compile(
    r"(?im)^\s*#{1,6}\s*(strategy|roadmap|future|vulnerab|legal|internal|notes|priority|source|context)\b.*$"
)


@dataclass
class Redaction:
    name: str
    count: int


@dataclass
class Payload:
    ticket_id: str
    instructions: str           # mechanical brief that goes to Kimi
    files: dict[str, str]       # path -> scrubbed contents
    acceptance: list[str]       # acceptance criteria
    redactions: list[Redaction] = field(default_factory=list)
    stripped_sections: list[str] = field(default_factory=list)

    def to_logged_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "instructions": self.instructions,
            "files": self.files,
            "acceptance": self.acceptance,
            "redactions": [r.__dict__ for r in self.redactions],
            "stripped_sections": self.stripped_sections,
        }


def check_deny_list(path: str) -> None:
    """Reject paths that match any deny-list glob.

    Match is CASE-INSENSITIVE (so `.ENV`, `Secrets.JSON` are caught) and
    walks every path component (so nested `ops/.ssh/config` is caught even
    though the leaf name `config` looks innocuous).
    """
    p = Path(path)
    parts_lower = tuple(part.lower() for part in p.parts)
    name_lower = p.name.lower()
    for pattern in DENY_GLOBS:
        pat_lower = pattern.lower()
        # 1. leaf-name match: catches "Secrets.json" vs "secrets.*"
        if fnmatch.fnmatch(name_lower, pat_lower):
            raise ScrubError(f"deny-list: {path!r} matches {pattern!r}")
        # 2. full-path glob (for slash-bearing patterns like .aws/* or .ssh/*)
        if "/" in pat_lower:
            # match against the full path, AND against any nested suffix that
            # starts with the first segment of the pattern. Catches `ops/.ssh/config`.
            path_lower = "/".join(parts_lower)
            if fnmatch.fnmatch(path_lower, pat_lower):
                raise ScrubError(f"deny-list: {path!r} matches {pattern!r}")
            head = pat_lower.split("/", 1)[0]
            for i, segment in enumerate(parts_lower):
                if fnmatch.fnmatch(segment, head):
                    suffix = "/".join(parts_lower[i:])
                    if fnmatch.fnmatch(suffix, pat_lower):
                        raise ScrubError(
                            f"deny-list: {path!r} contains nested {pattern!r} "
                            f"(at {parts_lower[i]!r})"
                        )
        # 3. any single segment matches (catches .env nested anywhere)
        for part in parts_lower:
            if fnmatch.fnmatch(part, pat_lower):
                raise ScrubError(
                    f"deny-list: {path!r} contains denied segment {part!r} ({pattern!r})"
                )


def redact(text: str) -> tuple[str, list[Redaction]]:
    log: list[Redaction] = []
    out = text
    for name, pattern, replacement in REDACTION_PATTERNS:
        out, n = pattern.subn(replacement, out)
        if n:
            log.append(Redaction(name=name, count=n))
    return out, log


def strip_strategy_sections(markdown: str) -> tuple[str, list[str]]:
    """Drop sections under strategic/sensitive headings until the next heading."""
    lines = markdown.splitlines()
    kept: list[str] = []
    dropped: list[str] = []
    skipping = False
    skip_level = 0
    current_dropped = ""
    heading_re = re.compile(r"^\s*(#{1,6})\s+(.*)$")
    for line in lines:
        m = heading_re.match(line)
        if m:
            level = len(m.group(1))
            if STRATEGY_HEADING.match(line):
                skipping = True
                skip_level = level
                current_dropped = m.group(2).strip()
                dropped.append(current_dropped)
                continue
            if skipping and level <= skip_level:
                skipping = False
        if not skipping:
            kept.append(line)
    return "\n".join(kept).strip() + ("\n" if kept else ""), dropped


def _read_safely(repo_root: Path, rel: str) -> str:
    check_deny_list(rel)
    abs_path = (repo_root / rel).resolve()
    if not str(abs_path).startswith(str(repo_root.resolve())):
        raise ScrubError(f"path escape: {rel!r} resolves outside repo")
    if not abs_path.exists():
        # New file the ticket creates — represent as empty, no scrub needed.
        return ""
    return abs_path.read_text(encoding="utf-8", errors="replace")


def build_payload(
    *,
    ticket_id: str,
    kimi_brief: str | None,
    ticket_source: str | None,
    acceptance: list[str],
    allowed_files: Iterable[str],
    repo_root: Path,
) -> Payload:
    """Construct the scrubbed payload for one ticket.

    `kimi_brief` is the preferred mechanical instruction (manually authored).
    `ticket_source` is the path to the human-readable ticket markdown; only
    used as fallback, and only after strategy-section stripping + redaction.
    """
    if not kimi_brief and not ticket_source:
        raise ScrubError(f"ticket {ticket_id}: must provide kimi_brief or ticket_source")

    redactions: list[Redaction] = []
    stripped: list[str] = []

    if kimi_brief:
        instructions, instr_redactions = redact(kimi_brief)
        redactions.extend(instr_redactions)
    else:
        # Route ticket_source through the same gate as allowed_files.
        # Without this, a blank kimi_brief lets the manifest read any local
        # path (including secrets) and forward it to Kimi.
        ticket_path = Path(ticket_source)
        check_deny_list(str(ticket_path))
        if ticket_path.is_absolute():
            # Ticket sources live under /tmp/uhm_issues by convention. Allow
            # absolute paths only if they're under that directory or under
            # the repo root; refuse anything else.
            allowed_roots = (Path("/tmp/uhm_issues").resolve(), repo_root.resolve())
            resolved = ticket_path.resolve()
            if not any(
                str(resolved).startswith(str(root)) for root in allowed_roots
            ):
                raise ScrubError(
                    f"ticket_source {ticket_source!r} must live under "
                    f"/tmp/uhm_issues or the repo root"
                )
        raw = ticket_path.read_text(encoding="utf-8", errors="replace")
        stripped_md, dropped = strip_strategy_sections(raw)
        stripped.extend(dropped)
        instructions, instr_redactions = redact(stripped_md)
        redactions.extend(instr_redactions)

    files: dict[str, str] = {}
    for rel in allowed_files:
        contents = _read_safely(repo_root, rel)
        scrubbed, file_redactions = redact(contents)
        files[rel] = scrubbed
        redactions.extend(file_redactions)

    # Coalesce redaction counts by name for a tidy log.
    counts: dict[str, int] = {}
    for r in redactions:
        counts[r.name] = counts.get(r.name, 0) + r.count
    coalesced = [Redaction(name=n, count=c) for n, c in sorted(counts.items()) if c]

    return Payload(
        ticket_id=ticket_id,
        instructions=instructions,
        files=files,
        acceptance=list(acceptance),
        redactions=coalesced,
        stripped_sections=stripped,
    )


def approx_tokens(text: str) -> int:
    """Cheap token estimate: ~1 token per 4 chars. Conservative upper bound."""
    return max(1, (len(text) + 3) // 4)


def payload_token_count(payload: Payload) -> int:
    total = approx_tokens(payload.instructions)
    for content in payload.files.values():
        total += approx_tokens(content)
    for crit in payload.acceptance:
        total += approx_tokens(crit)
    return total
