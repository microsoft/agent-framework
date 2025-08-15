# Sub-Workflow Implementation Guide

## Executive Summary

This document provides a complete implementation guide for the sub-workflow pattern in the Agent Framework. The design enables workflows to be executed as executors within other workflows, with automatic request interception and routing. The implementation requires only **2 new message types** and enhances the base `Executor` class with `@intercepts_request` support.

## Core Concept

The sub-workflow pattern allows hierarchical workflow composition:
- **Sub-workflows** run independently and don't know they're nested
- **WorkflowExecutor** wraps sub-workflows and acts as a bridge to parent workflows  
- **Parent workflows** can intercept sub-workflow requests and provide responses
- **Framework** automatically handles routing and context preservation

## Key Components

### 1. WorkflowExecutor (Framework-Provided)
Wraps a workflow to make it executable as an executor:

```python
class WorkflowExecutor(Executor):
    """An executor that runs another workflow as its execution logic."""
    
    def __init__(
        self,
        workflow: Workflow,
        id: str | None = None
    ):
        super().__init__(id)
        self._workflow = workflow
        self._pending_requests: dict[str, bool] = {}
```

### 2. Enhanced Base Executor 
The base `Executor` class automatically discovers `@intercepts_request` methods and provides routing:

```python
class Executor:
    def __init__(self, id: str | None = None):
        self.id = id or str(uuid.uuid4())
        self._request_handlers: dict = {}
        self._discover_request_handlers()
        
    def _discover_request_handlers(self):
        """Discover @intercepts_request methods and register SubWorkflowRequestInfo handler."""
        # Implementation details below
```

### 3. New Message Types
Only 3 new types are required:

```python
@dataclass
class SubWorkflowRequestInfo:
    """Routes requests from sub-workflows to parents."""
    request_id: str
    sub_workflow_id: str  
    data: Any

@dataclass
class SubWorkflowResponse:
    """Routes responses back to sub-workflows."""
    request_id: str
    data: Any

@dataclass 
class RequestResponse:
    """Response from @intercepts_request methods."""
    handled: bool
    data: Any = None
    forward_request: Any = None
    
    @staticmethod
    def handled(data: Any) -> 'RequestResponse':
        return RequestResponse(handled=True, data=data)
    
    @staticmethod
    def forward(modified_request: Any = None) -> 'RequestResponse':
        return RequestResponse(handled=False, forward_request=modified_request)
```

## Implementation Details

### 1. WorkflowExecutor Implementation

```python
class WorkflowExecutor(Executor):
    """Wraps a workflow to run as an executor."""
    
    def __init__(
        self,
        workflow: Workflow,
        id: str | None = None
    ):
        super().__init__(id)
        self._workflow = workflow
        self._pending_requests: dict[str, bool] = {}
    
    @handler
    async def execute(self, input_data: Any, ctx: WorkflowContext) -> None:
        """Execute sub-workflow with raw input data."""
        
        async for event in self._workflow.run_streaming(input_data):
            
            if isinstance(event, RequestInfoEvent):
                # Sub-workflow needs external information
                # Wrap with routing context and send to parent
                wrapped_request = SubWorkflowRequestInfo(
                    request_id=event.request_id,
                    sub_workflow_id=self.id,
                    data=event.data
                )
                self._pending_requests[event.request_id] = True
                await ctx.send_message(wrapped_request)
                
            elif isinstance(event, WorkflowCompletedEvent):
                # Sub-workflow completed - send raw result to parent
                await ctx.send_message(event.data)
                break
    
    @handler
    async def handle_response(
        self,
        response: SubWorkflowResponse,
        ctx: WorkflowContext
    ) -> None:
        """Handle response from parent for forwarded request."""
        
        if response.request_id in self._pending_requests:
            # Forward response to sub-workflow's RequestInfoExecutor
            await self._workflow.send_responses({
                response.request_id: response.data
            })
            
            # Continue running sub-workflow to process response
            async for event in self._workflow.run_streaming(None):
                if isinstance(event, WorkflowCompletedEvent):
                    await ctx.send_message(event.data)
                    break
            
            del self._pending_requests[response.request_id]
```

### 2. Enhanced Base Executor Implementation

