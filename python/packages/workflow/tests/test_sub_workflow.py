# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import Field

from agent_framework_workflow import (
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowExecutor,
    handler,
    intercepts_request,
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


# Test executors
class EmailValidator(Executor):
    """Validates email addresses in a sub-workflow."""

    def __init__(self):
        super().__init__(id="email_validator")

    @handler
    async def validate_request(
        self, request: EmailValidationRequest, ctx: WorkflowContext[RequestInfoMessage | ValidationResult]
    ) -> None:
        """Validate an email address."""
        # Extract domain and check if it's approved
        domain = request.email.split("@")[1] if "@" in request.email else ""

        if not domain:
            result = ValidationResult(email=request.email, is_valid=False, reason="Invalid email format")
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            return

        # Request domain check from external source
        domain_check = DomainCheckRequest(domain=domain, email=request.email)
        await ctx.send_message(domain_check)

    @handler
    async def handle_domain_response(
        self, response: RequestResponse[DomainCheckRequest, bool], ctx: WorkflowContext[ValidationResult]
    ) -> None:
        """Handle domain check response with correlation."""
        # Use the original email from the correlated response
        result = ValidationResult(
            email=response.original_request.email,
            is_valid=response.data or False,
            reason="Domain approved" if response.data else "Domain not approved",
        )
        await ctx.add_event(WorkflowCompletedEvent(data=result))


class ParentOrchestrator(Executor):
    """Parent workflow orchestrator with domain knowledge."""

    approved_domains: set[str] = Field(default_factory=lambda: {"example.com", "test.org"})
    results: list[ValidationResult] = Field(default_factory=list)

    def __init__(self, approved_domains: set[str] | None = None, **kwargs: Any):
        if approved_domains is not None:
            kwargs["approved_domains"] = approved_domains
        super().__init__(id="parent_orchestrator", **kwargs)

    @handler
    async def start(self, emails: list[str], ctx: WorkflowContext[EmailValidationRequest]) -> None:
        """Start processing emails."""
        for email in emails:
            request = EmailValidationRequest(email=email)
            await ctx.send_message(request, target_id="email_workflow")

    @intercepts_request
    async def check_domain(
        self, request: DomainCheckRequest, ctx: WorkflowContext[Any]
    ) -> RequestResponse[DomainCheckRequest, bool]:
        """Intercept domain check requests from sub-workflows."""
        # Check if we know this domain
        if request.domain in self.approved_domains:
            return RequestResponse[DomainCheckRequest, bool].handled(True)

        # We don't know this domain, forward to external
        return RequestResponse[DomainCheckRequest, bool].forward()

    @handler
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext[None]) -> None:
        """Collect validation results."""
        self.results.append(result)


@pytest.mark.asyncio
async def test_basic_sub_workflow() -> None:
    """Test basic sub-workflow execution without interception."""
    # Create sub-workflow
    email_validator = EmailValidator()
    email_request_info = RequestInfoExecutor(id="email_request_info")

    validation_workflow = (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, email_request_info)
        .add_edge(email_request_info, email_validator)
        .build()
    )

    # Create parent workflow without interception
    class SimpleParent(Executor):
        result: ValidationResult | None = Field(default=None)

        def __init__(self, **kwargs: Any):
            super().__init__(id="simple_parent", **kwargs)

        @handler
        async def start(self, email: str, ctx: WorkflowContext[EmailValidationRequest]) -> None:
            request = EmailValidationRequest(email=email)
            await ctx.send_message(request, target_id="email_workflow")

        @handler
        async def collect(self, result: ValidationResult, ctx: WorkflowContext[None]) -> None:
            self.result = result

    parent = SimpleParent()
    workflow_executor = WorkflowExecutor(validation_workflow, id="email_workflow")
    main_request_info = RequestInfoExecutor(id="main_request_info")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, workflow_executor)
        .add_edge(workflow_executor, parent)
        .add_edge(workflow_executor, main_request_info)
        .add_edge(main_request_info, workflow_executor)  # CRITICAL: For SubWorkflowResponse routing
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


@pytest.mark.asyncio
async def test_sub_workflow_with_interception():
    """Test sub-workflow with parent interception of requests."""
    # Create sub-workflow
    email_validator = EmailValidator()
    email_request_info = RequestInfoExecutor(id="email_request_info")

    validation_workflow = (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, email_request_info)
        .add_edge(email_request_info, email_validator)
        .build()
    )

    # Create parent workflow with interception
    parent = ParentOrchestrator(approved_domains={"example.com", "internal.org"})
    workflow_executor = WorkflowExecutor(validation_workflow, id="email_workflow")
    parent_request_info = RequestInfoExecutor()

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, workflow_executor)
        .add_edge(workflow_executor, parent)
        .add_edge(parent, parent_request_info)  # For forwarded requests
        .add_edge(parent_request_info, workflow_executor)  # For SubWorkflowResponse routing
        .build()
    )

    # Test 1: Email with known domain (intercepted)
    result = await main_workflow.run(["user@example.com"])

    # Should complete without external requests
    request_events = result.get_request_info_events()
    assert len(request_events) == 0  # No external requests, handled internally

    assert len(parent.results) == 1
    assert parent.results[0].email == "user@example.com"
    assert parent.results[0].is_valid is True
    assert parent.results[0].reason == "Domain approved"

    # Test 2: Email with unknown domain (forwarded)
    parent.results.clear()
    result = await main_workflow.run(["user@unknown.com"])

    # Should have external request
    request_events = result.get_request_info_events()
    assert len(request_events) == 1
    assert isinstance(request_events[0].data, DomainCheckRequest)
    assert request_events[0].data.domain == "unknown.com"

    # Send external response
    await main_workflow.send_responses({
        request_events[0].request_id: False  # Domain not approved
    })

    assert len(parent.results) == 1
    assert parent.results[0].email == "user@unknown.com"
    assert parent.results[0].is_valid is False
    assert parent.results[0].reason == "Domain not approved"


