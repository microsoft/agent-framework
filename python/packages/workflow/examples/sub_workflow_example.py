#!/usr/bin/env python3
"""
Example demonstrating sub-workflow feature with request interception.

This example shows:
1. A parent workflow that can intercept requests from sub-workflows
2. Sub-workflows that work normally without knowing they're nested
3. Request forwarding when parent can't handle requests
"""

import asyncio
from dataclasses import dataclass

from agent_framework_workflow import (
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    Workflow,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowExecutor,
    handler,
    intercepts_request,
)


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
            result = ValidationResult(
                email=request.email,
                is_valid=False,
                reason="Invalid email format"
            )
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            return
        
        # Request domain check
        print(f"Checking domain: {domain}")
        domain_check = DomainCheckRequest(domain=domain)
        await ctx.send_message(domain_check, target_id="email_request_info")
    
    @handler(output_types=[ValidationResult])
    async def handle_domain_response(self, approved: bool, ctx: WorkflowContext) -> None:
        """Handle domain check response."""
        print(f"Domain check result: {approved}")
        if self._pending_email:
            result = ValidationResult(
                email=self._pending_email,
                is_valid=approved,
                reason="Domain approved" if approved else "Domain not approved"
            )
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            self._pending_email = None


# Parent workflow with request interception
class SmartEmailOrchestrator(Executor):
    """Parent orchestrator that can intercept domain checks."""
    
    def __init__(self, approved_domains: set[str] | None = None):
        super().__init__(id="email_orchestrator")
        self.approved_domains = approved_domains or {"example.com", "test.org", "company.com"}
        self.results = []
        print(f"Orchestrator knows about domains: {self.approved_domains}")
    
    @handler(output_types=[EmailValidationRequest])
    async def start_validation(self, emails: list[str], ctx: WorkflowContext) -> None:
        """Start validating a batch of emails."""
        print(f"Starting validation of {len(emails)} emails")
        for email in emails:
            request = EmailValidationRequest(email=email)
            await ctx.send_message(request, target_id="email_validator_workflow")
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(
        self,
        request: DomainCheckRequest,
        ctx: WorkflowContext
    ) -> RequestResponse:
        """Intercept domain check requests from sub-workflows."""
        print(f"Intercepted domain check for: {request.domain}")
        
        if request.domain in self.approved_domains:
            print(f"Domain {request.domain} is pre-approved!")
            return RequestResponse.handled(True)
        else:
            print(f"Domain {request.domain} unknown, forwarding to external check")
            return RequestResponse.forward()
    
    @handler(output_types=[])
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        """Collect validation results."""
        print(f"Collected result: {result.email} -> {result.is_valid} ({result.reason})")
        self.results.append(result)


async def run_example():
    """Run the sub-workflow example."""
    print("Setting up sub-workflow...")
    
    # Create the email validation sub-workflow
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
    
    # Create the parent workflow with interception
    orchestrator = SmartEmailOrchestrator(approved_domains={"example.com", "company.com"})
    workflow_executor = WorkflowExecutor(validation_workflow, id="email_validator_workflow")
    parent_request_info = RequestInfoExecutor()
    
    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(orchestrator)
        .add_edge(orchestrator, workflow_executor)
        .add_edge(workflow_executor, orchestrator)
        # Note: Forwarded requests will be automatically handled by the workflow framework
        # The parent RequestInfoExecutor is not needed in this simplified example
        .build()
    )
    
    # Test emails: known domain, unknown domain
    test_emails = [
        "user@example.com",      # Should be intercepted and approved
        "admin@company.com",     # Should be intercepted and approved  
        "guest@unknown.org"      # Should be forwarded externally
    ]
    
    print(f"\nTesting with emails: {test_emails}")
    print("=" * 60)
    
    # Run the workflow
    result = await main_workflow.run(test_emails)
    
    # Handle any external requests
    request_events = result.get_request_info_events()
    if request_events:
        print(f"\nGot {len(request_events)} external request(s)")
        for event in request_events:
            print(f"   Request: {event.data}")
        
        # Simulate external responses
        external_responses = {}
        for event in request_events:
            # Simulate external domain checking
            domain = event.data.domain
            # Let's say unknown.org is actually approved externally
            approved = domain == "unknown.org"  
            external_responses[event.request_id] = approved
            print(f"   External check for {domain}: {approved}")
        
        # Send external responses
        await main_workflow.send_responses(external_responses)
    
    print("\nFinal Results:")
    print("=" * 60)
    for result in orchestrator.results:
        status = "PASS" if result.is_valid else "FAIL"
        print(f"{status} {result.email}: {result.reason}")
    
    print(f"\nValidated {len(orchestrator.results)} emails total")


if __name__ == "__main__":
    asyncio.run(run_example())