```python
def intercepts_request(
    request_type: str | type,
    from_workflow: str | None = None,
    condition: Callable[[Any], bool] | None = None
):
    """Decorator to mark methods as request handlers."""
    def decorator(func):
        func._intercepts_request = request_type
        func._from_workflow = from_workflow
        func._handle_condition = condition
        return func
    return decorator

class Executor:
    """Enhanced base executor with automatic request routing."""
    
    def __init__(self, id: str | None = None):
        self.id = id or str(uuid.uuid4())
        self._handlers: dict = {}
        self._request_handlers: dict = {}
        self._discover_handlers()
    
    def _discover_handlers(self):
        """Discover both @handler and @intercepts_request methods."""
        for name in dir(self):
            attr = getattr(self, name)
            
            # Standard @handler methods
            if hasattr(attr, '_handler_info'):
                input_type = attr._handler_info['input_type']
                self._handlers[input_type] = attr
            
            # @intercepts_request methods
            if hasattr(attr, '_intercepts_request'):
                handler_info = {
                    'method': attr,
                    'from_workflow': getattr(attr, '_from_workflow', None),
                    'condition': getattr(attr, '_handle_condition', None)
                }
                self._request_handlers[attr._intercepts_request] = handler_info
        
        # Register SubWorkflowRequestInfo handler if @intercepts_request methods exist
        if self._request_handlers:
            self._register_sub_workflow_handler()
    
    def _register_sub_workflow_handler(self):
        """Register automatic handler for SubWorkflowRequestInfo."""
        # Add to handlers dict so framework routes SubWorkflowRequestInfo messages here
        self._handlers[SubWorkflowRequestInfo] = self._handle_sub_workflow_request
    
    async def _handle_sub_workflow_request(
        self,
        request: SubWorkflowRequestInfo,
        ctx: WorkflowContext
    ) -> None:
        """Automatic routing to @intercepts_request methods."""
        
        # Try to match request against registered handlers
        for request_type, handler_info in self._request_handlers.items():
            if isinstance(request_type, type) and isinstance(request.data, request_type):
                
                # Check workflow scope
                from_workflow = handler_info['from_workflow']
                if from_workflow and request.sub_workflow_id != from_workflow:
                    continue
                
                # Check condition
                condition = handler_info['condition']
                if condition and not condition(request):
                    continue
                
                # Call the handler
                response = await handler_info['method'](request.data, ctx)
                
                # Handle response
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
                        # Forward with context preserved
                        if response.forward_request:
                            request.data = response.forward_request
                        await ctx.send_message(request)  # Forward entire SubWorkflowRequestInfo
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
        
        # No handler matched - forward to RequestInfoExecutor
        await ctx.send_message(request)
```

### 3. RequestInfoExecutor Enhancement

The `RequestInfoExecutor` needs to handle both regular requests and forwarded sub-workflow requests:

```python
class RequestInfoExecutor(Executor):
    """Enhanced to handle sub-workflow forwarding."""
    
    @handler
    async def handle_request(self, message: RequestInfoMessage, ctx: WorkflowContext) -> None:
        """Handle regular request for external information."""
        event = RequestInfoEvent(
            request_id=message.request_id,
            data=message.data
        )
        await ctx.add_event(event)
    
    @handler
    async def handle_sub_workflow_request(
        self,
        request: SubWorkflowRequestInfo,
        ctx: WorkflowContext
    ) -> None:
        """Handle forwarded sub-workflow request."""
        # Extract data but preserve routing context
        event = RequestInfoEvent(
            request_id=request.request_id,
            data=request.data,
            metadata={'sub_workflow_id': request.sub_workflow_id}
        )
        await ctx.add_event(event)
    
    async def handle_response(
        self,
        response_data: Any,
        request_id: str,
        ctx: WorkflowContext
    ) -> None:
        """Route response back to originator."""
        # Check if this was a sub-workflow request
        if hasattr(self, '_sub_workflow_contexts') and request_id in self._sub_workflow_contexts:
            context = self._sub_workflow_contexts[request_id]
            await ctx.send_message(
                SubWorkflowResponse(
                    request_id=request_id,
                    data=response_data
                ),
                target_id=context['sub_workflow_id']
            )
        else:
            # Regular response
            await ctx.send_message(response_data)
```

## Usage Examples

### Basic Sub-Workflow Usage

