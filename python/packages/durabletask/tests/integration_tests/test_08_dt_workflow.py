# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for the standalone durabletask workflow sample (08_workflow).

Exercises the standalone (non-Azure-Functions) workflow path:
- ``DurableAIAgentWorker.configure_workflow`` auto-registers the agent entities,
  non-agent executor activities, and the workflow orchestrator.
- A client starts the workflow by scheduling ``WORKFLOW_ORCHESTRATOR_NAME``.
- Conditional routing sends spam to a non-agent handler and legitimate email
  through a second agent and a sender executor.
"""

import logging

import pytest
from durabletask.client import OrchestrationStatus

from agent_framework_durabletask import WORKFLOW_ORCHESTRATOR_NAME

logging.basicConfig(level=logging.WARNING)

# Module-level markers
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("08_workflow"),
    pytest.mark.integration_test,
    pytest.mark.requires_dts,
]


class TestStandaloneWorkflow:
    """Standalone (non-Azure-Functions) workflow execution on a durabletask worker."""

    @pytest.fixture(autouse=True)
    def setup(self, agent_client_factory: type, orchestration_helper) -> None:
        """Provide a DTS client and orchestration helper for each test."""
        self.dts_client, self.agent_client = agent_client_factory.create()
        self.orch_helper = orchestration_helper

    def test_legitimate_email_drafts_response(self) -> None:
        """A legitimate email routes through the email agent and is 'sent'."""
        instance_id = self.dts_client.schedule_new_orchestration(
            orchestrator=WORKFLOW_ORCHESTRATOR_NAME,
            input=(
                "Hi team, just a reminder about our sprint planning meeting tomorrow at 10 AM. "
                "Please review the agenda in Jira."
            ),
        )

        metadata, output = self.orch_helper.wait_for_orchestration_with_output(
            instance_id=instance_id,
            timeout=180.0,
        )

        assert metadata.runtime_status == OrchestrationStatus.COMPLETED
        assert output is not None
        assert "Email sent" in str(output)

    def test_spam_email_handled(self) -> None:
        """A spam email routes to the non-agent spam handler."""
        instance_id = self.dts_client.schedule_new_orchestration(
            orchestrator=WORKFLOW_ORCHESTRATOR_NAME,
            input="URGENT! You've won $1,000,000! Click here now to claim your prize! Limited time offer!",
        )

        metadata, output = self.orch_helper.wait_for_orchestration_with_output(
            instance_id=instance_id,
            timeout=180.0,
        )

        assert metadata.runtime_status == OrchestrationStatus.COMPLETED
        assert output is not None
        assert "spam" in str(output).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
