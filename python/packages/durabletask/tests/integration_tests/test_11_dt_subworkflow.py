# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for the composed sub-workflow sample (11_subworkflow).

Exercises workflow *composition* on a standalone durabletask worker:
- An outer ``review_pipeline`` embeds an inner ``sentiment_analysis`` workflow via a
  ``WorkflowExecutor`` node (``sentiment_sub``).
- ``DurableAIAgentWorker.configure_workflow`` walks the composition and registers a
  durable orchestration for each workflow; the inner workflow runs as a child
  orchestration when the outer reaches the ``WorkflowExecutor`` node.
- The inner workflow's output (a sentiment summary) is forwarded to the outer
  ``reporter`` executor, which produces the final result.

The inner workflow hosts an AI agent, so these tests require model credentials.
"""

import logging
from typing import Any

import pytest

from agent_framework_durabletask import DurableWorkflowClient

logging.basicConfig(level=logging.WARNING)

# Must match the outer workflow name in samples/04-hosting/durabletask/11_subworkflow/worker.py
WORKFLOW_NAME = "review_pipeline"

# Module-level markers
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("11_subworkflow"),
    pytest.mark.integration_test,
    pytest.mark.requires_dts,
    pytest.mark.requires_azure_openai,
]


class TestSubworkflowComposition:
    """Composed (outer + inner) workflow execution on a standalone durabletask worker."""

    @pytest.fixture(autouse=True)
    def setup(self, workflow_client: DurableWorkflowClient) -> None:
        """Bind the DurableWorkflowClient for the current sample worker."""
        self.client = workflow_client

    def _run(self, review: str) -> Any:
        """Run the composed workflow with a review and return its final output."""
        instance_id = self.client.start_workflow(input=review, workflow_name=WORKFLOW_NAME)
        return self.client.await_workflow_output(instance_id, workflow_name=WORKFLOW_NAME, timeout_seconds=180)

    def test_positive_review_runs_through_subworkflow(self) -> None:
        """A positive review flows through the embedded sentiment sub-workflow to a report."""
        output = self._run(
            "Absolutely love this espresso machine - it heats up fast and the coffee is consistently great."
        )

        assert output is not None
        # The outer reporter wraps the inner sub-workflow's forwarded sentiment summary.
        assert "sentiment" in str(output).lower()

    def test_negative_review_runs_through_subworkflow(self) -> None:
        """A negative review also completes the composed pipeline end-to-end."""
        output = self._run("Disappointed. The device stopped working after two weeks and support never replied.")

        assert output is not None
        assert "sentiment" in str(output).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
