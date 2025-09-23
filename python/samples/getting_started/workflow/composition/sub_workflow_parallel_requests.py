# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Any

from typing_extensions import Never

from agent_framework import (
    Executor,
    RequestInfoExecutor,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)

# Import the new sub-workflow types directly from the implementation package
try:
    from agent_framework import (
        RequestInfoMessage,
        RequestResponse,
        WorkflowExecutor,
        intercepts_request,
    )
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "workflow"))
    from agent_framework import (
        RequestInfoMessage,
        RequestResponse,
        WorkflowExecutor,
        intercepts_request,
    )

"""
Sample: Sub-workflow with parallel requests

This sample demonstrates the PROPER pattern for request interception.

Prerequisites:
- No external services required (external handling simulated via `RequestInfoExecutor`).

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

Simple flow visualization:

  Coordinator
      |
      |  list[resource/policy requests]
      v
    [ Sub-workflow: WorkflowExecutor(ResourceRequester) ]
      |                        |
      | ResourceRequest        | PolicyCheckRequest
      v                        v
  ResourceCache (@intercepts)    PolicyEngine (@intercepts)
      | handled/forward             | handled/forward
      v                             v
  RequestInfo (external)  <----- forwarded when not handled
      | responses
      v
  Back to sub-workflow -> completion -> results collected
"""


# 1. Define domain-specific request/response types
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


@dataclass
class RequestFinished:
    pass


# 2. Implement the sub-workflow executor - makes resource and policy requests
class ResourceRequester(Executor):
    """Simple executor that requests resources and checks policies."""

    def __init__(self):
        super().__init__(id="resource_requester")
        self._request_count = 0

    @handler
    async def request_resources(
        self,
        requests: list[dict[str, Any]],
        ctx: WorkflowContext[ResourceRequest | PolicyCheckRequest],
    ) -> None:
        """Process a list of resource requests."""
        print(f"🏭 Sub-workflow processing {len(requests)} requests")
        self._request_count += len(requests)

        for req_data in requests:
            req_type = req_data.get("request_type", "resource")

            request: ResourceRequest | PolicyCheckRequest
            if req_type == "resource":
                print(f"  📦 Requesting resource: {req_data.get('type', 'cpu')} x{req_data.get('amount', 1)}")
                request = ResourceRequest(
                    resource_type=req_data.get("type", "cpu"),
                    amount=req_data.get("amount", 1),
                    priority=req_data.get("priority", "normal"),
                )
                # Send to parent workflow for interception - not to target_id
                await ctx.send_message(request)
            elif req_type == "policy":
                print(
                    f"  🛡️  Checking policy: {req_data.get('type', 'cpu')} x{req_data.get('amount', 1)} "
                    f"({req_data.get('policy_type', 'quota')})"
                )
                request = PolicyCheckRequest(
                    resource_type=req_data.get("type", "cpu"),
                    amount=req_data.get("amount", 1),
                    policy_type=req_data.get("policy_type", "quota"),
                )
                # Send to parent workflow for interception - not to target_id
                await ctx.send_message(request)

    @handler
    async def handle_resource_response(
        self,
        response: RequestResponse[ResourceRequest, ResourceResponse],
        ctx: WorkflowContext[Never, RequestFinished],
    ) -> None:
        """Handle resource allocation response."""
        if response.data:
            source_icon = "🏪" if response.data.source == "cache" else "🌐"
            print(
                f"📦 {source_icon} Sub-workflow received: {response.data.allocated} {response.data.resource_type} "
                f"from {response.data.source}"
            )
            if self._collect_results():
                # Yield completion result to the parent workflow.
                await ctx.yield_output(RequestFinished())

    @handler
    async def handle_policy_response(
        self, response: RequestResponse[PolicyCheckRequest, PolicyResponse], ctx: WorkflowContext[Never, RequestFinished]
    ) -> None:
        """Handle policy check response."""
        if response.data:
            status_icon = "✅" if response.data.approved else "❌"
            print(
                f"🛡️  {status_icon} Sub-workflow received policy response: "
                f"{response.data.approved} - {response.data.reason}"
            )
            if self._collect_results():
                # Yield completion result to the parent workflow.
                await ctx.yield_output(RequestFinished())

    def _collect_results(self) -> bool:
        """Collect and summarize results."""
        self._request_count -= 1
        print(f"📊 Sub-workflow completed request ({self._request_count} remaining)")
        return self._request_count == 0


