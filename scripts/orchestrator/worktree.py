"""Per-ticket git worktree management."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

WORKTREE_ROOT = Path("/tmp/uhm_work")


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def create_worktree(repo_root: Path, ticket_id: str, base: str = "origin/main") -> Path:
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    path = WORKTREE_ROOT / ticket_id
    if path.exists():
        cleanup_worktree(repo_root, ticket_id)
    branch = f"kimi/{ticket_id}"

    # If branch already exists from a previous run, delete it for a clean slate.
    existing = _git("branch", "--list", branch, cwd=repo_root)
    if existing.stdout.strip():
        _git("branch", "-D", branch, cwd=repo_root)

    proc = _git("worktree", "add", "-b", branch, str(path), base, cwd=repo_root)
    if proc.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {proc.stderr.strip()}")
    return path


def cleanup_worktree(repo_root: Path, ticket_id: str) -> None:
    path = WORKTREE_ROOT / ticket_id
    if path.exists():
        _git("worktree", "remove", "--force", str(path), cwd=repo_root)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def diff_against_base(worktree: Path, base: str = "origin/main") -> str:
    """Diff including staged-but-uncommitted changes (which is how we capture
    new files after `git apply` + `git add -A`)."""
    proc = _git("diff", "--cached", base, "--", ".", cwd=worktree)
    if proc.returncode != 0:
        raise RuntimeError(f"git diff failed: {proc.stderr.strip()}")
    return proc.stdout


def reset_worktree(worktree: Path, base: str = "origin/main") -> None:
    """Roll worktree back to base, including untracked files."""
    _git("reset", "--hard", base, cwd=worktree)
    _git("clean", "-fdx", cwd=worktree)
