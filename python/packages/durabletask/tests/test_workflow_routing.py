# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for synchronous edge-condition evaluation on the durabletask host.

Durable orchestrators run as generators and evaluate edge conditions
synchronously. A condition that returns an awaitable cannot be evaluated in
that context, so the edge is treated as *not matched* (not traversed).
"""

from agent_framework._workflows._edge import Edge  # pyright: ignore[reportPrivateImportUsage]

from agent_framework_durabletask._workflows.orchestrator import _evaluate_edge_condition_sync


class TestEvaluateEdgeConditionSync:
    """Synchronous edge-condition evaluation semantics."""

    def test_no_condition_traverses(self) -> None:
        edge = Edge("a", "b")
        assert _evaluate_edge_condition_sync(edge, {"x": 1}) is True

    def test_sync_true_traverses(self) -> None:
        edge = Edge("a", "b", condition=lambda m: m["ok"])
        assert _evaluate_edge_condition_sync(edge, {"ok": True}) is True

    def test_sync_false_does_not_traverse(self) -> None:
        edge = Edge("a", "b", condition=lambda m: m["ok"])
        assert _evaluate_edge_condition_sync(edge, {"ok": False}) is False

    def test_async_condition_is_not_traversed(self) -> None:
        # The durabletask host evaluates conditions synchronously; an async
        # condition cannot be evaluated, so the edge is treated as not matched
        # even though it would resolve True when awaited.
        async def gate(_message: object) -> bool:
            return True

        edge = Edge("a", "b", condition=gate)
        assert _evaluate_edge_condition_sync(edge, {"x": 1}) is False
