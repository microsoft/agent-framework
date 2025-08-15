# Strategy B: Complete End-to-End Example

This document shows a complete, simplified example of Strategy B (Parent Interceptor) with all the necessary code.

## Scenario

A data validation sub-workflow needs to check if an email domain is on an approved list. The parent workflow maintains this approved list and can answer the question without going to an external source.

## Step 1: Define Request Types

```python
# request_types.py
from dataclasses import dataclass

@dataclass
class DomainCheckRequest:
    """Request to check if a domain is approved."""
    domain: str
    check_type: str = "email"  # email, api, webhook
```

## Step 2: Define the Sub-Workflow

```python
# sub_workflow.py
from agent_framework_workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    RequestInfoMessage,
    RequestInfoExecutor
)

# Note: The flow in the sub-workflow is:
# 1. EmailValidator sends RequestInfoMessage to RequestInfoExecutor
# 2. RequestInfoExecutor emits RequestInfoEvent (caught by parent)
# 3. Parent (or external) provides response via workflow.send_responses()
# 4. RequestInfoExecutor sends the response data back to EmailValidator
#    (The edge RequestInfoExecutor -> EmailValidator enables this)

class EmailValidator(Executor):
    """Validates email addresses in the sub-workflow."""
    
    def __init__(self):
        super().__init__(id="email_validator")
        self._pending_email = None
    
    @handler(output_types=[RequestInfoMessage, ValidationResult])
    async def validate(self, email: str, ctx: WorkflowContext) -> None:
        """Validate an email address."""
        
        # Basic format check
        if "@" not in email:
            await ctx.send_message(ValidationResult(
                email=email,
                is_valid=False,
                reason="Invalid format"
            ))
            return
        
        # Store email for when we get response
        self._pending_email = email
        
        # Extract domain
        domain = email.split("@")[1]
        
        # Need to check if domain is approved - ask external
        await ctx.send_message(
            RequestInfoMessage(
                data=DomainCheckRequest(domain=domain, check_type="email")
            )
        )
    
    @handler(output_types=[ValidationResult])
    async def handle_domain_response(self, response: bool, ctx: WorkflowContext) -> None:
        """Handle the domain check response from RequestInfoExecutor.
        
        When workflow.send_responses() is called (either by parent interceptor
        or external system), the RequestInfoExecutor routes the response back
        to this handler based on the edge in the workflow graph.
        
        The response type (bool) comes from what the parent's @intercepts_request
        method returns.
        """
        
        email = self._pending_email
        
        if response:
            result = ValidationResult(email=email, is_valid=True, reason="Valid")
        else:
            result = ValidationResult(email=email, is_valid=False, reason="Domain not approved")
        
        await ctx.send_message(result)

@dataclass
class ValidationResult:
    """Result of email validation."""
    email: str
    is_valid: bool
    reason: str

# Build the sub-workflow
# Create instances first - IMPORTANT!
email_validator = EmailValidator()
request_info_executor = RequestInfoExecutor()

validation_workflow = (
    WorkflowBuilder()
    .set_start_executor(email_validator)
    .add_edge(email_validator, request_info_executor)
    .add_edge(request_info_executor, email_validator)
    .build()
)
```

## Step 3: Define the Parent Workflow Components

