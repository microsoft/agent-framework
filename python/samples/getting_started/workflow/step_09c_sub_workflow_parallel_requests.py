# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Any

from agent_framework.workflow import (
    Executor,
    RequestInfoExecutor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

# Import the new sub-workflow types directly from the implementation package
try:
    from agent_framework_workflow import (
        RequestInfoMessage,
        RequestResponse,
        WorkflowExecutor,
        intercepts_request,
    )
except ImportError:
    # For development/testing when agent_framework_workflow is not installed
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "workflow"))
    from agent_framework_workflow import (
        RequestInfoMessage,
        RequestResponse,
        WorkflowExecutor,
        intercepts_request,
    )

"""
This sample demonstrates the PROPER pattern for request interception.

Key principles:
1. Only ONE executor intercepts a given request type from a specific sub-workflow
2. Different executors can intercept DIFFERENT request types from the same sub-workflow
3. The same executor can intercept the same request type from DIFFERENT sub-workflows

This ensures:
- Deterministic behavior
- Clear responsibility boundaries
- Easier debugging and maintenance

The example simulates a resource allocation system where:
- Sub-workflow requests resources (CPU, memory, etc.)
- A single Cache executor intercepts and handles resource requests
- The Cache can either satisfy from cache or forward to external
"""


@dataclass
class ResourceRequest(RequestInfoMessage):
    """Request for computing resources."""

    resource_type: str = "cpu"  # cpu, memory, disk, etc.
    amount: int = 1
    priority: str = "normal"  # low, normal, high


@dataclass
class PolicyCheckRequest(RequestInfoMessage):
    """Request to check resource allocation policy."""

    resource_type: str = ""
    amount: int = 0
    policy_type: str = "quota"  # quota, compliance, security


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


# Sub-workflow executor - makes resource and policy requests
class ResourceRequester(Executor):
    """Simple executor that requests resources and checks policies."""

    def __init__(self):
        super().__init__(id="resource_requester")
        self._request_count = 0

    @handler
    async def request_resources(
        self,
        requests: list[dict[str, Any]],
        ctx: WorkflowContext[ResourceRequest | PolicyCheckRequest | ResourceResponse | PolicyResponse],
    ) -> None:
        """Process a list of resource requests."""
        print(f"Sub-workflow processing {len(requests)} requests")
        self._request_count += len(requests)

        for req_data in requests:
            req_type = req_data.get("request_type", "resource")

            if req_type == "resource":
                print(f"  Requesting resource: {req_data}")
                request = ResourceRequest(
                    resource_type=req_data.get("type", "cpu"),
                    amount=req_data.get("amount", 1),
                    priority=req_data.get("priority", "normal"),
                )
                await ctx.send_message(request)
            elif req_type == "policy":
                print(f"  Checking policy: {req_data}")
                request = PolicyCheckRequest(
                    resource_type=req_data.get("type", "cpu"),
                    amount=req_data.get("amount", 1),
                    policy_type=req_data.get("policy_type", "quota"),
                )
                await ctx.send_message(request)

    @handler
    async def handle_resource_response(
        self,
        response: RequestResponse[ResourceRequest, ResourceResponse],
        ctx: WorkflowContext[ResourceResponse | list[Any]],
    ) -> None:
        """Handle resource allocation response."""
        if response.data:
            print(
                f"Sub-workflow received: {response.data.allocated} {response.data.resource_type} from {response.data.source}"
            )
            if self._collect_results():
                await ctx.add_event(WorkflowCompletedEvent())

    @handler
    async def handle_policy_response(
        self, response: RequestResponse[PolicyCheckRequest, PolicyResponse], ctx: WorkflowContext[list[Any]]
    ) -> None:
        """Handle policy check response."""
        if response.data:
            print(f"Sub-workflow received policy response: {response.data.approved} - {response.data.reason}")
            if self._collect_results():
                await ctx.add_event(WorkflowCompletedEvent())

    def _collect_results(self) -> bool:
        """Collect and summarize results."""
        print(f"Sub-workflow completed {self._request_count} requests.")
        self._request_count -= 1
        return self._request_count == 0