# 3. Implement the Resource Cache - ONLY intercepts ResourceRequest
class ResourceCache(Executor):
    """Interceptor that handles RESOURCE requests from cache."""

    # Use class attributes to avoid Pydantic assignment restrictions
    cache: dict[str, int] = {"cpu": 10, "memory": 50, "disk": 100}
    results: list[ResourceResponse] = []

    def __init__(self):
        super().__init__(id="resource_cache")
        # Instance initialization only; state kept in class attributes as above

    @intercepts_request
    async def check_cache(
        self, request: ResourceRequest, ctx: WorkflowContext
    ) -> RequestResponse[ResourceRequest, ResourceResponse]:
        """Intercept RESOURCE requests and check cache first."""
        print(f"🏪 CACHE interceptor checking: {request.amount} {request.resource_type}")

        available = self.cache.get(request.resource_type, 0)

        if available >= request.amount:
            # We can satisfy from cache
            self.cache[request.resource_type] -= request.amount
            response = ResourceResponse(resource_type=request.resource_type, allocated=request.amount, source="cache")
            print(f"  ✅ Cache satisfied: {request.amount} {request.resource_type}")
            self.results.append(response)
            return RequestResponse[ResourceRequest, ResourceResponse].handled(response)

        # Cache miss - forward to external
        print(f"  ❌ Cache miss: need {request.amount}, have {available} {request.resource_type}")
        return RequestResponse[ResourceRequest, ResourceResponse].forward()

    @handler
    async def collect_result(
        self, response: RequestResponse[ResourceRequest, ResourceResponse], ctx: WorkflowContext
    ) -> None:
        """Collect results from external requests that were forwarded."""
        if response.data and response.data.source != "cache":  # Don't double-count our own results
            self.results.append(response.data)
            print(
                f"🏪 🌐 Cache received external response: {response.data.allocated} {response.data.resource_type} "
                f"from {response.data.source}"
            )


# 4. Implement the Policy Engine - ONLY intercepts PolicyCheckRequest (different type!)
class PolicyEngine(Executor):
    """Interceptor that handles POLICY requests."""

    # Use class attributes for simple sample state
    quota: dict[str, int] = {
        "cpu": 5,  # Only allow up to 5 CPU units
        "memory": 20,  # Only allow up to 20 memory units
        "disk": 1000,  # Liberal disk policy
    }
    results: list[PolicyResponse] = []

    def __init__(self):
        super().__init__(id="policy_engine")
        # Instance initialization only; state kept in class attributes as above

    @intercepts_request
    async def check_policy(
        self, request: PolicyCheckRequest, ctx: WorkflowContext
    ) -> RequestResponse[PolicyCheckRequest, PolicyResponse]:
        """Intercept POLICY requests and apply rules."""
        print(f"🛡️  POLICY interceptor checking: {request.amount} {request.resource_type}, policy={request.policy_type}")

        quota_limit = self.quota.get(request.resource_type, 0)

        if request.policy_type == "quota":
            if request.amount <= quota_limit:
                response = PolicyResponse(approved=True, reason=f"Within quota ({quota_limit})")
                print(f"  ✅ Policy approved: {request.amount} <= {quota_limit}")
                self.results.append(response)
                return RequestResponse[PolicyCheckRequest, PolicyResponse].handled(response)
            # Exceeds quota - forward to external for review
            print(f"  ❌ Policy exceeds quota: {request.amount} > {quota_limit}, forwarding to external")
            return RequestResponse[PolicyCheckRequest, PolicyResponse].forward()

        # Unknown policy type - forward to external
        print(f"  ❓ Unknown policy type: {request.policy_type}, forwarding")
        return RequestResponse[PolicyCheckRequest, PolicyResponse].forward()

    @handler
    async def collect_policy_result(
        self, response: RequestResponse[PolicyCheckRequest, PolicyResponse], ctx: WorkflowContext
    ) -> None:
        """Collect policy results from external requests that were forwarded."""
        if response.data:
            self.results.append(response.data)
            print(f"🛡️  🌐 Policy received external response: {response.data.approved} - {response.data.reason}")


class Coordinator(Executor):
    def __init__(self):
        super().__init__(id="coordinator")

    @handler
    async def start(self, requests: list[dict[str, Any]], ctx: WorkflowContext[list[dict[str, Any]]]) -> None:
        """Start the resource allocation process."""
        await ctx.send_message(requests, target_id="resource_workflow")

    @handler
    async def handle_completion(self, completion: RequestFinished, ctx: WorkflowContext) -> None:
        """Handle sub-workflow completion.

        It comes from the sub-workflow yielded output.
        """
        print("🎯 Main workflow received completion.")


