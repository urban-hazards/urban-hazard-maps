"""Frontend build smoke check on a worktree."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BuildResult:
    ok: bool
    stage: str          # "install" | "build" | "ok"
    stdout_tail: str
    stderr_tail: str


def _run(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def run_frontend_build(worktree: Path, *, timeout_install: int = 300, timeout_build: int = 300) -> BuildResult:
    frontend = worktree / "frontend"
    if not frontend.exists():
        return BuildResult(ok=False, stage="setup", stdout_tail="", stderr_tail="no frontend/ dir")

    install = _run(["pnpm", "install", "--frozen-lockfile"], frontend, timeout_install)
    if install.returncode != 0:
        return BuildResult(
            ok=False,
            stage="install",
            stdout_tail=install.stdout[-1500:],
            stderr_tail=install.stderr[-1500:],
        )

    build = _run(["pnpm", "build"], frontend, timeout_build)
    if build.returncode != 0:
        return BuildResult(
            ok=False,
            stage="build",
            stdout_tail=build.stdout[-1500:],
            stderr_tail=build.stderr[-1500:],
        )
    return BuildResult(ok=True, stage="ok", stdout_tail=build.stdout[-500:], stderr_tail="")


def apply_unified_diff(worktree: Path, diff_text: str) -> tuple[bool, str]:
    """Apply a unified diff to the worktree using `git apply`.

    Uses --recount to tolerate the off-by-one hunk-header errors LLM diffs
    commonly produce, --whitespace=fix for tabs-vs-spaces minor drift, and
    --3way as a final fallback. After a successful apply, every change
    (including new files) is staged so `git diff --cached` shows the full
    change set.
    """
    proc = subprocess.run(
        ["git", "apply", "--recount", "--whitespace=fix", "-"],
        cwd=str(worktree),
        input=diff_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        # Last-ditch retry with three-way merge enabled.
        proc = subprocess.run(
            ["git", "apply", "--recount", "--whitespace=fix", "--3way", "-"],
            cwd=str(worktree),
            input=diff_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            return False, (proc.stderr.strip() or proc.stdout.strip())[:1500]

    add = subprocess.run(
        ["git", "add", "-A"],
        cwd=str(worktree),
        text=True,
        capture_output=True,
        check=False,
    )
    if add.returncode != 0:
        return False, add.stderr.strip() or "git add -A failed"
    return True, ""