```python
# 1. Define sub-workflow
email_validator = EmailValidator()
request_info = RequestInfoExecutor()

validation_workflow = (
    WorkflowBuilder()
    .set_start_executor(email_validator)
    .add_edge(email_validator, request_info)
    .add_edge(request_info, email_validator)
    .build()
)

# 2. Use in parent workflow
class ParentOrchestrator(Executor):
    @handler
    async def start(self, emails: list[str], ctx: WorkflowContext) -> None:
        for email in emails:
            await ctx.send_message(email, target_id="validator")
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(
        self,
        request: DomainCheckRequest,
        ctx: WorkflowContext
    ) -> RequestResponse:
        if request.domain in self.approved_domains:
            return RequestResponse.handled(True)
        return RequestResponse.forward()

# 3. Wire together
orchestrator = ParentOrchestrator()
validator = WorkflowExecutor(validation_workflow, id="validator")
external_request = RequestInfoExecutor()

main_workflow = (
    WorkflowBuilder()
    .set_start_executor(orchestrator)
    .add_edge(orchestrator, validator)
    .add_edge(validator, orchestrator)
    .add_edge(orchestrator, external_request)
    .add_edge(external_request, orchestrator)
    .build()
)
```

### Multiple Sub-Workflows with Scoping

```python
class MultiWorkflowOrchestrator(Executor):
    @intercepts_request(ConfigRequest, from_workflow="workflow_a")
    async def config_for_a(self, request: ConfigRequest, ctx: WorkflowContext) -> RequestResponse:
        return RequestResponse.handled(self.config_a)
    
    @intercepts_request(ConfigRequest, from_workflow="workflow_b")
    async def config_for_b(self, request: ConfigRequest, ctx: WorkflowContext) -> RequestResponse:
        return RequestResponse.handled(self.config_b)
    
    @intercepts_request(ConfigRequest)  # Fallback for any other workflow
    async def default_config(self, request: ConfigRequest, ctx: WorkflowContext) -> RequestResponse:
        return RequestResponse.handled(self.default_config)
```

### Conditional Forwarding

```python
class SmartOrchestrator(Executor):
    @intercepts_request(DatabaseQueryRequest)
    async def handle_db_query(
        self,
        request: DatabaseQueryRequest,
        ctx: WorkflowContext
    ) -> RequestResponse:
        # Simple queries we can handle locally
        if request.query.startswith("SELECT COUNT"):
            count = await self.local_db.count(request.table)
            return RequestResponse.handled(count)
        
        # Complex queries need the main database - forward with timeout
        return RequestResponse.forward(
            DatabaseQueryRequest(
                query=request.query,
                timeout=30,
                read_only=True
            )
        )
```

## Implementation Considerations

### 1. Error Handling

```python
class WorkflowExecutor(Executor):
    @handler
    async def execute(self, input_data: Any, ctx: WorkflowContext) -> None:
        try:
            async for event in self._workflow.run_streaming(input_data):
                # ... handle events ...
        except Exception as e:
            # Sub-workflow failed
            await ctx.add_event(ExecutorErrorEvent(
                executor_id=self.id,
                error=str(e),
                sub_workflow_error=True
            ))
            raise
```

### 2. Error Handling

```python
class WorkflowExecutor(Executor):
    async def execute(self, input_data: Any, ctx: WorkflowContext) -> None:
        """Execute sub-workflow with proper error handling."""
        try:
            async for event in self._workflow.run_streaming(input_data):
                if isinstance(event, WorkflowCompletedEvent):
                    # Send raw result back to parent
                    await ctx.send_message(event.data)
                elif isinstance(event, RequestInfoEvent):
                    await self._handle_request_info_event(event, ctx)
        except Exception as e:
            # Sub-workflow failed - propagate error
            await ctx.add_event(ExecutorErrorEvent(
                executor_id=self.id,
                error=str(e)
            ))
            raise
```

### 3. State Management

```python
class WorkflowExecutor(Executor):
    async def _create_sub_workflow_state(self, parent_ctx: WorkflowContext) -> SharedState:
        """Create isolated state for sub-workflow."""
        # For simplicity, sub-workflows get isolated state by default
        # State sharing can be implemented later as needed
        return SharedState()
```

### 4. Performance Optimizations

```python
class Executor:
    def _discover_handlers(self):
        """Optimize handler discovery."""
        # Cache discovered handlers to avoid reflection overhead
        if hasattr(self.__class__, '_cached_request_handlers'):
            self._request_handlers = self.__class__._cached_request_handlers.copy()
        else:
            # ... discovery logic ...
            self.__class__._cached_request_handlers = self._request_handlers.copy()
```

## Integration with Existing Framework

### Changes to WorkflowBuilder

