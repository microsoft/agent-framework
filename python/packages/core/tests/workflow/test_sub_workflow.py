# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass, field
from uuid import uuid4

from typing_extensions import Never

from agent_framework import (
    Executor,
    SubWorkflowRequestMessage,
    SubWorkflowResponseMessage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
    response_handler,
)


# Test message types
@dataclass
class EmailValidationRequest:
    """Request to validate an email address."""

    email: str


@dataclass
class DomainCheckRequest:
    """Request to check if a domain is approved."""

    id: str = field(default_factory=lambda: str(uuid4()))
    domain: str = ""
    email: str = ""  # Include original email for correlation


@dataclass
class ValidationResult:
    """Result of email validation."""

    email: str
    is_valid: bool
    reason: str


class Coordinator(Executor):
    """Coordinator executor in the parent workflow for simple sub-workflow tests."""

    def __init__(self, cache: dict[str, bool] | None = None) -> None:
        super().__init__(id="basic_parent")
        self.result: ValidationResult | None = None
        self.cache: dict[str, bool] = dict(cache) if cache is not None else {}
        self._pending_sub_workflow_requests: dict[str, SubWorkflowRequestMessage] = {}

    @handler
    async def start(self, email: str, ctx: WorkflowContext[EmailValidationRequest]) -> None:
        request = EmailValidationRequest(email=email)
        await ctx.send_message(request)

    @handler
    async def handle_domain_request(
        self,
        sub_workflow_request: SubWorkflowRequestMessage,
        ctx: WorkflowContext[SubWorkflowResponseMessage],
    ) -> None:
        """Handle requests from sub-workflows with optional caching."""
        if not isinstance(sub_workflow_request.source_event.data, DomainCheckRequest):
            raise ValueError("Unexpected request type")

        domain_request = sub_workflow_request.source_event.data

        if domain_request.domain in self.cache:
            # Return cached result
            await ctx.send_message(sub_workflow_request.create_response(self.cache[domain_request.domain]))
        else:
            # Not in cache, forward to external
            self._pending_sub_workflow_requests[domain_request.id] = sub_workflow_request
            await ctx.request_info(domain_request, bool)

    @response_handler
    async def handle_domain_response(
        self,
        original_request: DomainCheckRequest,
        is_approved: bool,
        ctx: WorkflowContext[SubWorkflowResponseMessage],
    ) -> None:
        """Handle domain check response with correlation and send the response back to the sub-workflow."""
        if original_request.id not in self._pending_sub_workflow_requests:
            raise ValueError("No pending sub-workflow request for the given domain check response")

        sub_workflow_request = self._pending_sub_workflow_requests.pop(original_request.id)
        await ctx.send_message(sub_workflow_request.create_response(is_approved))

    @handler
    async def collect(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        self.result = result


class EmailFormatValidator(Executor):
    """Validates the format of an email address."""

    def __init__(self):
        super().__init__(id="email_format_validator")

    @handler
    async def validate(
        self, request: EmailValidationRequest, ctx: WorkflowContext[DomainCheckRequest, ValidationResult]
    ) -> None:
        """Validate email format and extract domain."""
        email = request.email
        if "@" not in email:
            result = ValidationResult(email=email, is_valid=False, reason="Invalid email format")
            await ctx.yield_output(result)
            return

        domain = email.split("@")[1]
        domain_check = DomainCheckRequest(domain=domain, email=email)
        await ctx.send_message(domain_check)


class EmailDomainValidator(Executor):
    """Validates email addresses in a sub-workflow."""

    def __init__(self):
        super().__init__(id="email_domain_validator")

    @handler
    async def validate_request(
        self, request: DomainCheckRequest, ctx: WorkflowContext[DomainCheckRequest, ValidationResult]
    ) -> None:
        """Validate an email address."""
        domain = request.domain

        if not domain:
            result = ValidationResult(email=request.email, is_valid=False, reason="Invalid email format")
            await ctx.yield_output(result)
            return

        # Request domain check from external source
        await ctx.request_info(request, bool)

    @response_handler
    async def handle_domain_response(
        self,
        original_request: DomainCheckRequest,
        is_approved: bool,
        ctx: WorkflowContext[Never, ValidationResult],
    ) -> None:
        """Handle domain check response with correlation."""
        # Use the original email from the correlated response
        result = ValidationResult(
            email=original_request.email,
            is_valid=is_approved,
            reason="Domain approved" if is_approved else "Domain not approved",
        )
        await ctx.yield_output(result)


# Test helper functions
def create_email_validation_workflow() -> Workflow:
    """Create a standard email validation workflow."""
    email_format_validator = EmailFormatValidator()
    email_domain_validator = EmailDomainValidator()

    return (
        WorkflowBuilder()
        .set_start_executor(email_format_validator)
        .add_edge(email_format_validator, email_domain_validator)
        .build()
    )


async def test_basic_sub_workflow() -> None:
    """Test basic sub-workflow execution without interception."""
    # Create sub-workflow
    validation_workflow = create_email_validation_workflow()

    # Create parent workflow without interception
    parent = Coordinator()
    workflow_executor = WorkflowExecutor(validation_workflow, "email_validation_workflow")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, workflow_executor)
        .add_edge(workflow_executor, parent)
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
    parent = Coordinator(cache={"example.com": True, "internal.org": True})
    workflow_executor = WorkflowExecutor(validation_workflow, "email_workflow")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, workflow_executor)
        .add_edge(workflow_executor, parent)
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
            self._pending_sub_workflow_requests: dict[str, SubWorkflowRequestMessage] = {}

        @handler
        async def start(self, data: dict[str, str], ctx: WorkflowContext[EmailValidationRequest]) -> None:
            # Send to different sub-workflows
            await ctx.send_message(EmailValidationRequest(email=data["email1"]), target_id="workflow_a")
            await ctx.send_message(EmailValidationRequest(email=data["email2"]), target_id="workflow_b")

        @handler
        async def handle_domain_request(
            self,
            sub_workflow_request: SubWorkflowRequestMessage,
            ctx: WorkflowContext[SubWorkflowResponseMessage],
        ) -> None:
            """Handle requests from sub-workflows with optional caching."""
            if not isinstance(sub_workflow_request.source_event.data, DomainCheckRequest):
                raise ValueError("Unexpected request type")

            domain_request = sub_workflow_request.source_event.data

            if sub_workflow_request.executor_id == "workflow_a" and domain_request.domain == "strict.com":
                # Strict rules for workflow A
                await ctx.send_message(
                    sub_workflow_request.create_response(True), target_id=sub_workflow_request.executor_id
                )
                return
            if sub_workflow_request.executor_id == "workflow_b" and domain_request.domain.endswith(".com"):
                # Lenient rules for workflow B
                await ctx.send_message(
                    sub_workflow_request.create_response(True), target_id=sub_workflow_request.executor_id
                )
                return

            # Unknown source, forward to external
            self._pending_sub_workflow_requests[domain_request.id] = sub_workflow_request
            await ctx.request_info(domain_request, bool)

        @response_handler
        async def handle_domain_response(
            self,
            original_request: DomainCheckRequest,
            is_approved: bool,
            ctx: WorkflowContext[SubWorkflowResponseMessage],
        ) -> None:
            """Handle domain check response with correlation and send the response back to the sub-workflow."""
            if original_request.id not in self._pending_sub_workflow_requests:
                raise ValueError("No pending sub-workflow request for the given domain check response")

            sub_workflow_request = self._pending_sub_workflow_requests.pop(original_request.id)
            await ctx.send_message(
                sub_workflow_request.create_response(is_approved), target_id=sub_workflow_request.executor_id
            )

        @handler
        async def collect(self, result: ValidationResult, ctx: WorkflowContext) -> None:
            self.results[result.email] = result

    # Create two identical sub-workflows
    workflow_a = create_email_validation_workflow()
    workflow_b = create_email_validation_workflow()

    parent = MultiWorkflowParent()
    executor_a = WorkflowExecutor(workflow_a, "workflow_a")
    executor_b = WorkflowExecutor(workflow_b, "workflow_b")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, executor_a)
        .add_edge(parent, executor_b)
        .add_edge(executor_a, parent)
        .add_edge(executor_b, parent)
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
            self._pending_sub_workflow_requests: dict[str, SubWorkflowRequestMessage] = {}

        @handler
        async def start(self, emails: list[str], ctx: WorkflowContext[EmailValidationRequest]) -> None:
            """Send multiple concurrent requests to the same sub-workflow."""
            # Send all requests concurrently to the same workflow executor
            for email in emails:
                request = EmailValidationRequest(email=email)
                await ctx.send_message(request)

        @handler
        async def handle_domain_request(
            self,
            sub_workflow_request: SubWorkflowRequestMessage,
            ctx: WorkflowContext[SubWorkflowResponseMessage],
        ) -> None:
            """Handle requests from sub-workflows with optional caching."""
            if not isinstance(sub_workflow_request.source_event.data, DomainCheckRequest):
                raise ValueError("Unexpected request type")

            domain_request = sub_workflow_request.source_event.data
            self._pending_sub_workflow_requests[domain_request.id] = sub_workflow_request
            await ctx.request_info(domain_request, bool)

        @response_handler
        async def handle_domain_response(
            self,
            original_request: DomainCheckRequest,
            is_approved: bool,
            ctx: WorkflowContext[SubWorkflowResponseMessage],
        ) -> None:
            """Handle domain check response with correlation and send the response back to the sub-workflow."""
            if original_request.id not in self._pending_sub_workflow_requests:
                raise ValueError("No pending sub-workflow request for the given domain check response")

            sub_workflow_request = self._pending_sub_workflow_requests.pop(original_request.id)
            await ctx.send_message(sub_workflow_request.create_response(is_approved))

        @handler
        async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
            """Collect results from concurrent executions."""
            self.results.append(result)

    # Create sub-workflow for email validation
    validation_workflow = create_email_validation_workflow()

    # Create parent workflow
    processor = ConcurrentProcessor()
    workflow_executor = WorkflowExecutor(validation_workflow, "email_workflow")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(processor)
        .add_edge(processor, workflow_executor)
        .add_edge(workflow_executor, processor)
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
