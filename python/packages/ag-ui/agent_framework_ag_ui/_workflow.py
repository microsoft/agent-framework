# Copyright (c) Microsoft. All rights reserved.

"""Workflow wrapper for AG-UI protocol compatibility."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from ag_ui.core import BaseEvent
from agent_framework import Workflow

from ._workflow_run import run_workflow_stream

WorkflowFactory = Callable[[str], Workflow]


class AgentFrameworkWorkflow:
    """Base AG-UI workflow wrapper.

    Can wrap a native ``Workflow`` or be subclassed for custom ``run`` behavior.
    """

    def __init__(
        self,
        workflow: Workflow | None = None,
        *,
        workflow_factory: WorkflowFactory | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        if workflow is not None and workflow_factory is not None:
            raise ValueError("Pass either workflow= or workflow_factory=, not both.")

        self.workflow = workflow
        self._workflow_factory = workflow_factory
        self._workflow_by_thread: dict[str, Workflow] = {}
        self.name = name if name is not None else getattr(workflow, "name", "workflow")
        self.description = description if description is not None else getattr(workflow, "description", "")

    @staticmethod
    def _thread_id_from_input(input_data: dict[str, Any]) -> str:
        """Resolve a stable thread id from AG-UI input payload."""
        thread_id = input_data.get("thread_id") or input_data.get("threadId")
        if thread_id is not None:
            return str(thread_id)
        return str(uuid.uuid4())

    def _resolve_workflow(self, thread_id: str) -> Workflow:
        """Get the workflow instance for the current run."""
        if self.workflow is not None:
            return self.workflow

        if self._workflow_factory is None:
            raise NotImplementedError("No workflow is attached. Override run or pass workflow=/workflow_factory=.")

        workflow = self._workflow_by_thread.get(thread_id)
        if workflow is None:
            workflow = self._workflow_factory(thread_id)
            if not isinstance(workflow, Workflow):
                raise TypeError("workflow_factory must return a Workflow instance.")
            self._workflow_by_thread[thread_id] = workflow
        return workflow

    def clear_thread_workflow(self, thread_id: str) -> None:
        """Drop a single cached thread workflow instance."""
        self._workflow_by_thread.pop(thread_id, None)

    def clear_workflow_cache(self) -> None:
        """Drop all cached thread workflow instances."""
        self._workflow_by_thread.clear()

    async def run(self, input_data: dict[str, Any]) -> AsyncGenerator[BaseEvent]:
        """Run the wrapped workflow and yield AG-UI events.

        Subclasses may override this to provide custom AG-UI streams.
        """
        thread_id = self._thread_id_from_input(input_data)
        workflow = self._resolve_workflow(thread_id)
        async for event in run_workflow_stream(input_data, workflow):
            yield event