# Resource Cache - ONLY intercepts ResourceRequest
class ResourceCache(Executor):
    """Interceptor that handles RESOURCE requests from cache."""

    def __init__(self):
        super().__init__(id="resource_cache")
        # Simulate cached resources
        self.cache = {"cpu": 10, "memory": 50, "disk": 100}
        self.results: list[ResourceResponse] = []

    @intercepts_request
    async def check_cache(
        self, request: ResourceRequest, ctx: WorkflowContext[Any]
    ) -> RequestResponse[ResourceRequest, ResourceResponse]:
        """Intercept RESOURCE requests and check cache first."""
        print(f"CACHE interceptor checking: {request.amount} {request.resource_type}")

        available = self.cache.get(request.resource_type, 0)

        if available >= request.amount:
            # We can satisfy from cache
            self.cache[request.resource_type] -= request.amount
            response = ResourceResponse(resource_type=request.resource_type, allocated=request.amount, source="cache")
            print(f"  + Cache satisfied: {request.amount} {request.resource_type}")
            self.results.append(response)
            return RequestResponse[ResourceRequest, ResourceResponse].handled(response)

        # Cache miss - forward to external
        print(f"  - Cache miss: need {request.amount}, have {available} {request.resource_type}")
        return RequestResponse.forward()

    @handler
    async def collect_result(
        self, response: RequestResponse[ResourceRequest, ResourceResponse], ctx: WorkflowContext[None]
    ) -> None:
        """Collect results from external requests that were forwarded."""
        if response.data and response.data.source != "cache":  # Don't double-count our own results
            self.results.append(response.data)
            print(
                f"Cache received external response: {response.data.allocated} {response.data.resource_type} from {response.data.source}"
            )


# Policy Engine - ONLY intercepts PolicyCheckRequest (different type!)
class PolicyEngine(Executor):
    """Interceptor that handles POLICY requests."""

    def __init__(self):
        super().__init__(id="policy_engine")
        self.quota = {
            "cpu": 5,  # Only allow up to 5 CPU units
            "memory": 20,  # Only allow up to 20 memory units
            "disk": 1000,  # Liberal disk policy
        }
        self.results: list[PolicyResponse] = []

    @intercepts_request
    async def check_policy(
        self, request: PolicyCheckRequest, ctx: WorkflowContext[Any]
    ) -> RequestResponse[PolicyCheckRequest, PolicyResponse]:
        """Intercept POLICY requests and apply rules."""
        print(f"POLICY interceptor checking: {request.amount} {request.resource_type}, policy={request.policy_type}")

        quota_limit = self.quota.get(request.resource_type, 0)

        if request.policy_type == "quota":
            if request.amount <= quota_limit:
                response = PolicyResponse(approved=True, reason=f"Within quota ({quota_limit})")
                print(f"  + Policy approved: {request.amount} <= {quota_limit}")
                self.results.append(response)
                return RequestResponse[PolicyCheckRequest, PolicyResponse].handled(response)
            # Exceeds quota - forward to external for review
            print(f"  - Policy exceeds quota: {request.amount} > {quota_limit}, forwarding to external")
            return RequestResponse.forward()

        # Unknown policy type - forward to external
        print(f"  ? Unknown policy type: {request.policy_type}, forwarding")
        return RequestResponse.forward()

    @handler
    async def collect_policy_result(
        self, response: RequestResponse[PolicyCheckRequest, PolicyResponse], ctx: WorkflowContext[None]
    ) -> None:
        """Collect policy results from external requests that were forwarded."""
        if response.data:
            self.results.append(response.data)
            print(f"Policy received external response: {response.data.approved} - {response.data.reason}")


