# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework_workflow import (
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
)


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


class EmailValidator(Executor):
    """Validates email addresses in a sub-workflow."""
    
    def __init__(self):
        super().__init__(id="email_validator")
        self._pending_email = None
    
    @handler(output_types=[RequestInfoMessage, ValidationResult])
    async def validate(self, request: EmailValidationRequest, ctx: WorkflowContext) -> None:
        """Validate an email address."""
        print(f"DEBUG: EmailValidator received: {request.email}")
        self._pending_email = request.email
        
        # Extract domain and check if it's approved
        domain = request.email.split("@")[1] if "@" in request.email else ""
        
        if not domain:
            result = ValidationResult(
                email=request.email,
                is_valid=False,
                reason="Invalid email format"
            )
            await ctx.send_message(result)
            return
        
        # Request domain check from external source
        print(f"DEBUG: EmailValidator requesting domain check for: {domain}")
        domain_check = DomainCheckRequest(domain=domain)
        print(f"DEBUG: Sending domain check to sub_request_info")
        await ctx.send_message(domain_check, target_id="sub_request_info")
    
    @handler(output_types=[ValidationResult])
    async def handle_domain_response(self, approved: bool, ctx: WorkflowContext) -> None:
        """Handle domain check response."""
        print(f"DEBUG: EmailValidator received domain response: {approved}")
        if self._pending_email:
            result = ValidationResult(
                email=self._pending_email,
                is_valid=approved,
                reason="Domain approved" if approved else "Domain not approved"
            )
            # Send the result and complete the workflow
            await ctx.send_message(result)
            
            from agent_framework_workflow import WorkflowCompletedEvent
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            self._pending_email = None


class SimpleParent(Executor):
    def __init__(self):
        super().__init__(id="simple_parent")
        self.result = None

    @handler
    async def start(self, email: str, ctx: WorkflowContext) -> None:
        print(f"DEBUG: SimpleParent starting with: {email}")
        request = EmailValidationRequest(email=email)
        await ctx.send_message(request, target_id="email_workflow")

    @handler
    async def collect(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        print(f"DEBUG: SimpleParent collected result: {result}")
        self.result = result


async def test_basic_sub_workflow_debug():
    """Test basic sub-workflow execution with debug output."""
    # Create sub-workflow
    email_validator = EmailValidator()
    sub_request_info = RequestInfoExecutor(id="sub_request_info")
    
    validation_workflow = (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, sub_request_info)
        .add_edge(sub_request_info, email_validator)
        .build()
    )
    
    # Create parent workflow
    parent = SimpleParent()
    workflow_executor = WorkflowExecutor(validation_workflow, id="email_workflow")
    main_request_info = RequestInfoExecutor(id="main_request_info")
    
    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, workflow_executor)
        .add_edge(workflow_executor, parent)
        .add_edge(parent, main_request_info)  # For forwarded external requests
        .add_edge(main_request_info, parent)
        .add_edge(main_request_info, workflow_executor)  # For SubWorkflowResponse delivery
        .build()
    )
    
    print("DEBUG: Starting workflow execution...")
    
    # Run workflow
    result = await main_workflow.run("test@example.com")
    
    print("DEBUG: Workflow completed. Getting request events...")
    
    # Get request events
    request_events = result.get_request_info_events()
    print(f"DEBUG: Found {len(request_events)} request events")
    for i, event in enumerate(request_events):
        print(f"DEBUG: Event {i}: {event}")
    
    # Check if we have the expected request
    print(f"Expected at least 1 request event, got {len(request_events)}")
    
    if request_events:
        # Test sending a response and continuing workflow
        print("DEBUG: Sending response to the request...")
        result_events = [event async for event in main_workflow.send_responses_streaming({
            request_events[0].request_id: True  # Domain is approved
        })]
        print(f"DEBUG: Got {len(result_events)} events from send_responses_streaming")
        for i, event in enumerate(result_events):
            print(f"DEBUG: Event {i}: {type(event).__name__} - {event}")
        print(f"DEBUG: Parent result after response: {parent.result}")


if __name__ == "__main__":
    asyncio.run(test_basic_sub_workflow_debug())