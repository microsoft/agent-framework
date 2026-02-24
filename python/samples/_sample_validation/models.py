# Copyright (c) Microsoft. All rights reserved.

"""Data models for the sample validation system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from agent_framework import Workflow
from agent_framework.github import GitHubCopilotAgent


@dataclass
class ValidationConfig:
    """Configuration for the validation workflow."""

    samples_dir: Path
    python_root: Path
    subdir: str | None = None
    max_parallel_workers: int = 10


@dataclass
class SampleInfo:
    """Information about a discovered sample file."""

    path: Path
    relative_path: str
    code: str

    @classmethod
    def from_path(cls, path: Path, samples_dir: Path) -> "SampleInfo":
        """Create SampleInfo from a file path."""
        return cls(
            path=path,
            relative_path=str(path.relative_to(samples_dir)),
            code=path.read_text(encoding="utf-8"),
        )


@dataclass
class DiscoveryResult:
    """Result of sample discovery."""

    samples: list[SampleInfo]


@dataclass
class WorkflowCreationResult:
    """Result of creating a nested per-sample concurrent workflow."""

    samples: list[SampleInfo]
    workflow: Workflow | None
    agents: list[GitHubCopilotAgent]


class RunStatus(Enum):
    """Status of a sample run."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class RunResult:
    """Result of running a single sample."""

    sample: SampleInfo
    status: RunStatus
    output: str
    error: str


@dataclass
class ExecutionResult:
    """Result of sample execution."""

    results: list[RunResult]


@dataclass
class Report:
    """Final validation report."""

    timestamp: datetime
    total_samples: int
    success_count: int
    failure_count: int
    timeout_count: int
    error_count: int
    results: list[RunResult] = field(default_factory=list)  # type: ignore

    def to_markdown(self) -> str:
        """Generate a markdown report."""
        lines = [
            "# Sample Validation Report",
            "",
            f"**Generated:** {self.timestamp.isoformat()}",
            "",
            "## Summary",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Total Samples | {self.total_samples} |",
            f"| [PASS] Success | {self.success_count} |",
            f"| [FAIL] Failure | {self.failure_count} |",
            f"| [TIMEOUT] Timeout | {self.timeout_count} |",
            f"| [ERROR] Error | {self.error_count} |",
            "",
            "## Detailed Results",
            "",
        ]

        # Group by status
        for status in [RunStatus.FAILURE, RunStatus.TIMEOUT, RunStatus.ERROR, RunStatus.SUCCESS]:
            status_results = [r for r in self.results if r.status == status]
            if not status_results:
                continue

            status_label = {
                RunStatus.SUCCESS: "[PASS]",
                RunStatus.FAILURE: "[FAIL]",
                RunStatus.TIMEOUT: "[TIMEOUT]",
                RunStatus.ERROR: "[ERROR]",
            }

            lines.append(f"### {status_label[status]} {status.value.title()} ({len(status_results)})")
            lines.append("")

            for result in status_results:
                lines.append(f"- **{result.sample.relative_path}**")
                if result.error:
                    # Truncate long errors
                    error_preview = result.error[:200] + "..." if len(result.error) > 200 else result.error
                    lines.append(f"  - Error: `{error_preview}`")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "summary": {
                "total_samples": self.total_samples,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "timeout_count": self.timeout_count,
                "error_count": self.error_count,
            },
            "results": [
                {
                    "path": r.sample.relative_path,
                    "status": r.status.value,
                    "output": r.output,
                    "error": r.error,
                }
                for r in self.results
            ],
        }