```python
# parent_workflow_components.py
from agent_framework_workflow import Executor, WorkflowContext, handler
from typing import Any, Callable, Protocol

def intercepts_request(
    request_type: str | type, 
    from_workflow: str | None = None,
    condition: Callable[[Any], bool] | None = None
):
    """Decorator to mark methods as request handlers.
    
    Args:
        request_type: The type of request to handle (string or class)
        from_workflow: Optional sub-workflow ID to scope this handler to
        condition: Optional additional condition function
    """
    def decorator(func):
        func._intercepts_request = request_type
        func._from_workflow = from_workflow
        func._handle_condition = condition
        return func
    return decorator

class RequestWrapper(Protocol):
    """Protocol for request wrapper objects."""
    data: Any
    request_id: str
    
class InterceptingExecutor(Executor):
    """Base class for executors that can intercept sub-workflow requests.
    
    This base class automatically handles routing of SubWorkflowRequestInfo
    to methods decorated with @intercepts_request, eliminating boilerplate.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._request_handlers = self._discover_handlers()
    
    def _discover_handlers(self):
        """Discover methods decorated with @intercepts_request."""
        handlers = {}
        for name in dir(self):
            attr = getattr(self, name)
            if hasattr(attr, '_intercepts_request'):
                handler_info = {
                    'method': attr,
                    'from_workflow': getattr(attr, '_from_workflow', None),
                    'condition': getattr(attr, '_handle_condition', None)
                }
                handlers[attr._intercepts_request] = handler_info
        return handlers
    
    @handler  # Framework provides this automatically!
    async def _handle_sub_workflow_request(
        self,
        request: SubWorkflowRequestInfo,
        ctx: WorkflowContext
    ) -> None:
        """Automatic routing to @intercepts_request methods.
        
        This is provided by the framework so developers don't need
        to write boilerplate routing code.
        """
        # Try to match against registered handlers
        for request_type, handler_info in self._request_handlers.items():
            if isinstance(request_type, type) and isinstance(request.data, request_type):
                # Check workflow scope if specified
                from_workflow = handler_info['from_workflow']
                if from_workflow and request.sub_workflow_id != from_workflow:
                    continue  # Skip this handler, wrong workflow
                
                # Check additional condition
                condition = handler_info['condition']
                if condition and not condition(request):
                    continue
                
                # Call the handler
                result = await handler_info['method'](request.data, ctx)
                
                # Send response back to sub-workflow
                await ctx.send_message(
                    SubWorkflowResponse(
                        request_id=request.request_id,
                        data=result
                    ),
                    target_id=request.sub_workflow_id
                )
                return
        
        # No handler found - forward to external RequestInfoExecutor
        await ctx.send_message(request.data)
```

## Step 4: Define the Parent Workflow

```python
# parent_workflow.py
from dataclasses import dataclass

@dataclass  
class SubWorkflowRequestInfo:
    """Wrapper for requests from sub-workflows."""
    request_id: str
    sub_workflow_id: str
    data: Any
    
@dataclass
class SubWorkflowResponse:
    """Response to send back to sub-workflow."""
    request_id: str
    data: Any

class EmailProcessingOrchestrator(InterceptingExecutor):
    """Main orchestrator that manages email processing.
    
    Note: No boilerplate routing method needed! The InterceptingExecutor
    base class automatically handles routing SubWorkflowRequestInfo to
    our @intercepts_request methods.
    """
    
    def __init__(self):
        super().__init__(id="orchestrator")
        # Parent maintains the approved domains list
        self.approved_domains = {
            "company.com",
            "trusted-partner.org", 
            "verified-client.net"
        }
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(
        self,
        request: DomainCheckRequest,
        ctx: WorkflowContext
    ) -> bool:
        """Check if a domain is on the approved list.
        
        The framework automatically:
        1. Routes SubWorkflowRequestInfo here when data is DomainCheckRequest
        2. Sends the response back to the sub-workflow
        3. Forwards to RequestInfoExecutor if no handler matches
        """
        print(f"Parent checking domain: {request.domain}")
        
        # Parent has the approved list, no need for external call
        is_approved = request.domain in self.approved_domains
        
        # Could also check other criteria
        if request.check_type == "email" and request.domain.endswith(".edu"):
            is_approved = True  # Auto-approve educational domains
        
        return is_approved
    
    @handler
    async def start_processing(self, emails: list[str], ctx: WorkflowContext) -> None:
        """Start processing a batch of emails."""
        print(f"Starting to process {len(emails)} emails")
        
        # Send raw email strings directly to sub-workflow - no wrapper needed!
        for email in emails:
            await ctx.send_message(
                email,  # Just the raw string
                target_id="email_validator_workflow"
            )
    
    @handler
    async def handle_validation_result(
        self,
        result: ValidationResult,
        ctx: WorkflowContext
    ) -> None:
        """Handle validation results from sub-workflow."""
        print(f"Validation result: {result.email} - {result.reason}")
        
        # Store results
        results = await ctx.get_state().get("results", [])
        results.append(result)
        await ctx.get_state().set("results", results)
```

