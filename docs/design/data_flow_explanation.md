# Complete Data Flow Explanation for Sub-Workflows

## Overview

The sub-workflow pattern requires only a minimal set of message types to enable parent workflows to execute and optionally intercept requests from sub-workflows. This document explains the complete data flow with the minimum concepts needed.

## The Key Players

1. **Parent Workflow** - Contains the orchestrator and WorkflowExecutor
2. **WorkflowExecutor** - Wraps the sub-workflow and acts as a bridge
3. **Sub-Workflow** - Independent workflow that doesn't know it's nested
4. **RequestInfoExecutor** - Handles external information requests

## Minimal Message Types Required

### 1. RequestInfoMessage (Already exists in framework)
**Purpose**: Standard way for any workflow to request external information  
**Used by**: Sub-workflow when it needs data it doesn't have

```python
# Sub-workflow sends this when it needs external info
await ctx.send_message(
    RequestInfoMessage(
        data=DomainCheckRequest(domain="example.com")
    )
)
```

### 2. SubWorkflowRequestInfo  
**Purpose**: Wrapper that adds routing context to requests from sub-workflows  
**Why needed**: Parent needs to know which sub-workflow to send responses back to

```python
@dataclass
class SubWorkflowRequestInfo:
    request_id: str           # Original request ID from sub-workflow
    sub_workflow_id: str      # Which WorkflowExecutor this came from
    data: Any                 # The actual request data
```

### 3. SubWorkflowResponse
**Purpose**: Routes responses back to the correct sub-workflow  
**Why needed**: Multiple sub-workflows might be running in parallel

```python
@dataclass
class SubWorkflowResponse:
    request_id: str    # Matches the original request
    data: Any          # The actual response data
```

That's it! Just 3 types total (and one already exists in the framework).

## Minimal Type System

Only **2 new types** are required:

1. **SubWorkflowRequestInfo**: Adds routing context when requests bubble up from sub-workflows
2. **SubWorkflowResponse**: Routes responses back to the correct sub-workflow

Everything else uses existing types:
- Parent sends raw data directly to WorkflowExecutor
- WorkflowExecutor sends raw results back to parent  
- Sub-workflows use standard RequestInfoMessage
- Regular data flow (input and output) uses raw types - wrappers only needed for request/response patterns

## Developer Code Example

Here's what developers need to write with the simplified pattern:

```python
# 1. Sub-workflow - completely standard, no special types needed
class EmailValidator(Executor):
    @handler(output_types=[RequestInfoMessage, ValidationResult])
    async def validate(self, email: str, ctx: WorkflowContext) -> None:
        domain = email.split("@")[1]
        
        # Standard request for external info
        await ctx.send_message(
            RequestInfoMessage(
                data=DomainCheckRequest(domain=domain)
            )
        )
    
    @handler(output_types=[ValidationResult])
    async def handle_response(self, approved: bool, ctx: WorkflowContext) -> None:
        # Standard response handling
        result = ValidationResult(is_valid=approved)
        await ctx.send_message(result)

# 2. Parent - simple and clean!
class ParentOrchestrator(Executor):
    """Parent orchestrator with automatic request routing.
    
    The base Executor class automatically routes SubWorkflowRequestInfo 
    to @handles_request methods when they exist.
    """
    
    def __init__(self):
        super().__init__(id="orchestrator")
        self.approved_domains = {"company.com", "trusted.org"}
    
    @handler
    async def start(self, emails: list[str], ctx: WorkflowContext) -> None:
        """Send raw data to sub-workflow."""
        for email in emails:
            # Just send the raw string, no wrapper needed!
            await ctx.send_message(email, target_id="email_validator_workflow")
    
    @handles_request(DomainCheckRequest, from_workflow="email_validator_workflow")
    async def check_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> RequestResponse:
        """Handle domain check requests from email validator.
        
        Framework automatically:
        - Routes SubWorkflowRequestInfo here when data matches type
        - Sends response back via SubWorkflowResponse if handled
        - Forwards to RequestInfoExecutor if not handled
        """
        if request.domain in self.approved_domains:
            # We know this domain - return the answer
            return RequestResponse.handled(True)
        
        # We don't know - forward to external for verification
        return RequestResponse.forward()
    
    @handler
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        """Receive raw results from sub-workflow."""
        print(f"Got result: {result}")
    
    # NO boilerplate routing method needed!

# 3. Workflow setup
# Create executor instances first - IMPORTANT!
email_validator = EmailValidator()
request_info_executor = RequestInfoExecutor()

validation_workflow = (
    WorkflowBuilder()
    .set_start_executor(email_validator)
    .add_edge(email_validator, request_info_executor)
    .add_edge(request_info_executor, email_validator)
    .build()
)

# Parent workflow executors
parent_orchestrator = ParentOrchestrator()
workflow_executor = WorkflowExecutor(validation_workflow, id="email_validator_workflow")
parent_request_info = RequestInfoExecutor()

main_workflow = (
    WorkflowBuilder()
    .set_start_executor(parent_orchestrator)
    .add_edge(parent_orchestrator, workflow_executor)
    .add_edge(workflow_executor, parent_orchestrator)
    .add_edge(parent_orchestrator, parent_request_info)
    .build()
)
```