@pytest.mark.asyncio
async def test_conditional_forwarding() -> None:
    """Test conditional forwarding with RequestResponse.forward()."""

    class ConditionalParent(Executor):
        """Parent that conditionally handles requests."""

        cache: dict[str, bool] = Field(default_factory=lambda: {"cached.com": True})
        result: ValidationResult | None = Field(default=None)

        def __init__(self, **kwargs: Any):
            super().__init__(id="conditional_parent", **kwargs)

        @handler
        async def start(self, email: str, ctx: WorkflowContext[EmailValidationRequest]) -> None:
            request = EmailValidationRequest(email=email)
            await ctx.send_message(request, target_id="email_workflow")

        @intercepts_request
        async def check_domain(
            self, request: DomainCheckRequest, ctx: WorkflowContext[Any]
        ) -> RequestResponse[DomainCheckRequest, bool]:
            """Check cache first, then forward if not found."""
            if request.domain in self.cache:
                # Return cached result
                return RequestResponse[DomainCheckRequest, bool].handled(self.cache[request.domain])

            # Not in cache, forward to external
            return RequestResponse[DomainCheckRequest, bool].forward()

        @handler
        async def collect(self, result: ValidationResult, ctx: WorkflowContext[None]) -> None:
            self.result = result

    # Setup workflows
    email_validator = EmailValidator()
    request_info = RequestInfoExecutor()

    validation_workflow = (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, request_info)
        .add_edge(request_info, email_validator)
        .build()
    )

    parent = ConditionalParent()
    workflow_executor = WorkflowExecutor(validation_workflow, id="email_workflow")
    parent_request_info = RequestInfoExecutor()

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, workflow_executor)
        .add_edge(workflow_executor, parent)
        .add_edge(parent, parent_request_info)
        .add_edge(parent_request_info, workflow_executor)  # For SubWorkflowResponse routing
        .build()
    )

    # Test cached domain
    result = await main_workflow.run("user@cached.com")
    request_events = result.get_request_info_events()
    assert len(request_events) == 0  # Handled from cache
    assert parent.result is not None
    assert parent.result.is_valid is True

    # Test uncached domain
    parent.result = None
    result = await main_workflow.run("user@new.com")
    request_events = result.get_request_info_events()
    assert len(request_events) == 1  # Forwarded to external

    await main_workflow.send_responses({request_events[0].request_id: True})
    assert parent.result is not None
    assert parent.result.is_valid is True


@pytest.mark.asyncio
async def test_workflow_scoped_interception() -> None:
    """Test interception scoped to specific sub-workflows."""

    class MultiWorkflowParent(Executor):
        """Parent handling multiple sub-workflows."""

        results: dict[str, ValidationResult] = Field(default_factory=dict)

        def __init__(self, **kwargs: Any):
            super().__init__(id="multi_parent", **kwargs)

        @handler
        async def start(self, data: dict[str, str], ctx: WorkflowContext[EmailValidationRequest]) -> None:
            # Send to different sub-workflows
            await ctx.send_message(EmailValidationRequest(email=data["email1"]), target_id="workflow_a")
            await ctx.send_message(EmailValidationRequest(email=data["email2"]), target_id="workflow_b")

        @intercepts_request(from_workflow="workflow_a")
        async def check_domain_a(
            self, request: DomainCheckRequest, ctx: WorkflowContext[Any]
        ) -> RequestResponse[DomainCheckRequest, bool]:
            """Strict rules for workflow A."""
            if request.domain == "strict.com":
                return RequestResponse[DomainCheckRequest, bool].handled(True)
            return RequestResponse[DomainCheckRequest, bool].forward()

        @intercepts_request(from_workflow="workflow_b")
        async def check_domain_b(
            self, request: DomainCheckRequest, ctx: WorkflowContext[Any]
        ) -> RequestResponse[DomainCheckRequest, bool]:
            """Lenient rules for workflow B."""
            if request.domain.endswith(".com"):
                return RequestResponse[DomainCheckRequest, bool].handled(True)
            return RequestResponse[DomainCheckRequest, bool].forward()

        @handler
        async def collect(self, result: ValidationResult, ctx: WorkflowContext[None]) -> None:
            self.results[result.email] = result

    # Create two identical sub-workflows
    def create_validation_workflow():
        validator = EmailValidator()
        request_info = RequestInfoExecutor()
        return (
            WorkflowBuilder()
            .set_start_executor(validator)
            .add_edge(validator, request_info)
            .add_edge(request_info, validator)
            .build()
        )

    workflow_a = create_validation_workflow()
    workflow_b = create_validation_workflow()

    parent = MultiWorkflowParent()
    executor_a = WorkflowExecutor(workflow_a, id="workflow_a")
    executor_b = WorkflowExecutor(workflow_b, id="workflow_b")
    parent_request_info = RequestInfoExecutor()

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, executor_a)
        .add_edge(parent, executor_b)
        .add_edge(executor_a, parent)
        .add_edge(executor_b, parent)
        .add_edge(parent, parent_request_info)
        .add_edge(parent_request_info, executor_a)  # For SubWorkflowResponse routing
        .add_edge(parent_request_info, executor_b)  # For SubWorkflowResponse routing
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


if __name__ == "__main__":
    # Run tests
    asyncio.run(test_basic_sub_workflow())
    asyncio.run(test_sub_workflow_with_interception())
    asyncio.run(test_conditional_forwarding())
    asyncio.run(test_workflow_scoped_interception())
