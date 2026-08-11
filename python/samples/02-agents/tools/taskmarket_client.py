# Copyright (c) Microsoft. All rights reserved.

"""Small, read-only client for the public TaskMarket task API.

This module deliberately contains no authentication, wallet, signing, or
mutation support. It is suitable for discovery tools that let an agent inspect
work before a human chooses whether to delegate it.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any


DEFAULT_BASE_URL = "https://api.taskmarket.dev"
TASK_ID_PATTERN = re.compile(r"^0x[0-9a-fA-F]{64}$")


class TaskMarketError(RuntimeError):
    """Raised when TaskMarket cannot return a valid public response."""


def _reward_usdc(value: Any) -> str | None:
    """Convert a TaskMarket base-unit reward to a readable USDC string."""
    if value is None:
        return None
    try:
        amount = Decimal(str(value)) / Decimal(1_000_000)
    except (InvalidOperation, ValueError):
        return None
    return format(amount, "f")


def _title(description: Any) -> str | None:
    """Use the first Markdown heading as a title when the API has no title."""
    if not isinstance(description, str):
        return None
    for line in description.replace("\\n", "\n").splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip() or None
    return None


def normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    """Return a compact, model-friendly task record without hidden credentials."""
    description = task.get("description")
    normalized_description = description.replace("\\n", "\n") if isinstance(description, str) else description
    record = {
        "id": task.get("id"),
        "title": task.get("title") or _title(normalized_description),
        "status": task.get("status"),
        "phase": task.get("phase"),
        "reward_base_units": task.get("reward"),
        "reward_usdc": _reward_usdc(task.get("reward")),
        "net_reward_base_units": task.get("netReward"),
        "expiry_time": task.get("expiryTime") or task.get("expires_at"),
        "submission_count": task.get("submissionCount"),
        "award_count": task.get("awardCount"),
        "tags": task.get("tags") or [],
        "escrow_tx_hash": task.get("escrowTxHash"),
    }
    if isinstance(normalized_description, str):
        record["description"] = normalized_description[:6000]
        record["description_truncated"] = len(normalized_description) > 6000
    return record


class TaskMarketClient:
    """Read public TaskMarket tasks without authentication or side effects."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "agent-framework-taskmarket-sample/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            raise TaskMarketError(f"TaskMarket request failed: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TaskMarketError("TaskMarket returned invalid JSON") from error

    def discover_tasks(
        self,
        query: str = "",
        min_reward_usdc: float = 0.0,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find open public tasks, filtering locally by text and reward."""
        if not 1 <= limit <= 20:
            raise TaskMarketError("limit must be between 1 and 20")
        if min_reward_usdc < 0:
            raise TaskMarketError("min_reward_usdc cannot be negative")

        payload = self._get("/api/tasks", {"status": "open", "limit": "20"})
        raw_tasks = payload if isinstance(payload, list) else payload.get("tasks", [])
        if not isinstance(raw_tasks, list):
            raise TaskMarketError("TaskMarket returned an unexpected task list")

        needle = query.strip().lower()
        results: list[dict[str, Any]] = []
        for raw_task in raw_tasks:
            if not isinstance(raw_task, dict):
                continue
            record = normalize_task(raw_task)
            haystack = " ".join(
                [
                    str(record.get("title") or ""),
                    str(record.get("description") or ""),
                    " ".join(str(tag) for tag in record.get("tags", [])),
                ]
            ).lower()
            reward = Decimal(record["reward_usdc"] or "0")
            if needle and needle not in haystack:
                continue
            if reward < Decimal(str(min_reward_usdc)):
                continue
            results.append(record)
            if len(results) == limit:
                break
        return results

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Inspect one exact public task after validating its immutable ID format."""
        if not TASK_ID_PATTERN.fullmatch(task_id):
            raise TaskMarketError("task_id must be a 32-byte 0x-prefixed hexadecimal ID")
        payload = self._get(f"/api/tasks/{task_id}")
        if not isinstance(payload, dict):
            raise TaskMarketError("TaskMarket returned an unexpected task record")
        return normalize_task(payload)