async def main():
    """Main function to run the proper interceptor pattern example."""
    print("Setting up PROPER interceptor pattern example...")
    print("=" * 70)

    # Step 1: Create the resource requesting sub-workflow
    requester = ResourceRequester()
    request_info = RequestInfoExecutor(id="sub_request_info")

    sub_workflow = (
        WorkflowBuilder()
        .set_start_executor(requester)
        .add_edge(requester, request_info)
        .add_edge(request_info, requester)
        .build()
    )

    # Step 2: Create parent workflow with PROPER interceptor pattern
    cache = ResourceCache()  # Intercepts ResourceRequest
    policy = PolicyEngine()  # Intercepts PolicyCheckRequest (different type!)
    workflow_executor = WorkflowExecutor(sub_workflow, id="resource_workflow")
    main_request_info = RequestInfoExecutor(id="main_request_info")

    # Create a simple coordinator that starts the process
    class Coordinator(Executor):
        def __init__(self):
            super().__init__(id="coordinator")

        @handler
        async def start(self, requests: list[dict[str, Any]], ctx: WorkflowContext[list[dict[str, Any]]]) -> None:
            """Start the resource allocation process."""
            await ctx.send_message(requests, target_id="resource_workflow")

    coordinator = Coordinator()

    # PROPER PATTERN: Each executor intercepts DIFFERENT request types
    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(coordinator)
        .add_edge(coordinator, workflow_executor)  # Start sub-workflow
        .add_edge(workflow_executor, cache)  # Cache intercepts ResourceRequest
        .add_edge(cache, workflow_executor)  # Cache handles ResourceRequest
        .add_edge(workflow_executor, policy)  # Policy handles PolicyCheckRequest
        .add_edge(policy, workflow_executor)  # Policy intercepts PolicyCheckRequest
        .add_edge(cache, main_request_info)  # Cache forwards to external
        .add_edge(policy, main_request_info)  # Policy forwards to external
        .add_edge(main_request_info, workflow_executor)  # External responses back
        .add_edge(workflow_executor, main_request_info)  # Sub-workflow forwards to main
        .build()
    )

    # Step 3: Test with various requests (mixed resource and policy)
    test_requests = [
        {"request_type": "resource", "type": "cpu", "amount": 2, "priority": "normal"},  # Cache hit
        {"request_type": "policy", "type": "cpu", "amount": 3, "policy_type": "quota"},  # Policy hit
        {"request_type": "resource", "type": "memory", "amount": 15, "priority": "normal"},  # Cache hit
        {"request_type": "policy", "type": "memory", "amount": 100, "policy_type": "quota"},  # Policy miss -> external
        {"request_type": "resource", "type": "gpu", "amount": 1, "priority": "high"},  # Cache miss -> external
        {"request_type": "policy", "type": "disk", "amount": 500, "policy_type": "quota"},  # Policy hit
        {"request_type": "policy", "type": "cpu", "amount": 1, "policy_type": "security"},  # Unknown policy -> external
    ]

    print(f"Testing with requests: {test_requests}")
    print("-" * 70)

    # Step 4: Run the workflow
    result = await main_workflow.run(test_requests)

    # Step 5: Handle any external requests that couldn't be intercepted
    request_events = result.get_request_info_events()
    if request_events:
        print(f"\nHandling {len(request_events)} external request(s)...")

        external_responses: dict[str, Any] = {}
        for event in request_events:
            if hasattr(event.data, "resource_type") and event.data:
                # Simulate external resource provider
                response = ResourceResponse(
                    resource_type=event.data.resource_type, allocated=event.data.amount, source="external_provider"
                )
                external_responses[event.request_id] = response
                print(f"  External provider: {response.allocated} {response.resource_type}")
            elif hasattr(event.data, "policy_type"):
                # Simulate external policy service
                response = PolicyResponse(approved=True, reason="External policy service approved")
                external_responses[event.request_id] = response
                print(f"  External policy: {response.approved}")

        await main_workflow.send_responses(external_responses)
    else:
        print("\nAll requests were intercepted internally!")

    # Step 6: Show results and analysis
    print("\n" + "=" * 70)
    print("RESULTS ANALYSIS")
    print("=" * 70)

    print(f"\nCache Results ({len(cache.results)} handled):")
    for result in cache.results:
        print(f"  {result.allocated} {result.resource_type} from {result.source}")

    print(f"\nPolicy Results ({len(policy.results)} handled):")
    for result in policy.results:
        print(f"  Approved: {result.approved} - {result.reason}")

    print("\nFinal Cache State:")
    for resource, amount in cache.cache.items():
        print(f"  {resource}: {amount} remaining")

    print("\nSummary:")
    print(f"  Total requests: {len(test_requests)}")
    print(f"  Resource requests handled: {len(cache.results)}")
    print(f"  Policy requests handled: {len(policy.results)}")
    print(f"  External requests: {len(request_events) if request_events else 0}")

    print("\n" + "=" * 70)
    print("SUCCESS: This workflow passes validation!")
    print("SUCCESS: Each request type has exactly ONE interceptor")
    print("SUCCESS: Behavior is deterministic and predictable")


if __name__ == "__main__":
    asyncio.run(main())
