# Copyright (c) Microsoft. All rights reserved.

import json
import unittest
from unittest.mock import patch

from taskmarket_client import TaskMarketClient, TaskMarketError


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class TaskMarketClientTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_discovery_filters_and_normalizes_rewards(self, urlopen: object) -> None:
        urlopen.return_value = FakeResponse(
            [
                {"id": "0x" + "a" * 64, "description": "# Small task\\nagent tooling", "reward": "500000"},
                {
                    "id": "0x" + "b" * 64,
                    "description": "# Agent integration\\nBuild a tool",
                    "reward": "2000000",
                    "tags": ["agents"],
                },
            ]
        )

        tasks = TaskMarketClient().discover_tasks(query="integration", min_reward_usdc=1, limit=5)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Agent integration")
        self.assertEqual(tasks[0]["reward_usdc"], "2")

    def test_invalid_task_id_is_rejected_before_network_access(self) -> None:
        with self.assertRaisesRegex(TaskMarketError, "32-byte"):
            TaskMarketClient().get_task("not-an-id")

    @patch("urllib.request.urlopen")
    def test_exact_task_is_read_only(self, urlopen: object) -> None:
        task_id = "0x" + "c" * 64
        urlopen.return_value = FakeResponse({"id": task_id, "reward": "1000000", "status": "open"})

        task = TaskMarketClient().get_task(task_id)

        self.assertEqual(task["id"], task_id)
        self.assertEqual(task["reward_usdc"], "1")
        urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
