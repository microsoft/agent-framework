# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

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
        SubWorkflowRequestInfo,
        SubWorkflowResponse,
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


# Sub-workflow executor (completely standard)
class EmailValidator(Executor):
    """Validates email addresses - doesn't know it's in a sub-workflow."""

    def __init__(self):
        super().__init__(id="email_validator")
        self._pending_email = None

    @handler(output_types=[DomainCheckRequest, ValidationResult])
    async def validate(self, request: EmailValidationRequest, ctx: WorkflowContext) -> None:
        """Validate an email address."""
        print(f"Validating email: {request.email}")
        self._pending_email = request.email

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
    async def handle_domain_response(self, approved: bool, ctx: WorkflowContext) -> None:
        """Handle domain check response."""
        print(f"Domain check result: {approved}")
        if self._pending_email:
            result = ValidationResult(
                email=self._pending_email,
                is_valid=approved,
                reason="Domain approved" if approved else "Domain not approved",
            )
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            self._pending_email = None


# Parent workflow with request interception
class SmartEmailOrchestrator(Executor):
    """Parent orchestrator that can intercept domain checks."""

    def __init__(self, approved_domains: set[str] | None = None):
        super().__init__(id="email_orchestrator")
        self.approved_domains = approved_domains or {"example.com", "test.org", "company.com"}
        self.results: list[ValidationResult] = []
        print(f"Orchestrator knows about domains: {self.approved_domains}")

    @handler(output_types=[EmailValidationRequest])
    async def start_validation(self, emails: list[str], ctx: WorkflowContext) -> None:
        """Start validating a batch of emails."""
        print(f"Starting validation of {len(emails)} emails")
        for email in emails:
            request = EmailValidationRequest(email=email)
            await ctx.send_message(request, target_id="email_validator_workflow")

    @intercepts_request(DomainCheckRequest)
    async def check_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> RequestResponse:
        """Intercept domain check requests from sub-workflows."""
        print(f"Intercepted domain check for: {request.domain}")

        if request.domain in self.approved_domains:
            print(f"Domain {request.domain} is pre-approved!")
            return RequestResponse.handled(True)
        print(f"Domain {request.domain} unknown, forwarding to external check")
        return RequestResponse.forward()

    @handler(output_types=[])
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        """Collect validation results."""
        print(f"Collected result: {result.email} -> {result.is_valid} ({result.reason})")
        self.results.append(result)

    # Remove the placeholder handler - the base Executor class will handle it automatically
    # @handler(output_types=[])
    # async def handle_sub_workflow_request(self, request: SubWorkflowRequestInfo, ctx: WorkflowContext) -> None:
    #     """Handle sub-workflow requests - enables the interception mechanism."""
    #     # This handler ensures SubWorkflowRequestInfo messages are routed to the @intercepts_request methods
    #     pass


async def main():
    """Main function to run the sub-workflow example."""
    print("Setting up sub-workflow...")

    # Step 1: Create the email validation sub-workflow
    email_validator = EmailValidator()
    request_info = RequestInfoExecutor()

    validation_workflow = (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, request_info)
        .add_edge(request_info, email_validator)
        .build()
    )

    print("Setting up parent workflow...")

    # Step 2: Create the parent workflow with interception
    orchestrator = SmartEmailOrchestrator()
    workflow_executor = WorkflowExecutor(validation_workflow, id="email_validator_workflow")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(orchestrator)
        .add_edge(orchestrator, workflow_executor)
        .add_edge(workflow_executor, orchestrator)
        .add_edge(orchestrator, request_info)
        .add_edge(request_info, workflow_executor)
        .build()
    )

    # Step 3: Test emails - some known domains, some unknown
    test_emails = [
        "user@example.com",  # Should be intercepted and approved
        "admin@company.com",  # Should be intercepted and approved
        "guest@unknown.org",  # Should be forwarded externally
    ]

    print(f"\nTesting with emails: {test_emails}")
    print("=" * 60)

    # Step 4: Run the workflow
    result = await main_workflow.run(test_emails)

    # Step 5: Handle any external requests
    request_events = result.get_request_info_events()
    if request_events:
        print(f"\nGot {len(request_events)} external request(s)")
        for event in request_events:
            print(f"   Request: {event.data}")

        # Handle external requests (simulate external services)
        external_responses = {}
        for event in request_events:
            # For this demo, approve unknown.org from external service
            if hasattr(event.data, "domain"):
                domain = event.data.domain
                approved = domain == "unknown.org"  # External service approves this
                external_responses[event.request_id] = approved
                print(f"   External check for {domain}: {approved}")

        # Send responses back
        await main_workflow.send_responses(external_responses)
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
