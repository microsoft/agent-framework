# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass

from agent_framework import (
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunState,
    handler,
    response_handler,
)
from agent_framework._workflows._executor import Executor
from agent_framework._workflows._request_info_mixin import RequestInfoMixin


@dataclass
class UserApprovalRequest:
    """A request for user approval with context."""

    prompt: str
    context: str
    request_id: str = ""

    def __post_init__(self):
        if not self.request_id:
            import uuid

            self.request_id = str(uuid.uuid4())


@dataclass
class CalculationRequest:
    """A request for a complex calculation."""

    operation: str
    operands: list[float]
    request_id: str = ""

    def __post_init__(self):
        if not self.request_id:
            import uuid

            self.request_id = str(uuid.uuid4())


class ApprovalRequiredExecutor(Executor, RequestInfoMixin):
    """Executor that requires approval before proceeding."""

    def __init__(self, id: str):
        super().__init__(id=id)
        self.approval_received = False
        self.final_result = None

    @handler
    async def start_process(self, message: str, ctx: WorkflowContext) -> None:
        """Start a process that requires approval."""
        # Request approval from external system
        approval_request = UserApprovalRequest(
            prompt=f"Please approve the operation: {message}",
            context="This is a critical operation that requires human approval.",
        )
        await ctx.request_info(approval_request, bool)

    @response_handler
    async def handle_approval_response(
        self, original_request: UserApprovalRequest, approved: bool, ctx: WorkflowContext[str]
    ) -> None:
        """Handle the approval response."""
        self.approval_received = True

        if approved:
            self.final_result = f"Operation approved: {original_request.prompt}"
            await ctx.send_message(f"APPROVED: {original_request.context}")
        else:
            self.final_result = "Operation denied by user"
            await ctx.send_message("DENIED: Operation was not approved")


class CalculationExecutor(Executor, RequestInfoMixin):
    """Executor that delegates complex calculations to external services."""

    def __init__(self, id: str):
        super().__init__(id=id)
        self.calculations_performed: list[tuple[str, list[float], float]] = []

    @handler
    async def process_calculation(self, message: str, ctx: WorkflowContext[str]) -> None:
        """Process a calculation request."""
        # Parse the message to extract operation
        parts = message.split()
        if len(parts) >= 3:
            operation = parts[0]
            try:
                operands = [float(x) for x in parts[1:]]
                calc_request = CalculationRequest(operation=operation, operands=operands)
                await ctx.request_info(calc_request, float)
            except ValueError:
                await ctx.send_message("Invalid calculation format")
        else:
            await ctx.send_message("Insufficient parameters for calculation")

    @response_handler
    async def handle_calculation_response(
        self, original_request: CalculationRequest, result: float, ctx: WorkflowContext[str]
    ) -> None:
        """Handle the calculation response."""
        self.calculations_performed.append((original_request.operation, original_request.operands, result))
        operands_str = ", ".join(map(str, original_request.operands))
        await ctx.send_message(f"Calculation complete: {original_request.operation}({operands_str}) = {result}")


class MultiRequestExecutor(Executor, RequestInfoMixin):
    """Executor that makes multiple requests and waits for all responses."""

    def __init__(self, id: str):
        super().__init__(id=id)
        self.responses_received: list[tuple[str, bool | float]] = []

    @handler
    async def start_multi_request(self, message: str, ctx: WorkflowContext) -> None:
        """Start multiple requests simultaneously."""
        # Request approval
        approval_request = UserApprovalRequest(
            prompt="Approve batch operation", context="Multiple operations will be performed"
        )
        await ctx.request_info(approval_request, bool)

        # Request calculation
        calc_request = CalculationRequest(operation="multiply", operands=[10.0, 5.0])
        await ctx.request_info(calc_request, float)

    @response_handler
    async def handle_approval_response(
        self, original_request: UserApprovalRequest, approved: bool, ctx: WorkflowContext[str]
    ) -> None:
        """Handle approval response."""
        self.responses_received.append(("approval", approved))
        await self._check_completion(ctx)

    @response_handler
    async def handle_calculation_response(
        self, original_request: CalculationRequest, result: float, ctx: WorkflowContext[str]
    ) -> None:
        """Handle calculation response."""
        self.responses_received.append(("calculation", result))
        await self._check_completion(ctx)

    async def _check_completion(self, ctx: WorkflowContext[str]) -> None:
        """Check if all responses are received and send final result."""
        if len(self.responses_received) == 2:
            approval_result = next((r[1] for r in self.responses_received if r[0] == "approval"), None)
            calc_result = next((r[1] for r in self.responses_received if r[0] == "calculation"), None)

            if approval_result and calc_result is not None:
                await ctx.send_message(f"All operations complete. Calculation result: {calc_result}")
            else:
                await ctx.send_message("Operations completed with mixed results")


class OutputCollector(Executor):
    """Simple executor that collects outputs for testing."""

    def __init__(self, id: str):
        super().__init__(id=id)
        self.collected_outputs: list[str] = []

    @handler
    async def collect_output(self, message: str, ctx: WorkflowContext) -> None:
        """Collect output messages."""
        self.collected_outputs.append(message)