## Handling Multiple Sub-Workflows

When you have multiple sub-workflows that might use the same request types, you can scope handlers to specific workflows:

```python
class ParentWithMultipleValidators(Executor):
    
    @handles_request(DomainCheckRequest, from_workflow="email_validator")
    async def check_email_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> bool:
        """Strict rules for email domains."""
        return request.domain in self.email_domains
    
    @handles_request(DomainCheckRequest, from_workflow="api_validator")
    async def check_api_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> bool:
        """Different rules for API domains."""
        return request.domain.endswith(".api.com") or request.domain in self.api_domains
    
    @handles_request(DomainCheckRequest)  # No scope - catches all others
    async def check_domain_default(self, request: DomainCheckRequest, ctx: WorkflowContext) -> bool:
        """Fallback for any other validators."""
        return not request.domain.endswith(".blocked")
```

The `from_workflow` parameter matches against the `sub_workflow_id` in the `SubWorkflowRequestInfo`, ensuring the right handler is called for each sub-workflow.

## Complete Data Flow - Step by Step

Let's trace an email validation through the entire system:

```
STEP 1: Parent starts the process
----------------------------------------
Parent Orchestrator
    |
    | sends raw data: "user@example.com"
    | (no special wrapper type needed!)
    v
WorkflowExecutor (id="email_validator_workflow")
    |
    | starts sub-workflow with: "user@example.com"
    v
Sub-Workflow EmailValidator


STEP 2: Sub-workflow needs domain check
----------------------------------------
EmailValidator (in sub-workflow)
    |
    | sends: RequestInfoMessage(data=DomainCheckRequest(domain="example.com"))
    v
RequestInfoExecutor (in sub-workflow)
    |
    | emits: RequestInfoEvent(request_id="123", data=DomainCheckRequest)
    v
(Event is caught by WorkflowExecutor watching the sub-workflow)


STEP 3: WorkflowExecutor adds routing context
----------------------------------------
WorkflowExecutor
    |
    | wraps with: SubWorkflowRequestInfo(
    |                request_id="123",
    |                sub_workflow_id="email_validator_workflow",
    |                data=DomainCheckRequest(domain="example.com")
    |             )
    v
Parent Orchestrator


STEP 4: Parent intercepts and handles
----------------------------------------
Parent Orchestrator
    |
    | @handles_request(DomainCheckRequest) method runs
    | returns: RequestResponse.handled(True)
    |
    | Framework sends: SubWorkflowResponse(
    |                    request_id="123",
    |                    data=True
    |                  )
    v
WorkflowExecutor (using sub_workflow_id for routing)


STEP 5: WorkflowExecutor forwards to sub-workflow
----------------------------------------
WorkflowExecutor
    |
    | receives: SubWorkflowResponse(request_id="123", data=True)
    |
    | calls: sub_workflow.send_responses({"123": True})
    v
RequestInfoExecutor (in sub-workflow)
    |
    | sends: True
    v
EmailValidator (receives bool response)


STEP 6: Sub-workflow completes
----------------------------------------
EmailValidator
    |
    | sends: ValidationResult
    | (workflow completes)
    v
WorkflowExecutor
    |
    | sends: ValidationResult (raw, no wrapper needed)
    v
Parent Orchestrator
```

