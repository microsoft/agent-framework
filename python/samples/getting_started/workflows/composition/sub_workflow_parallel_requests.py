# Copyright (c) Microsoft. All rights reserved.

import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal

from agent_framework import (
    Executor,
    RequestInfoEvent,
    SubWorkflowRequestMessage,
    SubWorkflowResponseMessage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
    response_handler,
)
from typing_extensions import Never

"""
This sample demonstrates how to handle multiple parallel requests from a sub-workflow to
different executors in the main workflow.

Prerequisite:
- Understanding of sub-workflows.
- Understanding of requests and responses.

This pattern is useful when a sub-workflow needs to interact with multiple external systems
or services.

This sample implements a resource request distribution system where:
1. A sub-workflow generates requests for computing resources and policy checks.
2. The main workflow has executors that handle resource allocation and policy checking.
3. Responses are routed back to the sub-workflow, which collects and processes them.

The sub-workflow sends two types of requests:
- ResourceRequest: Requests for computing resources (e.g., CPU, memory).
- PolicyRequest: Requests to check resource allocation policies.

The main workflow contains:
- ResourceAllocator: Simulates a system that allocates computing resources.
- PolicyEngine: Simulates a policy engine that approves or denies resource requests.
"""


@dataclass
class ComputingResourceRequest:
    """Request for computing resources."""

    request_type: Literal["resource", "policy"]
    resource_type: Literal["cpu", "memory", "disk", "gpu"]
    amount: int
    priority: Literal["low", "normal", "high"] | None = None
    policy_type: Literal["quota", "security"] | None = None


@dataclass
class ResourceResponse:
    """Response with allocated resources."""

    resource_type: str
    allocated: int
    source: str  # Which system provided the resources


@dataclass
class PolicyResponse:
    """Response from policy check."""

    approved: bool
    reason: str


@dataclass
class ResourceRequest:
    """Request for computing resources."""

    resource_type: Literal["cpu", "memory", "disk", "gpu"]
    amount: int
    priority: Literal["low", "normal", "high"]
    id: str = str(uuid.uuid4())


@dataclass
class PolicyRequest:
    """Request to check resource allocation policy."""

    policy_type: Literal["quota", "security"]
    resource_type: Literal["cpu", "memory", "disk", "gpu"]
    amount: int
    id: str = str(uuid.uuid4())


def build_resource_request_distribution_workflow() -> Workflow:
    class RequestDistribution(Executor):
        """Distributes computing resource requests to appropriate executors."""

        @handler
        async def distribute_requests(
            self,
            requests: list[ComputingResourceRequest],
            ctx: WorkflowContext[ResourceRequest | PolicyRequest | int],
        ) -> None:
            for req in requests:
                if req.request_type == "resource":
                    if req.priority is None:
                        raise ValueError("Priority must be set for resource requests")
                    await ctx.send_message(ResourceRequest(req.resource_type, req.amount, req.priority))
                elif req.request_type == "policy":
                    if req.policy_type is None:
                        raise ValueError("Policy type must be set for policy requests")
                    await ctx.send_message(PolicyRequest(req.policy_type, req.resource_type, req.amount))
                else:
                    raise ValueError(f"Unknown request type: {req.request_type}")
            # Notify the collector about the number of requests sent
            await ctx.send_message(len(requests))

    class ResourceRequester(Executor):
        """Handles resource allocation requests."""

        @handler
        async def run(self, request: ResourceRequest, ctx: WorkflowContext) -> None:
            await ctx.request_info(request_data=request, response_type=ResourceResponse)

        @response_handler
        async def handle_response(
            self, original_request: ResourceRequest, response: ResourceResponse, ctx: WorkflowContext[ResourceResponse]
        ) -> None:
            print(f"Resource allocated: {response.allocated} {response.resource_type} from {response.source}")
            await ctx.send_message(response)

    class PolicyChecker(Executor):
        """Handles policy check requests."""

        @handler
        async def run(self, request: PolicyRequest, ctx: WorkflowContext) -> None:
            await ctx.request_info(request_data=request, response_type=PolicyResponse)

        @response_handler
        async def handle_response(
            self, original_request: PolicyRequest, response: PolicyResponse, ctx: WorkflowContext[PolicyResponse]
        ) -> None:
            print(f"Policy check result: {response.approved} - {response.reason}")
            await ctx.send_message(response)

    class ResultCollector(Executor):
        """Collects and processes all responses."""

        def __init__(self, id: str) -> None:
            super().__init__(id)
            self._request_count = 0
            self._responses: list[ResourceResponse | PolicyResponse] = []

        @handler
        async def set_request_count(self, count: int, ctx: WorkflowContext) -> None:
            if count <= 0:
                raise ValueError("Request count must be positive")
            self._request_count = count

        @handler
        async def collect(self, response: ResourceResponse | PolicyResponse, ctx: WorkflowContext[Never, str]) -> None:
            self._responses.append(response)
            print(f"Collected {len(self._responses)}/{self._request_count} responses")
            if len(self._responses) == self._request_count:
                # All responses received, process them
                await ctx.yield_output(f"All {self._request_count} requests processed.")
            elif len(self._responses) > self._request_count:
                raise ValueError("Received more responses than expected")

    return (
        WorkflowBuilder()
        .register_executor(lambda: RequestDistribution("orchestrator"), name="orchestrator")
        .register_executor(lambda: ResourceRequester("resource_requester"), name="resource_requester")
        .register_executor(lambda: PolicyChecker("policy_checker"), name="policy_checker")
        .register_executor(lambda: ResultCollector("result_collector"), name="result_collector")
        .set_start_executor("orchestrator")
        .add_edge("orchestrator", "resource_requester")
        .add_edge("orchestrator", "policy_checker")
        .add_edge("resource_requester", "result_collector")
        .add_edge("policy_checker", "result_collector")
        .add_edge("orchestrator", "result_collector")  # For request count
        .build()
    )


