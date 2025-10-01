# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any

from typing_extensions import Never

from agent_framework import (
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
)


# Test message types
@dataclass
class EmailValidationRequest:
    """Request to validate an email address."""

    email: str


@dataclass
class DomainCheckRequest(RequestInfoMessage):
    """Request to check if a domain is approved."""

    domain: str = ""
    email: str = ""  # Include original email for correlation


@dataclass
class ValidationResult:
    """Result of email validation."""

    email: str
    is_valid: bool
    reason: str


# Test helper functions
def create_email_validation_workflow() -> Workflow:
    """Create a standard email validation workflow."""
    email_validator = EmailValidator()
    email_request_info = RequestInfoExecutor(id="email_request_info")

    return (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, email_request_info)
        .add_edge(email_request_info, email_validator)
        .build()
    )


class BasicParent(Executor):
    """Basic parent executor for simple sub-workflow tests."""

    def __init__(self, cache: dict[str, bool] | None = None) -> None:
        super().__init__(id="basic_parent")
        self.result: ValidationResult | None = None
        self.cache: dict[str, bool] = dict(cache) if cache is not None else {}

    @handler
    async def start(self, email: str, ctx: WorkflowContext[EmailValidationRequest]) -> None:
        request = EmailValidationRequest(email=email)
        await ctx.send_message(request, target_id="email_workflow")

    @handler
    async def handle_domain_request(
        self,
        request: DomainCheckRequest,
        ctx: WorkflowContext[RequestResponse[DomainCheckRequest, Any] | DomainCheckRequest],
    ) -> None:
        """Handle requests from sub-workflows with optional caching."""
        domain_request = request

        if domain_request.domain in self.cache:
            # Return cached result
            response = RequestResponse(
                data=self.cache[domain_request.domain], original_request=request, request_id=request.request_id
            )
            await ctx.send_message(response, target_id=request.source_executor_id)
        else:
            # Not in cache, forward to external
            await ctx.send_message(request)

    @handler
    async def collect(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        self.result = result


# Test executors
class EmailValidator(Executor):
    """Validates email addresses in a sub-workflow."""

    def __init__(self):
        super().__init__(id="email_validator")

    @handler
    async def validate_request(
        self, request: EmailValidationRequest, ctx: WorkflowContext[DomainCheckRequest, ValidationResult]
    ) -> None:
        """Validate an email address."""
        # Extract domain and check if it's approved
        domain = request.email.split("@")[1] if "@" in request.email else ""

        if not domain:
            result = ValidationResult(email=request.email, is_valid=False, reason="Invalid email format")
            await ctx.yield_output(result)
            return

        # Request domain check from external source
        domain_check = DomainCheckRequest(domain=domain, email=request.email)
        await ctx.send_message(domain_check)

    @handler
    async def handle_domain_response(
        self, response: RequestResponse[DomainCheckRequest, bool], ctx: WorkflowContext[Never, ValidationResult]
    ) -> None:
        """Handle domain check response with correlation."""
        # Use the original email from the correlated response
        result = ValidationResult(
            email=response.original_request.email,
            is_valid=response.data or False,
            reason="Domain approved" if response.data else "Domain not approved",
        )
        await ctx.yield_output(result)


class ParentOrchestrator(Executor):
    """Parent workflow orchestrator with domain knowledge."""

    def __init__(self, approved_domains: set[str] | None = None) -> None:
        super().__init__(id="parent_orchestrator")
        self.approved_domains: set[str] = (
            set(approved_domains) if approved_domains is not None else {"example.com", "test.org"}
        )
        self.results: list[ValidationResult] = []

    @handler
    async def start(self, emails: list[str], ctx: WorkflowContext[EmailValidationRequest]) -> None:
        """Start processing emails."""
        for email in emails:
            request = EmailValidationRequest(email=email)
            await ctx.send_message(request, target_id="email_workflow")

    @handler
    async def handle_domain_request(
        self,
        request: DomainCheckRequest,
        ctx: WorkflowContext[RequestResponse[DomainCheckRequest, Any] | DomainCheckRequest],
    ) -> None:
        """Handle requests from sub-workflows."""
        domain_request = request

        # Check if we know this domain
        if domain_request.domain in self.approved_domains:
            # Send response back to sub-workflow
            response = RequestResponse(data=True, original_request=request, request_id=request.request_id)
            await ctx.send_message(response, target_id=request.source_executor_id)
        else:
            # We don't know this domain, forward to external
            await ctx.send_message(request)

    @handler
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        """Collect validation results."""
        self.results.append(result)


async def test_basic_sub_workflow() -> None:
    """Test basic sub-workflow execution without interception."""
    # Create sub-workflow
    validation_workflow = create_email_validation_workflow()

    # Create parent workflow without interception
    parent = BasicParent()
    workflow_executor = WorkflowExecutor(validation_workflow, "email_workflow")
    main_request_info = RequestInfoExecutor(id="main_request_info")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, workflow_executor)
        .add_edge(workflow_executor, parent)
        .add_edge(workflow_executor, main_request_info)
        .add_edge(main_request_info, workflow_executor)  # CRITICAL: For RequestResponse routing
        .build()
    )

    # Run workflow with mocked external response
    result = await main_workflow.run("test@example.com")

    # Get request event and respond
    request_events = result.get_request_info_events()
    assert len(request_events) == 1
    assert isinstance(request_events[0].data, DomainCheckRequest)
    assert request_events[0].data.domain == "example.com"

    # Send response through the main workflow
    await main_workflow.send_responses({
        request_events[0].request_id: True  # Domain is approved
    })

    # Check result
    assert parent.result is not None
    assert parent.result.email == "test@example.com"
    assert parent.result.is_valid is True