## Step 5: Define the WorkflowExecutor

```python
# workflow_executor.py
from dataclasses import dataclass
from enum import Enum
import uuid

class MessagePolicy(Enum):
    PASSTHROUGH = "passthrough"
    INTERCEPT = "intercept"
    ISOLATE = "isolate"

@dataclass
class SubWorkflowConfig:
    """Configuration for sub-workflow execution."""
    message_policy: MessagePolicy = MessagePolicy.INTERCEPT

class WorkflowExecutor(Executor):
    """Executor that runs a workflow as its execution logic."""
    
    def __init__(
        self,
        workflow: 'Workflow',
        id: str | None = None,
        config: SubWorkflowConfig | None = None
    ):
        super().__init__(id or f"workflow_executor_{uuid.uuid4()}")
        self._workflow = workflow
        self._config = config or SubWorkflowConfig()
        self._pending_requests = {}
    
    @handler
    async def execute(self, message: Any, ctx: WorkflowContext) -> None:
        """Execute the sub-workflow with the given message."""
        
        # Store current email in sub-workflow state for later use
        sub_state = SharedState()  # Would be created based on state policy
        await sub_state.set("current_email", message)
        
        # Run sub-workflow
        async for event in self._workflow.run_streaming(message):
            
            if isinstance(event, WorkflowCompletedEvent):
                # Sub-workflow completed, send result to parent
                await ctx.send_message(event.data)
                
            elif isinstance(event, RequestInfoEvent):
                # Sub-workflow needs information
                if self._config.message_policy == MessagePolicy.INTERCEPT:
                    # Wrap request and send to parent for potential interception
                    wrapped_request = SubWorkflowRequestInfo(
                        request_id=event.request_id,
                        sub_workflow_id=self.id,
                        data=event.data
                    )
                    
                    # Store mapping for response routing
                    self._pending_requests[event.request_id] = event.request_id
                    
                    # Send to parent
                    await ctx.send_message(wrapped_request)
    
    @handler
    async def handle_response(
        self,
        response: SubWorkflowResponse,
        ctx: WorkflowContext
    ) -> None:
        """Handle response from parent for forwarded request."""
        
        if response.request_id in self._pending_requests:
            # Forward response to sub-workflow's RequestInfoExecutor
            # The RequestInfoExecutor will route it to the correct handler
            # based on the workflow edges (RequestInfoExecutor -> EmailValidator)
            await self._workflow.send_responses({
                response.request_id: response.data  # response.data is the bool value
            })
            
            # Continue running the sub-workflow to process the response
            async for event in self._workflow.run_streaming(None):
                if isinstance(event, WorkflowCompletedEvent):
                    # Sub-workflow completed after processing response
                    await ctx.send_message(event.data)
                    break
            
            # Clean up
            del self._pending_requests[response.request_id]
```

## Step 6: Wire Everything Together