async def main() -> None:
    """Demonstrate parallel request interception patterns."""
    print("🚀 Starting Sub-Workflow Parallel Request Interception Demo...")
    print("=" * 60)

    # 5. Create the sub-workflow
    resource_requester = ResourceRequester()
    sub_request_info = RequestInfoExecutor(id="sub_request_info")

    sub_workflow = (
        WorkflowBuilder()
        .set_start_executor(resource_requester)
        .add_edge(resource_requester, sub_request_info)
        .add_edge(sub_request_info, resource_requester)
        .build()
    )

    # 6. Create parent workflow with PROPER interceptor pattern
    cache = ResourceCache()  # Intercepts ResourceRequest
    policy = PolicyEngine()  # Intercepts PolicyCheckRequest (different type!)
    workflow_executor = WorkflowExecutor(sub_workflow, id="resource_workflow")
    main_request_info = RequestInfoExecutor(id="main_request_info")

    # Create a simple coordinator that starts the process
    coordinator = Coordinator()

    # PROPER PATTERN: Each executor intercepts DIFFERENT request types
    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(coordinator)
        .add_edge(coordinator, workflow_executor)  # Start sub-workflow
        .add_edge(workflow_executor, coordinator)  # Sub-workflow completion back to coordinator
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

    # 7. Test with various requests (mixed resource and policy)
    test_requests = [
        {"request_type": "resource", "type": "cpu", "amount": 2, "priority": "normal"},  # Cache hit
        {"request_type": "policy", "type": "cpu", "amount": 3, "policy_type": "quota"},  # Policy hit
        {"request_type": "resource", "type": "memory", "amount": 15, "priority": "normal"},  # Cache hit
        {"request_type": "policy", "type": "memory", "amount": 100, "policy_type": "quota"},  # Policy miss -> external
        {"request_type": "resource", "type": "gpu", "amount": 1, "priority": "high"},  # Cache miss -> external
        {"request_type": "policy", "type": "disk", "amount": 500, "policy_type": "quota"},  # Policy hit
        {"request_type": "policy", "type": "cpu", "amount": 1, "policy_type": "security"},  # Unknown policy -> external
    ]

    print(f"🧪 Testing with {len(test_requests)} mixed requests:")
    for i, req in enumerate(test_requests, 1):
        req_icon = "📦" if req["request_type"] == "resource" else "🛡️"
        print(
            f"  {i}. {req_icon} {req['type']} x{req['amount']} "
            f"({req.get('priority', req.get('policy_type', 'default'))})"
        )
    print("=" * 70)

    # 8. Run the workflow
    print("🎬 Running workflow...")
    events = await main_workflow.run(test_requests)

    # 9. Handle any external requests that couldn't be intercepted
    request_events = events.get_request_info_events()
    if request_events:
        print(f"\n🌐 Handling {len(request_events)} external request(s)...")

        external_responses: dict[str, Any] = {}
        for event in request_events:
            if isinstance(event.data, ResourceRequest):
                # Handle ResourceRequest - create ResourceResponse
                resource_response = ResourceResponse(
                    resource_type=event.data.resource_type, allocated=event.data.amount, source="external_provider"
                )
                external_responses[event.request_id] = resource_response
                print(f"  🏭 External provider: {resource_response.allocated} {resource_response.resource_type}")
            elif isinstance(event.data, PolicyCheckRequest):
                # Handle PolicyCheckRequest - create PolicyResponse
                policy_response = PolicyResponse(approved=True, reason="External policy service approved")
                external_responses[event.request_id] = policy_response
                print(f"  🔒 External policy: {'✅ APPROVED' if policy_response.approved else '❌ DENIED'}")

        await main_workflow.send_responses(external_responses)
    else:
        print("\n🎯 All requests were intercepted internally!")

    # 10. Show results and analysis
    print("\n" + "=" * 70)
    print("📊 RESULTS ANALYSIS")
    print("=" * 70)

    print(f"\n🏪 Cache Results ({len(cache.results)} handled):")
    for result in cache.results:
        print(f"  ✅ {result.allocated} {result.resource_type} from {result.source}")

    print(f"\n🛡️  Policy Results ({len(policy.results)} handled):")
    for result in policy.results:
        status_icon = "✅" if result.approved else "❌"
        print(f"  {status_icon} Approved: {result.approved} - {result.reason}")

    print("\n💾 Final Cache State:")
    for resource, amount in cache.cache.items():
        print(f"  📦 {resource}: {amount} remaining")

    print("\n📈 Summary:")
    print(f"  🎯 Total requests: {len(test_requests)}")
    print(f"  🏪 Resource requests handled: {len(cache.results)}")
    print(f"  🛡️  Policy requests handled: {len(policy.results)}")
    print(f"  🌐 External requests: {len(request_events) if request_events else 0}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
