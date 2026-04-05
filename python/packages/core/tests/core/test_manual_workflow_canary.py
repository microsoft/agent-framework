import os
import subprocess
from pathlib import Path


def _git_output(*args: str) -> str:
    repo_root = next((parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()), None)
    try:
        completed = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
    except Exception:
        return "unavailable"

    value = completed.stdout.strip()
    return value or "empty"


def test_manual_workflow_canary() -> None:
    """Safe canary for privileged manual workflow execution."""
    marker = (
        "AF_CANARY "
        f"event={os.getenv('GITHUB_EVENT_NAME', 'none')} "
        f"workflow={os.getenv('GITHUB_WORKFLOW', 'none')} "
        f"run_id={os.getenv('GITHUB_RUN_ID', 'none')} "
        f"head={_git_output('rev-parse', 'HEAD')}"
    )
    print(marker)

    # Safe proof only: fail inside reusable workflow runs so the marker is easy
    # to recover from logs, without touching secrets or external services.
    if os.getenv("GITHUB_ACTIONS") == "true" and os.getenv("GITHUB_EVENT_NAME") == "workflow_call":
        assert False, marker
