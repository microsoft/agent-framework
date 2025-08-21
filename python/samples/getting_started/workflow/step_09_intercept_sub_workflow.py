# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Any

from agent_framework.workflow import (
    Executor,
    RequestInfoEvent,
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
This sample demonstrates request interception in sub-workflows.

This sample shows how to:
1. Create a sub-workflow that makes external requests
2. Create a parent workflow that can intercept those requests
3. Use @intercepts_request to conditionally handle or forward requests
4. Use RequestResponse.handled() and RequestResponse.forward() patterns

The example shows an email validation system where:
- Sub-workflow validates emails and requests domain checks
- Parent workflow intercepts domain check requests
- Known domains are approved locally, unknown domains are forwarded externally

Key concepts demonstrated:
- @intercepts_request: Decorator for intercepting sub-workflow requests
- RequestResponse: Enables conditional handling vs forwarding
- Smart caching and optimization through interception
"""


@dataclass
class DomainCheckRequest(RequestInfoMessage):
    """Request to check if a domain is approved."""

    domain: str = ""


@dataclass
class ValidationResult:
    """Result of email validation."""

    email: str
    is_valid: bool
    reason: str


class EmailValidator(Executor):
    """Validates emails by checking domain approval."""

    def __init__(self):
        super().__init__(id="email_validator")
        self._pending_email = None

    @handler
    async def validate(self, email: str, ctx: WorkflowContext[DomainCheckRequest | ValidationResult]) -> None:
        """Validate an email address."""
        self._pending_email = email
        domain = email.split("@")[1] if "@" in email else ""

        if not domain:
            result = ValidationResult(email=email, is_valid=False, reason="Invalid email format")
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            return

        # Request external domain check
        domain_check = DomainCheckRequest(domain=domain)
        await ctx.send_message(domain_check, target_id="request_info")

    @handler
    async def handle_domain_response(
        self, response: RequestResponse[DomainCheckRequest, bool], ctx: WorkflowContext[ValidationResult]
    ) -> None:
        """Handle domain check response with correlation."""
        if response.original_request:
            print(f"Domain check result: {response.original_request.domain} -> {response.data}")
        else:
            print(f"Domain check result: {response.data}")

        if self._pending_email:
            result = ValidationResult(
                email=self._pending_email,
                is_valid=response.data or False,
                reason="Domain approved" if response.data else "Domain not approved",
            )
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            self._pending_email = None


class SmartEmailOrchestrator(Executor):
    """Parent that can intercept domain checks for optimization."""

    def __init__(self):
        super().__init__(id="orchestrator")
        self.approved_domains = {"company.com", "partner.org"}
        self.results: list[ValidationResult] = []

    @handler
    async def start(self, emails: list[str], ctx: WorkflowContext[str]) -> None:
        """Start email validation."""
        for email in emails:
            await ctx.send_message(email, target_id="email_workflow")

    @intercepts_request(DomainCheckRequest)
    async def check_domain(
        self, request: DomainCheckRequest, ctx: WorkflowContext[Any]
    ) -> RequestResponse[DomainCheckRequest, bool]:
        """Intercept domain checks from sub-workflows."""

        if request.domain in self.approved_domains:
            # We know this domain - handle locally
            print(f"Domain {request.domain} is pre-approved locally!")
            return RequestResponse[DomainCheckRequest, bool].handled(True)

        # We don't know - forward to external service
        print(f"Domain {request.domain} unknown, forwarding to external service...")
        return RequestResponse.forward()

    @handler
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext[None]) -> None:
        """Collect validation results."""
        print(f"Email validation result: {result.email} -> {result.is_valid} ({result.reason})")
        self.results.append(result)


async def main():
    """Main function to run the request interception example."""
    print("Setting up sub-workflow with request interception...")

    # Sub-workflow setup
    email_validator = EmailValidator()
    request_info = RequestInfoExecutor(id="request_info")

    validation_workflow = (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, request_info)
        .add_edge(request_info, email_validator)
        .build()
    )

    # Parent workflow setup with interception
    orchestrator = SmartEmailOrchestrator()
    email_workflow = WorkflowExecutor(validation_workflow, id="email_workflow")
    main_request_info = RequestInfoExecutor()

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(orchestrator)
        .add_edge(orchestrator, email_workflow)
        .add_edge(email_workflow, orchestrator)
        .add_edge(orchestrator, main_request_info)  # For forwarded requests
        .add_edge(main_request_info, orchestrator)
        .build()
    )

    # Test emails - mix of known and unknown domains
    test_emails = [
        "user@company.com",  # Will be intercepted and approved
        "admin@partner.org",  # Will be intercepted and approved
        "guest@external.com",  # Will be forwarded to external check
    ]

    print(f"Testing with emails: {test_emails}")
    print("=" * 60)

    # Run the workflow
    result = await main_workflow.run(test_emails)

    # Handle any external requests that were forwarded
    request_events = result.get_request_info_events()
    if request_events:
        print(f"\nGot {len(request_events)} external request(s) to handle")

        # Simulate external service responses
        external_responses: dict[str, bool] = {}
        for event in request_events:
            if isinstance(event, RequestInfoEvent) and event.data and hasattr(event.data, "domain"):
                print(f"External request for domain: {event.data.domain}")
                # For demo purposes, approve external.com
                approved = event.data.domain == "external.com"
                external_responses[event.request_id] = approved
                print(f"External service response: {approved}")

        # Send responses back to the workflow
        await main_workflow.send_responses(external_responses)
    else:
        print("\nAll requests were intercepted and handled locally!")

    print("\nValidation Results:")
    print("=" * 60)
    for result in orchestrator.results:
        status = "VALID" if result.is_valid else "INVALID"
        print(f"{status} {result.email}: {result.reason}")

    print(f"\nProcessed {len(orchestrator.results)} emails total")


if __name__ == "__main__":
    asyncio.run(main())