class ResourceAllocator(Executor):
    """Simulates a system that allocates computing resources."""

    def __init__(self, id: str) -> None:
        super().__init__(id)
        self._cache: dict[str, int] = {"cpu": 10, "memory": 50, "disk": 100}
        # Record pending requests to match responses
        self._pending_requests: dict[str, RequestInfoEvent] = {}

    async def _handle_resource_request(self, request: ResourceRequest) -> ResourceResponse | None:
        """Allocates resources based on request and available cache."""
        available = self._cache.get(request.resource_type, 0)
        if available >= request.amount:
            self._cache[request.resource_type] -= request.amount
            return ResourceResponse(request.resource_type, request.amount, "cache")
        return None

    @handler
    async def handle_subworkflow_request(
        self, request: SubWorkflowRequestMessage, ctx: WorkflowContext[SubWorkflowResponseMessage]
    ) -> None:
        """Handles requests from sub-workflows."""
        source_event: RequestInfoEvent = request.source_event
        if not isinstance(source_event.data, ResourceRequest):
            return

        request_payload: ResourceRequest = source_event.data
        response = await self._handle_resource_request(request_payload)
        if response:
            await ctx.send_message(request.create_response(response))
        else:
            # Request cannot be fulfilled via cache, forward the request to external
            self._pending_requests[request_payload.id] = source_event
            await ctx.request_info(request_data=request_payload, response_type=ResourceResponse)

    @response_handler
    async def handle_external_response(
        self,
        original_request: ResourceRequest,
        response: ResourceResponse,
        ctx: WorkflowContext[SubWorkflowResponseMessage],
    ) -> None:
        """Handles responses from external systems and routes them to the sub-workflow."""
        print(f"External resource allocated: {response.allocated} {response.resource_type} from {response.source}")
        source_event = self._pending_requests.pop(original_request.id, None)
        if source_event is None:
            raise ValueError("No matching pending request found for the resource response")
        await ctx.send_message(SubWorkflowResponseMessage(data=response, source_event=source_event))