## Summary

The minimal design needs only **2 new types**:

1. **SubWorkflowRequestInfo** - Adds routing context to requests going up (includes `sub_workflow_id` for scoping)
2. **SubWorkflowResponse** - Routes responses going back down

Everything else uses standard types:
- Parent sends raw data to WorkflowExecutor
- WorkflowExecutor sends raw results back to parent
- Sub-workflow uses standard RequestInfoMessage

This keeps the design simple while enabling:
- **Sub-workflow reusability** (doesn't know it's nested)
- **Parent interception** (can handle requests internally via `@handles_request`)
- **Automatic routing** (base `Executor` handles `SubWorkflowRequestInfo` → handler → `SubWorkflowResponse`)
- **No boilerplate** (parents only define domain logic, not routing logic)
- **Zero overhead** (features only activate when `@handles_request` is used)
- **One base class** (no need for special `InterceptingExecutor`)
- **Proper routing** (responses go to the right sub-workflow)
- **Clean separation of concerns**
- **Scoped handling** for multiple sub-workflows using the same request types

---

## Framework Implementation Details

The following sections show the framework-level code that makes the simple developer experience possible. **Developers don't need to write this code** - it's provided by the framework.

### WorkflowExecutor (Framework-Provided)

```python
class WorkflowExecutor(Executor):
    """Framework-provided executor that wraps sub-workflows."""
    
    def __init__(self, workflow, id=None, config=None):
        super().__init__(id)
        self.workflow = workflow
        self.config = config or SubWorkflowConfig()
        self.pending_requests = {}
    
    @handler
    async def execute(self, input_data: Any, ctx: WorkflowContext) -> None:
        """Execute sub-workflow with any input type."""
        async for event in self.workflow.run_streaming(input_data):
            
            if isinstance(event, RequestInfoEvent):
                # Only wrap requests that need routing
                wrapped = SubWorkflowRequestInfo(
                    request_id=event.request_id,
                    sub_workflow_id=self.id,
                    data=event.data
                )
                self.pending_requests[event.request_id] = True
                await ctx.send_message(wrapped)
            
            elif isinstance(event, WorkflowCompletedEvent):
                # Send raw result, no wrapper needed
                await ctx.send_message(event.data)
    
    @handler
    async def handle_response(self, response: SubWorkflowResponse, ctx: WorkflowContext) -> None:
        """Route response back to sub-workflow."""
        if response.request_id in self.pending_requests:
            await self.workflow.send_responses({
                response.request_id: response.data
            })
            # Continue running after response
            async for event in self.workflow.run_streaming(None):
                if isinstance(event, WorkflowCompletedEvent):
                    await ctx.send_message(event.data)
                    break
            del self.pending_requests[response.request_id]
```

### Enhanced Base Executor (Framework-Provided)

