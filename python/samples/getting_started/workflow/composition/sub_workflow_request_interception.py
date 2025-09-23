# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import (
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
    intercepts_request,
)

"""
Sample: Sub-Workflows with Request Interception

This sample shows how to:
1. Create workflows that execute other workflows as sub-workflows
2. Intercept requests from sub-workflows in parent workflows using @intercepts_request
3. Conditionally handle or forward requests using RequestResponse.handled() and RequestResponse.forward()
4. Handle external requests that are forwarded by the parent workflow
5. Proper request/response correlation for concurrent processing

The example simulates an email validation system where:
- Sub-workflows validate multiple email addresses concurrently
- Parent workflows can intercept domain check requests for optimization
- Known domains (example.com, company.com) are approved locally
- Unknown domains (unknown.org) are forwarded to external services
- Request correlation ensures each email gets the correct domain check response
- External domain check requests are processed and responses routed back correctly

Key concepts demonstrated:
- WorkflowExecutor: Wraps a workflow to make it behave as an executor
- @intercepts_request: Decorator for parent workflows to handle sub-workflow requests
- RequestResponse: Enables conditional handling vs forwarding of requests
- Request correlation: Using request_id to match responses with original requests
- Concurrent processing: Multiple emails processed simultaneously without interference
- External request routing: RequestInfoExecutor handles forwarded external requests
- Sub-workflow isolation: Sub-workflows work normally without knowing they're nested
- Sub-workflows complete by yielding outputs when validation is finished

Prerequisites:
- No external services required (external calls are simulated via `RequestInfoExecutor`).

Simple flow visualization:

  Parent Orchestrator (@intercepts_request)
      |
      |  EmailValidationRequest(email) x3 (concurrent)
      v
    [ Sub-workflow: WorkflowExecutor(EmailValidator) ]
      |
      |  DomainCheckRequest(domain) with request_id correlation
      v
  Interception? yes -> handled locally with RequestResponse.handled(True)
               no  -> forwarded to RequestInfoExecutor -> external service
                                |
                                v
                     Response routed back to sub-workflow using request_id
"""


# 1. Define domain-specific message types
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


# 2. Implement the sub-workflow executor (completely standard)
class EmailValidator(Executor):
    """Validates email addresses - doesn't know it's in a sub-workflow."""

    def __init__(self):
        """Initialize the EmailValidator executor."""
        super().__init__(id="email_validator")
        # Use a dict to track multiple pending emails by request_id
        self._pending_emails: dict[str, str] = {}

    @handler
    async def validate_request(
        self,
        request: EmailValidationRequest,
        ctx: WorkflowContext[DomainCheckRequest | ValidationResult, ValidationResult],
    ) -> None:
        """Validate an email address."""
        print(f"🔍 Sub-workflow validating email: {request.email}")

        # Extract domain
        domain = request.email.split("@")[1] if "@" in request.email else ""

        if not domain:
            print(f"❌ Invalid email format: {request.email}")
            result = ValidationResult(email=request.email, is_valid=False, reason="Invalid email format")
            await ctx.yield_output(result)
            return

        print(f"🌐 Sub-workflow requesting domain check for: {domain}")
        # Request domain check
        domain_check = DomainCheckRequest(domain=domain)
        # Store the pending email with the request_id for correlation
        self._pending_emails[domain_check.request_id] = request.email
        await ctx.send_message(domain_check, target_id="email_request_info")

    @handler
    async def handle_domain_response(
        self,
        response: RequestResponse[DomainCheckRequest, bool],
        ctx: WorkflowContext[ValidationResult, ValidationResult],
    ) -> None:
        """Handle domain check response from RequestInfo with correlation."""
        approved = bool(response.data)
        domain = (
            response.original_request.domain
            if (hasattr(response, "original_request") and response.original_request)
            else "unknown"
        )
        print(f"📬 Sub-workflow received domain response for '{domain}': {approved}")

        # Find the corresponding email using the request_id
        request_id = (
            response.original_request.request_id
            if (hasattr(response, "original_request") and response.original_request)
            else None
        )
        if request_id and request_id in self._pending_emails:
            email = self._pending_emails.pop(request_id)  # Remove from pending
            result = ValidationResult(
                email=email,
                is_valid=approved,
                reason="Domain approved" if approved else "Domain not approved",
            )
            print(f"✅ Sub-workflow completing validation for: {email}")
            await ctx.yield_output(result)