class PolicyEngine(Executor):
    """Simulates a policy engine that approves or denies resource requests."""

    def __init__(self, id: str) -> None:
        super().__init__(id)
        self._quota: dict[str, int] = {
            "cpu": 5,  # Only allow up to 5 CPU units
            "memory": 20,  # Only allow up to 20 memory units
            "disk": 1000,  # Liberal disk policy
        }
        # Record pending requests to match responses
        self._pending_requests: dict[str, RequestInfoEvent] = {}

    @handler
    async def handle_subworkflow_request(
        self, request: SubWorkflowRequestMessage, ctx: WorkflowContext[SubWorkflowResponseMessage]
    ) -> None:
        """Handles requests from sub-workflows."""
        source_event: RequestInfoEvent = request.source_event
        if not isinstance(source_event.data, PolicyRequest):
            return

        request_payload: PolicyRequest = source_event.data
        # Simple policy logic for demonstration
        if request_payload.policy_type == "quota":
            allowed_amount = self._quota.get(request_payload.resource_type, 0)
            if request_payload.amount <= allowed_amount:
                response = PolicyResponse(True, "Within quota limits")
            else:
                response = PolicyResponse(False, "Exceeds quota limits")
            await ctx.send_message(request.create_response(response))
        else:
            # For other policy types, forward to external system
            self._pending_requests[request_payload.id] = source_event
            await ctx.request_info(request_data=request_payload, response_type=PolicyResponse)

    @response_handler
    async def handle_external_response(
        self,
        original_request: PolicyRequest,
        response: PolicyResponse,
        ctx: WorkflowContext[SubWorkflowResponseMessage],
    ) -> None:
        """Handles responses from external systems and routes them to the sub-workflow."""
        print(f"External policy check result: {response.approved} - {response.reason}")
        source_event = self._pending_requests.pop(original_request.id, None)
        if source_event is None:
            raise ValueError("No matching pending request found for the policy response")
        await ctx.send_message(SubWorkflowResponseMessage(data=response, source_event=source_event))


async def main() -> None:
    # Build the main workflow
    main_workflow = (
        WorkflowBuilder()
        .register_executor(lambda: ResourceAllocator("resource_allocator"), name="resource_allocator")
        .register_executor(lambda: PolicyEngine("policy_engine"), name="policy_engine")
        .register_executor(
            lambda: WorkflowExecutor(
                build_resource_request_distribution_workflow(),
                "sub_workflow_executor",
                # Setting allow_direct_output=True to let the sub-workflow output directly.
                # This is because the sub-workflow is the both the entry point and the exit
                # point of the main workflow.
                allow_direct_output=True,
            ),
            name="sub_workflow_executor",
        )
        .set_start_executor("sub_workflow_executor")
        .add_edge("sub_workflow_executor", "resource_allocator")
        .add_edge("resource_allocator", "sub_workflow_executor")
        .add_edge("sub_workflow_executor", "policy_engine")
        .add_edge("policy_engine", "sub_workflow_executor")
        .build()
    )

    # Test requests
    test_requests = [
        ComputingResourceRequest("resource", "cpu", 2, priority="normal"),  # cache hit
        ComputingResourceRequest("policy", "cpu", 3, policy_type="quota"),  # policy hit
        ComputingResourceRequest("resource", "memory", 15, priority="normal"),  # cache hit
        ComputingResourceRequest("policy", "memory", 100, policy_type="quota"),  # policy miss -> external
        ComputingResourceRequest("resource", "gpu", 1, priority="high"),  # cache miss -> external
        ComputingResourceRequest("policy", "disk", 500, policy_type="quota"),  # policy hit
        ComputingResourceRequest("policy", "cpu", 1, policy_type="security"),  # unknown policy -> external
    ]

    # Run the workflow
    print(f"🧪 Testing with {len(test_requests)} mixed requests.")
    print("🚀 Starting main workflow...")
    run_result = await main_workflow.run(test_requests)

    # Handle request info events
    request_info_events = run_result.get_request_info_events()
    if request_info_events:
        print(f"\n🔍 Handling {len(request_info_events)} request info events...\n")

        responses: dict[str, ResourceResponse | PolicyResponse] = {}
        for event in request_info_events:
            if isinstance(event.data, ResourceRequest):
                # Simulate external resource allocation
                resource_response = ResourceResponse(
                    resource_type=event.data.resource_type, allocated=event.data.amount, source="external_provider"
                )
                responses[event.request_id] = resource_response
            elif isinstance(event.data, PolicyRequest):
                # Simulate external policy check
                response = PolicyResponse(True, "External system approved")
                responses[event.request_id] = response
            else:
                print(f"Unknown request info event data type: {type(event.data)}")

        run_result = await main_workflow.send_responses(responses)

    outputs = run_result.get_outputs()
    if outputs:
        print("\nWorkflow completed with outputs:")
        for output in outputs:
            print(f"- {output}")
    else:
        raise RuntimeError("Workflow did not produce an output.")


if __name__ == "__main__":
    asyncio.run(main())