```python
def handles_request(
    request_type: str | type,
    from_workflow: str | None = None,
    condition: Callable[[Any], bool] | None = None
):
    """Framework-provided decorator for request handlers."""
    def decorator(func):
        func._handles_request = request_type
        func._from_workflow = from_workflow
        func._handle_condition = condition
        return func
    return decorator

class Executor:
    """Enhanced base executor with built-in request interception support."""
    
    def __init__(self, id: str | None = None):
        self.id = id or str(uuid.uuid4())
        self._handlers = {}
        self._request_handlers = {}  # For @handles_request methods
        self._discover_handlers()
    
    def _discover_handlers(self):
        """Discover both @handler and @handles_request methods."""
        for name in dir(self):
            attr = getattr(self, name)
            
            # Regular handlers
            if hasattr(attr, '_handler_info'):
                self._handlers[attr._handler_info['input_type']] = attr
            
            # Request handlers (only add automatic routing if they exist)
            if hasattr(attr, '_handles_request'):
                handler_info = {
                    'method': attr,
                    'from_workflow': getattr(attr, '_from_workflow', None),
                    'condition': getattr(attr, '_handle_condition', None)
                }
                self._request_handlers[attr._handles_request] = handler_info
        
        # Only register SubWorkflowRequestInfo handler if @handles_request methods exist
        if self._request_handlers:
            self._register_sub_workflow_handler()
    
    def _register_sub_workflow_handler(self):
        """Register automatic handler for SubWorkflowRequestInfo messages."""
        # This would integrate with the existing handler registration system
        pass
    
    @handler  # Only active if @handles_request methods exist
    async def _handle_sub_workflow_request(
        self,
        request: SubWorkflowRequestInfo,
        ctx: WorkflowContext
    ) -> None:
        """Automatic routing to @handles_request methods.
        
        This is only active for executors that have @handles_request methods.
        Zero overhead for regular executors.
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
                response = await handler_info['method'](request.data, ctx)
                
                # Check if handler could handle it or needs to forward
                if isinstance(response, RequestResponse):
                    if response.handled:
                        # Send response back to sub-workflow
                        await ctx.send_message(
                            SubWorkflowResponse(
                                request_id=request.request_id,
                                data=response.data
                            ),
                            target_id=request.sub_workflow_id
                        )
                    else:
                        # Forward WITH CONTEXT PRESERVED
                        # Update the data if handler provided a modified request
                        if response.forward_request:
                            request.data = response.forward_request
                        
                        # Forward the entire SubWorkflowRequestInfo to preserve routing context
                        await ctx.send_message(request)  # Still has request_id and sub_workflow_id!
                else:
                    # Legacy support: direct return means handled
                    await ctx.send_message(
                        SubWorkflowResponse(
                            request_id=request.request_id,
                            data=response
                        ),
                        target_id=request.sub_workflow_id
                    )
                return
        
        # No handler found - forward entire request to RequestInfoExecutor
        # (preserves routing context)
        await ctx.send_message(request)
```

### Message Types (Framework-Provided)

```python
@dataclass
class SubWorkflowRequestInfo:
    """Framework-provided wrapper for sub-workflow requests."""
    request_id: str           # Original request ID from sub-workflow
    sub_workflow_id: str      # Which WorkflowExecutor this came from
    data: Any                 # The actual request data

@dataclass
class SubWorkflowResponse:
    """Framework-provided wrapper for responses to sub-workflows."""
    request_id: str    # Matches the original request
    data: Any          # The actual response data

@dataclass
class RequestResponse:
    """Response from a @handles_request method."""
    handled: bool
    data: Any = None
    forward_request: Any = None
    
    @staticmethod
    def handled(data: Any) -> 'RequestResponse':
        """Create a response indicating the request was handled."""
        return RequestResponse(handled=True, data=data)
    
    @staticmethod
    def forward(modified_request: Any = None) -> 'RequestResponse':
        """Create a response indicating the request should be forwarded."""
        return RequestResponse(handled=False, forward_request=modified_request)

@dataclass
class SubWorkflowConfig:
    """Framework-provided configuration for sub-workflow behavior."""
    message_policy: MessagePolicy = MessagePolicy.INTERCEPT
    # ... other configuration options
```

The enhanced base `Executor` class handles all the complexity automatically - developers just use `@handles_request` and the framework does the rest! No special base classes, no boilerplate, just clean business logic.