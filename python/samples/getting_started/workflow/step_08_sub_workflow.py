# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Any

from agent_framework.workflow import (
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

# Import the new sub-workflow types directly from the implementation package
try:
    from agent_framework_workflow import (
        RequestResponse,
        WorkflowEvent,
        WorkflowExecutor,
        intercepts_request,
    )
except ImportError:
    # For development/testing when agent_framework_workflow is not installed
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "workflow"))
    from agent_framework_workflow import (
        RequestResponse,
        WorkflowExecutor,
        intercepts_request,
    )

"""
The following sample demonstrates advanced sub-workflows with request interception.

This sample shows how to:
1. Create workflows that execute other workflows as sub-workflows
2. Intercept requests from sub-workflows in parent workflows using @intercepts_request
3. Conditionally handle or forward requests using RequestResponse.handled() and RequestResponse.forward()

The example simulates an email validation system where:
- Sub-workflows validate email addresses and request domain checks
- Parent workflows can intercept domain check requests for optimization
- Known domains are approved locally, unknown domains would be forwarded externally

Note: This is an advanced example. For basic sub-workflow functionality, 
see step_08a_simple_sub_workflow.py first.

Key concepts demonstrated:
- WorkflowExecutor: Wraps a workflow to make it behave as an executor
- @intercepts_request: Decorator for parent workflows to handle sub-workflow requests
- RequestResponse: Enables conditional handling vs forwarding of requests
- Sub-workflow isolation: Sub-workflows work normally without knowing they're nested
"""


# Domain-specific message types
@dataclass
class EmailValidationRequest:
    """Request to validate an email address."""

    email: str


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


class WorkflowFinished(WorkflowEvent):
    """Event triggered when a workflow completes."""

    def __init__(self, data: Any = None):
        super().__init__(data)


# Sub-workflow executor (completely standard)
class EmailValidator(Executor):
    """Validates email addresses - doesn't know it's in a sub-workflow."""

    def __init__(self):
        super().__init__(id="email_validator")

    @handler(output_types=[DomainCheckRequest, ValidationResult])
    async def validate(self, request: EmailValidationRequest, ctx: WorkflowContext) -> None:
        """Validate an email address."""
        print(f"Validating email: {request.email}")

        # Extract domain
        domain = request.email.split("@")[1] if "@" in request.email else ""

        if not domain:
            result = ValidationResult(email=request.email, is_valid=False, reason="Invalid email format")
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            return

        # Request domain check
        print(f"Checking domain: {domain}")
        domain_check = DomainCheckRequest(domain=domain)
        await ctx.send_message(domain_check)

    @handler(output_types=[ValidationResult])
    async def handle_domain_response(
        self, response: RequestResponse[DomainCheckRequest, bool], ctx: WorkflowContext
    ) -> None:
        """Handle domain check response with correlation."""
        print(f"Domain check result: {response.original_request.domain} - {response.data}")

        result = ValidationResult(
            email=response.original_request.domain,
            is_valid=response.data or False,
            reason="Domain approved" if response.data else "Domain not approved",
        )
        await ctx.add_event(WorkflowCompletedEvent(data=result))


# Parent workflow with request interception
class SmartEmailOrchestrator(Executor):
    """Parent orchestrator that can intercept domain checks."""

    def __init__(self, approved_domains: set[str] | None = None):
        super().__init__(id="email_orchestrator")
        self.approved_domains = approved_domains or {"example.com", "test.org", "company.com"}
        self.results: list[ValidationResult] = []
        self.expected_result_count: int
        print(f"Orchestrator knows about domains: {self.approved_domains}")

    @handler(output_types=[EmailValidationRequest])
    async def start_validation(self, emails: list[str], ctx: WorkflowContext) -> None:
        """Start validating a batch of emails."""
        print(f"Starting validation of {len(emails)} emails")
        for email in emails:
            request = EmailValidationRequest(email=email)
            self.expected_result_count = len(emails)
            await ctx.send_message(request, target_id="email_validator_workflow")

    @intercepts_request(DomainCheckRequest)
    async def check_domain(
        self, request: DomainCheckRequest, ctx: WorkflowContext
    ) -> RequestResponse[DomainCheckRequest, bool]:
        """Intercept domain check requests from sub-workflows."""
        print(f"Intercepted domain check for: {request.domain}")

        if request.domain in self.approved_domains:
            print(f"Domain {request.domain} is pre-approved!")
            return RequestResponse[DomainCheckRequest, bool].handled(True)
        print(f"Domain {request.domain} unknown, forwarding to external check")
        return RequestResponse.forward()

    @handler(output_types=[])
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        """Collect validation results."""
        print(f"Collected result: {result.email} -> {result.is_valid} ({result.reason})")
        self.results.append(result)
        if len(self.results) == self.expected_result_count:
            print("All results collected, workflow completed!")
            await ctx.add_event(WorkflowFinished())


async def main():
    """Main function to run the sub-workflow example."""
    print("Setting up sub-workflow...")

    # Step 1: Create the email validation sub-workflow
    email_validator = EmailValidator()
    email_request_info = RequestInfoExecutor(id="email_request_info")

    validation_workflow = (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, email_request_info)
        .add_edge(email_request_info, email_validator)
        .build()
    )

    print("Setting up parent workflow...")

    # Step 2: Create the parent workflow with interception
    orchestrator = SmartEmailOrchestrator()
    workflow_executor = WorkflowExecutor(validation_workflow, id="email_validator_workflow")
    main_request_info = RequestInfoExecutor(id="main_request_info")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(orchestrator)
        .add_edge(orchestrator, workflow_executor)
        .add_edge(workflow_executor, orchestrator)
        .add_edge(orchestrator, main_request_info)
        .add_edge(main_request_info, workflow_executor)
        .build()
    )

    # Step 3: Test emails - some known domains, some unknown
    test_emails = [
        "user@example.com",  # Should be intercepted and approved
        "admin@company.com",  # Should be intercepted and approved
        "guest@partner.com",  # Should be forwarded externally and approved
        "guest@unknown.com",  # Should be forwarded externally and denied
    ]

    manually_approved_domains = ["partner.com"]

    print(f"\nTesting with emails: {test_emails}")
    print("=" * 60)

    # Step 4: Run the workflow
    result = await main_workflow.run(test_emails)

    # Step 5: Handle any external requests
    request_events = result.get_request_info_events()
    running = True

    if request_events:
        while running and request_events:
            print(f"\nGot {len(request_events)} external request(s)")

            # Handle events (simulate external services)
            external_responses = {}
            for event in request_events:
                if isinstance(event, WorkflowFinished):
                    print(f"   Workflow finished: {event}")
                    running = False
                    continue

                # Only process RequestInfoEvent types
                if hasattr(event, "data") and event.data is not None:
                    print(f"   Request: {event.data}")

                    # For this demo, approve unknown.org from external service
                    if hasattr(event.data, "domain"):
                        domain = event.data.domain
                        approved = domain in manually_approved_domains
                        external_responses[event.request_id] = approved
                        print(f"   External check for {domain}: {approved}")
                else:
                    print(f"   Event without data: {event}")

            # Send responses back
            request_events = await main_workflow.send_responses(external_responses)
            print("\nResponses sent back to the workflow!")
    else:
        print("\nAll requests were intercepted and handled internally!")

    print("\nFinal Results:")
    print("=" * 60)
    for result in orchestrator.results:
        status = "PASS" if result.is_valid else "FAIL"
        print(f"{status} {result.email}: {result.reason}")

    print(f"\nValidated {len(orchestrator.results)} emails total")


if __name__ == "__main__":
    asyncio.run(main())