async def test_sub_workflow_with_interception():
    """Test sub-workflow with parent interception and conditional forwarding."""
    # Create sub-workflow
    validation_workflow = create_email_validation_workflow()

    # Create parent workflow with interception cache
    parent = BasicParent(cache={"example.com": True, "internal.org": True})
    workflow_executor = WorkflowExecutor(validation_workflow, "email_workflow")
    parent_request_info = RequestInfoExecutor(id="request_info")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, workflow_executor)
        .add_edge(workflow_executor, parent)
        .add_edge(parent, parent_request_info)  # For forwarded requests
        .add_edge(parent_request_info, workflow_executor)  # For RequestResponse routing
        .build()
    )

    # Test 1: Email with cached domain (intercepted)
    result = await main_workflow.run("user@example.com")
    request_events = result.get_request_info_events()
    assert len(request_events) == 0  # No external requests, handled from cache
    assert parent.result is not None
    assert parent.result.email == "user@example.com"
    assert parent.result.is_valid is True

    # Test 2: Email with unknown domain (forwarded to external)
    parent.result = None
    result = await main_workflow.run("user@unknown.com")
    request_events = result.get_request_info_events()
    assert len(request_events) == 1  # Forwarded to external
    assert isinstance(request_events[0].data, DomainCheckRequest)
    assert request_events[0].data.domain == "unknown.com"

    # Send external response
    await main_workflow.send_responses({
        request_events[0].request_id: False  # Domain not approved
    })
    assert parent.result is not None
    assert parent.result.email == "user@unknown.com"
    assert parent.result.is_valid is False

    # Test 3: Another cached domain
    parent.result = None
    result = await main_workflow.run("user@internal.org")
    request_events = result.get_request_info_events()
    assert len(request_events) == 0  # Handled from cache
    assert parent.result is not None
    assert parent.result.is_valid is True