```python
# main.py
from agent_framework_workflow import WorkflowBuilder, RequestInfoExecutor
import asyncio

# Create the main workflow with parent interception
# Create instances first - IMPORTANT!
orchestrator = EmailProcessingOrchestrator()
email_validator_workflow = WorkflowExecutor(
    validation_workflow,
    id="email_validator_workflow",
    config=SubWorkflowConfig(message_policy=MessagePolicy.INTERCEPT)
)
external_request_info = RequestInfoExecutor()

main_workflow = (
    WorkflowBuilder()
    .set_start_executor(orchestrator)
    
    # Connect orchestrator to sub-workflow executor
    .add_edge(orchestrator, email_validator_workflow)
    
    # Sub-workflow can send requests back to orchestrator
    .add_edge(email_validator_workflow, orchestrator)
    
    # Orchestrator can forward unhandled requests to external handler
    .add_edge(orchestrator, external_request_info)
    .add_edge(external_request_info, orchestrator)
    
    .build()
)

async def main():
    """Run the complete workflow."""
    
    # Test emails with different domains
    test_emails = [
        "user@company.com",          # Approved domain
        "student@university.edu",     # Auto-approved .edu
        "contact@unknown-site.com",   # Not approved
        "admin@trusted-partner.org"   # Approved domain
    ]
    
    # Run the workflow
    result = await main_workflow.run(test_emails)
    
    # Get final results from state
    final_results = result.state.get("results", [])
    
    print("\nFinal Results:")
    for r in final_results:
        status = "✓" if r.is_valid else "✗"
        print(f"{status} {r.email}: {r.reason}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Example with Multiple Sub-Workflows and Scoping

If you have multiple sub-workflows that might use the same request types, you can scope handlers:

```python
class OrchestratorWithMultipleSubWorkflows(InterceptingExecutor):
    """Orchestrator managing multiple validation sub-workflows."""
    
    @intercepts_request(DomainCheckRequest, from_workflow="email_validator_workflow")
    async def check_email_domain(
        self,
        request: DomainCheckRequest,
        ctx: WorkflowContext
    ) -> bool:
        """Handle domain checks specifically from email validator."""
        # Strict email domain rules
        return request.domain in self.approved_email_domains
    
    @intercepts_request(DomainCheckRequest, from_workflow="api_validator_workflow")
    async def check_api_domain(
        self,
        request: DomainCheckRequest,
        ctx: WorkflowContext
    ) -> bool:
        """Handle domain checks specifically from API validator."""
        # Different rules for API domains
        return request.domain in self.approved_api_domains or request.domain.endswith(".api.internal")
    
    @intercepts_request(DomainCheckRequest)  # No scope - catches all others
    async def check_domain_fallback(
        self,
        request: DomainCheckRequest,
        ctx: WorkflowContext
    ) -> bool:
        """Default handler for any other domain check requests."""
        # Generic domain check
        return not request.domain.endswith(".blocked")
```

You can also use conditions for more complex logic:

```python
    @intercepts_request(
        DomainCheckRequest,
        condition=lambda req: req.data.check_type == "strict"
    )
    async def strict_domain_check(
        self,
        request: DomainCheckRequest,
        ctx: WorkflowContext
    ) -> bool:
        """Handle strict domain checks from any workflow."""
        return request.domain in self.strictly_approved_domains
```

## Expected Output

```
Starting to process 4 emails
Received request from sub-workflow: DomainCheckRequest(domain='company.com', check_type='email')
Parent checking domain: company.com
Parent handled request internally, responding with: True
Validation result: user@company.com - Valid

Received request from sub-workflow: DomainCheckRequest(domain='university.edu', check_type='email')
Parent checking domain: university.edu
Parent handled request internally, responding with: True
Validation result: student@university.edu - Valid

Received request from sub-workflow: DomainCheckRequest(domain='unknown-site.com', check_type='email')
Parent checking domain: unknown-site.com
Parent handled request internally, responding with: False
Validation result: contact@unknown-site.com - Domain not approved

Received request from sub-workflow: DomainCheckRequest(domain='trusted-partner.org', check_type='email')
Parent checking domain: trusted-partner.org
Parent handled request internally, responding with: True
Validation result: admin@trusted-partner.org - Valid

Final Results:
✓ user@company.com: Valid
✓ student@university.edu: Valid
✗ contact@unknown-site.com: Domain not approved
✓ admin@trusted-partner.org: Valid
```

## Key Points

1. **Sub-workflow asks for information**: The `EmailValidator` sends a `RequestInfoMessage` with a `DomainCheckRequest` when it needs to know if a domain is approved.

2. **WorkflowExecutor wraps the request**: It creates a `SubWorkflowRequestInfo` wrapper and sends it to the parent.

3. **Parent intercepts and handles**: The `EmailProcessingOrchestrator` has a `@intercepts_request(DomainCheckRequest)` method that checks the domain against its internal list.

4. **Response flows back**: The parent sends a `SubWorkflowResponse` back through the `WorkflowExecutor` to the sub-workflow.

5. **No external call needed**: Because the parent can answer the question, the request never reaches the `RequestInfoExecutor`.

This demonstrates a clean, type-safe way for parent workflows to provide information to sub-workflows without external dependencies.