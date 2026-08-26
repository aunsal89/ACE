"""Automated Git Commit & Push utility for Career Engine results."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.utils.logger import console, logger


def auto_git_commit_and_push(
    repo_root: Optional[Path] = None,
    staged_packages_count: int = 0,
    commit_msg_prefix: str = "chore(inbox)"
) -> bool:
    """
    Automatically commits and pushes staged application packages in inbox/
    and updated SQLite database state so results can be pulled remotely from any machine.
    """
    if repo_root is None:
        # Default to Portfolio root (two levels above this file's folder)
        repo_root = Path(__file__).resolve().parent.parent.parent.parent

    date_str = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # Check git status
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15
        )
        if status_proc.returncode != 0:
            logger.warning(f"Git status check failed: {status_proc.stderr}")
            return False

        changes = status_proc.stdout.strip()
        if not changes:
            console.print("[dim]Git sync: No changes to commit.[/dim]")
            return True

        # Check if inbox or data was modified
        relevant_changes = any(
            line for line in changes.splitlines()
            if "career-engine/inbox" in line or "career-engine/data" in line or "inbox" in line
        )

        if not relevant_changes and staged_packages_count == 0:
            console.print("[dim]Git sync: No inbox packages or data changes to sync.[/dim]")
            return True

        # Stage inbox and data files
        subprocess.run(
            ["git", "add", "career-engine/inbox", "career-engine/data"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            timeout=20
        )

        # Check if anything is staged
        diff_cached = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(repo_root),
            timeout=10
        )
        if diff_cached.returncode == 0:
            console.print("[dim]Git sync: Nothing staged for commit.[/dim]")
            return True

        # Commit
        if staged_packages_count > 0:
            msg = f"{commit_msg_prefix}: auto-stage {staged_packages_count} application package(s) [{date_str}]"
        else:
            msg = f"{commit_msg_prefix}: update career engine database state [{date_str}]"

        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            timeout=20
        )
        console.print(f"[bold green]✓ Git commit created:[/bold green] {msg}")

        # Push
        console.print("[cyan]Pushing staged changes to remote origin/main...[/cyan]")
        push_proc = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=45
        )
        if push_proc.returncode == 0:
            console.print("[bold green]✓ Git push succeeded! Results are available remotely on GitHub.[/bold green]")
            return True
        else:
            console.print(f"[yellow]⚠ Git push failed (non-fatal): {push_proc.stderr.strip()}[/yellow]")
            return False

    except subprocess.TimeoutExpired:
        logger.warning("Git sync timed out. Skipping remote push.")
        return False
    except Exception as e:
        logger.warning(f"Git sync encountered an error: {e}")
        return False