# 3. Implement the parent workflow with request interception
class SmartEmailOrchestrator(Executor):
    """Parent orchestrator that can intercept domain checks."""

    approved_domains: set[str] = set()

    def __init__(self, approved_domains: set[str] | None = None):
        """Initialize the SmartEmailOrchestrator with approved domains.

        Args:
            approved_domains: Set of pre-approved domains, defaults to example.com, test.org, company.com
        """
        super().__init__(id="email_orchestrator", approved_domains=approved_domains)
        self._results: list[ValidationResult] = []

    @handler
    async def start_validation(self, emails: list[str], ctx: WorkflowContext[EmailValidationRequest]) -> None:
        """Start validating a batch of emails."""
        print(f"📧 Starting validation of {len(emails)} email addresses")
        print("=" * 60)
        for email in emails:
            print(f"📤 Sending '{email}' to sub-workflow for validation")
            request = EmailValidationRequest(email=email)
            await ctx.send_message(request, target_id="email_validator_workflow")

    @intercepts_request
    async def check_domain(
        self, request: DomainCheckRequest, ctx: WorkflowContext
    ) -> RequestResponse[DomainCheckRequest, bool]:
        """Intercept domain check requests from sub-workflows."""
        print(f"🔍 Parent intercepting domain check for: {request.domain}")
        if request.domain in self.approved_domains:
            print(f"✅ Domain '{request.domain}' is pre-approved locally!")
            return RequestResponse[DomainCheckRequest, bool].handled(True)
        print(f"❓ Domain '{request.domain}' unknown, forwarding to external service...")
        return RequestResponse[DomainCheckRequest, bool].forward()

    @handler
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        """Collect validation results. It comes from the sub-workflow yielded output."""
        status_icon = "✅" if result.is_valid else "❌"
        print(f"📥 {status_icon} Validation result: {result.email} -> {result.reason}")
        self._results.append(result)

    @property
    def results(self) -> list[ValidationResult]:
        """Get the collected validation results."""
        return self._results


async def run_example() -> None:
    """Run the sub-workflow example."""
    print("🚀 Setting up sub-workflow with request interception...")
    print()

    # 4. Build the sub-workflow
    email_validator = EmailValidator()
    # Match the target_id used in EmailValidator ("email_request_info")
    request_info = RequestInfoExecutor(id="email_request_info")

    validation_workflow = (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, request_info)
        .add_edge(request_info, email_validator)
        .build()
    )

    # 5. Build the parent workflow with interception
    orchestrator = SmartEmailOrchestrator(approved_domains={"example.com", "company.com"})
    workflow_executor = WorkflowExecutor(validation_workflow, id="email_validator_workflow")
    # Add a RequestInfoExecutor to handle forwarded external requests
    main_request_info = RequestInfoExecutor(id="main_request_info")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(orchestrator)
        .add_edge(orchestrator, workflow_executor)
        .add_edge(workflow_executor, orchestrator)
        # Add edges for external request handling
        .add_edge(orchestrator, main_request_info)
        .add_edge(main_request_info, workflow_executor)  # Route external responses to sub-workflow
        .build()
    )

    # 6. Prepare test inputs: known domain, unknown domain
    test_emails = [
        "user@example.com",  # Should be intercepted and approved
        "admin@company.com",  # Should be intercepted and approved
        "guest@unknown.org",  # Should be forwarded externally
    ]

    # 7. Run the workflow
    result = await main_workflow.run(test_emails)

    # 8. Handle any external requests
    request_events = result.get_request_info_events()
    if request_events:
        print(f"\n🌐 Handling {len(request_events)} external request(s)...")
        for event in request_events:
            if event.data and hasattr(event.data, "domain"):
                print(f"🔍 External domain check needed for: {event.data.domain}")

        # Simulate external responses
        external_responses: dict[str, bool] = {}
        for event in request_events:
            # Simulate external domain checking
            if event.data and hasattr(event.data, "domain"):
                domain = event.data.domain
                # Let's say unknown.org is actually approved externally
                approved = domain == "unknown.org"
                print(f"🌐 External service response for '{domain}': {'APPROVED' if approved else 'REJECTED'}")
                external_responses[event.request_id] = approved

        # 9. Send external responses
        await main_workflow.send_responses(external_responses)
    else:
        print("\n🎯 All requests were intercepted and handled locally!")

    # 10. Display final summary
    print("\n📊 Final Results Summary:")
    print("=" * 60)
    for result in orchestrator.results:
        status = "✅ VALID" if result.is_valid else "❌ INVALID"
        print(f"{status} {result.email}: {result.reason}")

    print(f"\n🏁 Processed {len(orchestrator.results)} emails total")


if __name__ == "__main__":
    asyncio.run(run_example())