async def test_workflow_scoped_interception() -> None:
    """Test interception scoped to specific sub-workflows."""

    class MultiWorkflowParent(Executor):
        """Parent handling multiple sub-workflows."""

        def __init__(self) -> None:
            super().__init__(id="multi_parent")
            self.results: dict[str, ValidationResult] = {}

        @handler
        async def start(self, data: dict[str, str], ctx: WorkflowContext[EmailValidationRequest]) -> None:
            # Send to different sub-workflows
            await ctx.send_message(EmailValidationRequest(email=data["email1"]), target_id="workflow_a")
            await ctx.send_message(EmailValidationRequest(email=data["email2"]), target_id="workflow_b")

        @handler
        async def handle_domain_request(
            self,
            request: DomainCheckRequest,
            ctx: WorkflowContext[RequestResponse[DomainCheckRequest, Any] | DomainCheckRequest],
        ) -> None:
            domain_request = request

            if request.source_executor_id == "workflow_a":
                # Strict rules for workflow A
                if domain_request.domain == "strict.com":
                    response = RequestResponse(data=True, original_request=request, request_id=request.request_id)
                    await ctx.send_message(response, target_id=request.source_executor_id)
                else:
                    # Forward to external
                    await ctx.send_message(request)
            elif request.source_executor_id == "workflow_b":
                # Lenient rules for workflow B
                if domain_request.domain.endswith(".com"):
                    response = RequestResponse(data=True, original_request=request, request_id=request.request_id)
                    await ctx.send_message(response, target_id=request.source_executor_id)
                else:
                    # Forward to external
                    await ctx.send_message(request)
            else:
                # Unknown source, forward to external
                await ctx.send_message(request)

        @handler
        async def collect(self, result: ValidationResult, ctx: WorkflowContext) -> None:
            self.results[result.email] = result

    # Create two identical sub-workflows
    workflow_a = create_email_validation_workflow()
    workflow_b = create_email_validation_workflow()

    parent = MultiWorkflowParent()
    executor_a = WorkflowExecutor(workflow_a, "workflow_a")
    executor_b = WorkflowExecutor(workflow_b, "workflow_b")
    parent_request_info = RequestInfoExecutor(id="request_info")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, executor_a)
        .add_edge(parent, executor_b)
        .add_edge(executor_a, parent)
        .add_edge(executor_b, parent)
        .add_edge(parent, parent_request_info)
        .add_edge(parent_request_info, executor_a)  # For RequestResponse routing
        .add_edge(parent_request_info, executor_b)  # For RequestResponse routing
        .build()
    )

    # Run test
    result = await main_workflow.run({"email1": "user@strict.com", "email2": "user@random.com"})

    # Workflow A should handle strict.com
    # Workflow B should handle any .com domain
    request_events = result.get_request_info_events()
    assert len(request_events) == 0  # Both handled internally

    assert len(parent.results) == 2
    assert parent.results["user@strict.com"].is_valid is True
    assert parent.results["user@random.com"].is_valid is True


async def test_concurrent_sub_workflow_execution() -> None:
    """Test that WorkflowExecutor can handle multiple concurrent invocations properly."""

    class ConcurrentProcessor(Executor):
        """Processor that sends multiple concurrent requests to the same sub-workflow."""

        def __init__(self) -> None:
            super().__init__(id="concurrent_processor")
            self.results: list[ValidationResult] = []

        @handler
        async def start(self, emails: list[str], ctx: WorkflowContext[EmailValidationRequest]) -> None:
            """Send multiple concurrent requests to the same sub-workflow."""
            # Send all requests concurrently to the same workflow executor
            for email in emails:
                request = EmailValidationRequest(email=email)
                await ctx.send_message(request, target_id="email_workflow")

        @handler
        async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
            """Collect results from concurrent executions."""
            self.results.append(result)

    # Create sub-workflow for email validation
    validation_workflow = create_email_validation_workflow()

    # Create parent workflow
    processor = ConcurrentProcessor()
    workflow_executor = WorkflowExecutor(validation_workflow, "email_workflow")
    parent_request_info = RequestInfoExecutor(id="request_info")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(processor)
        .add_edge(processor, workflow_executor)
        .add_edge(workflow_executor, processor)
        .add_edge(workflow_executor, parent_request_info)  # For external requests
        .add_edge(parent_request_info, workflow_executor)  # For RequestResponse routing
        .build()
    )

    # Test concurrent execution with multiple emails
    emails = [
        "user1@domain1.com",
        "user2@domain2.com",
        "user3@domain3.com",
        "user4@domain4.com",
        "user5@domain5.com",
    ]

    result = await main_workflow.run(emails)

    # Each email should generate one external request
    request_events = result.get_request_info_events()
    assert len(request_events) == len(emails)

    # Verify each request corresponds to the correct domain
    domains_requested = {event.data.domain for event in request_events}  # type: ignore[union-attr]
    expected_domains = {f"domain{i}.com" for i in range(1, 6)}
    assert domains_requested == expected_domains

    # Send responses for all requests (approve all domains)
    responses = {event.request_id: True for event in request_events}
    await main_workflow.send_responses(responses)

    # All results should be collected
    assert len(processor.results) == len(emails)

    # Verify each email was processed correctly
    result_emails = {result.email for result in processor.results}
    expected_emails = set(emails)
    assert result_emails == expected_emails

    # All should be valid since we approved all domains
    for result_obj in processor.results:
        assert result_obj.is_valid is True
        assert result_obj.reason == "Domain approved"

    # Verify that concurrent executions were properly isolated
    # (This is implicitly tested by the fact that we got correct results for all emails)