```python
class WorkflowBuilder:
    def add_sub_workflow(
        self,
        sub_workflow: Workflow,
        id: str
    ) -> 'WorkflowBuilder':
        """Convenience method for adding sub-workflows."""
        executor = WorkflowExecutor(sub_workflow, id=id)
        return self.add_executor(executor)
```

### Changes to Runner

```python
class Runner:
    async def _handle_request_info_event(self, event: RequestInfoEvent) -> None:
        """Enhanced to handle sub-workflow metadata."""
        if 'sub_workflow_id' in event.metadata:
            # Store context for response routing
            self._sub_workflow_contexts[event.request_id] = event.metadata
        # ... existing logic ...
```

## Message Visibility and Privacy Considerations

### Current Limitations

The current design does not provide a specific mechanism to control which messages from a sub-workflow are visible to the parent workflow. By default:

- **All completion messages bubble up**: When a sub-workflow completes, its final output is automatically sent to the parent
- **No built-in filtering**: The `WorkflowExecutor` passes all workflow completion data to the parent without filtering
- **Privacy concerns**: Sensitive data within a sub-workflow could inadvertently leak to the parent

### Current Workaround: Targeted Messages

The only way to prevent messages from bubbling up to the parent is to use `target_id` for every message send within the sub-workflow:

```python
class SecureProcessor(Executor):
    @handler
    async def process(self, data: SensitiveData, ctx: WorkflowContext) -> None:
        # Internal message - use target_id to keep it within sub-workflow
        internal_result = InternalProcessingResult(
            sensitive_field="private_data",
            internal_state="should_not_leak"
        )
        await ctx.send_message(internal_result, target_id="internal_aggregator")
        
        # Only the final executor's output (without target_id) goes to parent
        public_summary = PublicSummary(status="complete", record_count=42)
        await ctx.send_message(public_summary)  # This becomes workflow output
```

This approach requires discipline - every internal message must explicitly specify a `target_id`, or it may become visible to the parent.

### Future Enhancement: Protocol-Based Privacy

In the future, we may provide a mechanism using Python protocols to mark message types as private:

```python
# Potential future enhancement (not currently implemented)
class PrivateMessage(Protocol):
    """Marker protocol for messages that should not leave the workflow."""
    pass

class InternalState(PrivateMessage):
    """This message type would automatically be filtered from parent visibility."""
    sensitive_data: str
    internal_metrics: dict

class WorkflowExecutor(Executor):
    async def execute(self, input_data: Any, ctx: WorkflowContext) -> None:
        async for event in self._workflow.run_streaming(input_data):
            if isinstance(event, WorkflowCompletedEvent):
                # Future: Check protocol to filter private messages
                if not isinstance(event.data, PrivateMessage):
                    await ctx.send_message(event.data)
```

This would provide a cleaner, more declarative way to control message visibility without requiring `target_id` on every internal message. However, this is not part of the current design and would be added based on actual use cases and requirements.

## Testing Strategy

### Unit Tests

```python
async def test_sub_workflow_request_routing():
    """Test that requests are properly routed to handlers."""
    # Setup
    orchestrator = TestOrchestrator()
    request = SubWorkflowRequestInfo(
        request_id="123",
        sub_workflow_id="test_workflow",
        data=DomainCheckRequest(domain="test.com")
    )
    
    # Execute
    await orchestrator._handle_sub_workflow_request(request, mock_context)
    
    # Verify response sent back
    mock_context.send_message.assert_called_with(
        SubWorkflowResponse(request_id="123", data=True),
        target_id="test_workflow"
    )

async def test_request_forwarding():
    """Test that unhandled requests are forwarded."""
    # ... test forwarding behavior ...

async def test_conditional_forwarding():
    """Test RequestResponse.forward() behavior."""
    # ... test conditional logic ...
```

### Integration Tests

```python
async def test_end_to_end_sub_workflow():
    """Test complete sub-workflow execution."""
    # Create sub-workflow with RequestInfo
    # Create parent with @intercepts_request
    # Wire together and execute
    # Verify request interception and response
```

## Migration Path

### For Existing Workflows

1. **No changes required** for existing workflows - they continue to work as before
2. **Optional enhancement** - add `@intercepts_request` methods to enable interception
3. **Gradual adoption** - start with simple static sub-workflows, add interception later

### For Custom Executors

1. **No breaking changes** - custom executors inherit new functionality automatically
2. **Optional adoption** - use `@intercepts_request` when needed
3. **Performance** - zero overhead if `@intercepts_request` not used