class TestRequestInfoAndResponse:
    """Test cases for end-to-end request info and response handling at the workflow level."""

    async def test_approval_workflow(self):
        """Test end-to-end workflow with approval request."""
        executor = ApprovalRequiredExecutor(id="approval_executor")
        workflow = WorkflowBuilder(start_executor=executor).build()

        # First run the workflow until it emits a request
        request_info_event: WorkflowEvent | None = None
        async for event in workflow.run("test operation", stream=True):
            if event.type == "request_info":
                request_info_event = event

        assert request_info_event is not None
        assert isinstance(request_info_event.data, UserApprovalRequest)
        assert request_info_event.data.prompt == "Please approve the operation: test operation"

        # Send response and continue workflow
        completed = False
        async for event in workflow.run(stream=True, responses={request_info_event.request_id: True}):
            if event.type == "status" and event.state == WorkflowRunState.IDLE:
                completed = True

        assert completed
        assert executor.approval_received is True
        assert executor.final_result == "Operation approved: Please approve the operation: test operation"

    async def test_calculation_workflow(self):
        """Test end-to-end workflow with calculation request."""
        executor = CalculationExecutor(id="calc_executor")
        workflow = WorkflowBuilder(start_executor=executor).build()

        # First run the workflow until it emits a calculation request
        request_info_event: WorkflowEvent | None = None
        async for event in workflow.run("multiply 15.5 2.0", stream=True):
            if event.type == "request_info":
                request_info_event = event

        assert request_info_event is not None
        assert isinstance(request_info_event.data, CalculationRequest)
        assert request_info_event.data.operation == "multiply"
        assert request_info_event.data.operands == [15.5, 2.0]

        # Send response with calculated result
        calculated_result = 31.0
        completed = False
        async for event in workflow.run(stream=True, responses={request_info_event.request_id: calculated_result}):
            if event.type == "status" and event.state == WorkflowRunState.IDLE:
                completed = True

        assert completed
        assert len(executor.calculations_performed) == 1
        assert executor.calculations_performed[0] == ("multiply", [15.5, 2.0], calculated_result)

    async def test_multiple_requests_workflow(self):
        """Test workflow with multiple concurrent requests."""
        executor = MultiRequestExecutor(id="multi_executor")
        workflow = WorkflowBuilder(start_executor=executor).build()

        # Collect all request events by running the full stream
        request_events: list[WorkflowEvent] = []
        async for event in workflow.run("start batch", stream=True):
            if event.type == "request_info":
                request_events.append(event)

        assert len(request_events) == 2

        # Find the approval and calculation requests
        approval_event: WorkflowEvent | None = next(
            (e for e in request_events if isinstance(e.data, UserApprovalRequest)), None
        )
        calc_event: WorkflowEvent | None = next(
            (e for e in request_events if isinstance(e.data, CalculationRequest)), None
        )

        assert approval_event is not None
        assert calc_event is not None

        # Send responses for both requests
        responses = {approval_event.request_id: True, calc_event.request_id: 50.0}
        completed = False
        async for event in workflow.run(stream=True, responses=responses):
            if event.type == "status" and event.state == WorkflowRunState.IDLE:
                completed = True

        assert completed
        assert len(executor.responses_received) == 2

    async def test_denied_approval_workflow(self):
        """Test workflow when approval is denied."""
        executor = ApprovalRequiredExecutor(id="approval_executor")
        workflow = WorkflowBuilder(start_executor=executor).build()

        # First run the workflow until it emits a request
        request_info_event: WorkflowEvent | None = None
        async for event in workflow.run("sensitive operation", stream=True):
            if event.type == "request_info":
                request_info_event = event

        assert request_info_event is not None

        # Deny the request
        completed = False
        async for event in workflow.run(stream=True, responses={request_info_event.request_id: False}):
            if event.type == "status" and event.state == WorkflowRunState.IDLE:
                completed = True

        assert completed
        assert executor.approval_received is True
        assert executor.final_result == "Operation denied by user"

    async def test_workflow_state_with_pending_requests(self):
        """Test workflow state when waiting for responses."""
        executor = ApprovalRequiredExecutor(id="approval_executor")
        workflow = WorkflowBuilder(start_executor=executor).build()

        # Run workflow until idle with pending requests
        request_info_event: WorkflowEvent | None = None
        idle_with_pending = False
        async for event in workflow.run("test operation", stream=True):
            if event.type == "request_info":
                request_info_event = event
            elif event.type == "status" and event.state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS:
                idle_with_pending = True

        assert request_info_event is not None
        assert idle_with_pending

        # Continue with response
        completed = False
        async for event in workflow.run(stream=True, responses={request_info_event.request_id: True}):
            if event.type == "status" and event.state == WorkflowRunState.IDLE:
                completed = True

        assert completed

    async def test_invalid_calculation_input(self):
        """Test workflow handling of invalid calculation input."""
        executor = CalculationExecutor(id="calc_executor")
        workflow = WorkflowBuilder(start_executor=executor).build()

        # Send invalid input (no numbers)
        completed = False
        async for event in workflow.run("invalid input", stream=True):
            if event.type == "status" and event.state == WorkflowRunState.IDLE:
                completed = True

        assert completed
        # Should not have any calculations performed due to invalid input
        assert len(executor.calculations_performed) == 0
