# Conditional Request Forwarding Patterns

## The Problem

With automatic routing to `@intercepts_request`, what happens when the parent realizes it can't actually handle the request and needs to forward it to external sources?

```python
@intercepts_request(DomainCheckRequest)
async def check_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> ???:
    """What if we don't have the answer?"""
    
    if request.domain in self.approved_domains:
        return True  # We can handle it
    
    # But what if we need to check externally for unknown domains?
    # How do we say "I can't handle this, forward it"?
```

## Solution Options

### Option 1: Return Special Sentinel Value (Simple but Limited)

Use a special return value to indicate "forward this request":

```python
from agent_framework_workflow import FORWARD_REQUEST

class ParentOrchestrator(InterceptingExecutor):
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> bool | object:
        """Check domain if we can, otherwise forward."""
        
        # Check our cache first
        if request.domain in self.cached_domains:
            return self.cached_domains[request.domain]
        
        # We don't know - forward to external
        return FORWARD_REQUEST  # Special sentinel value

# Framework implementation
class InterceptingExecutor(Executor):
    @handler
    async def _handle_sub_workflow_request(self, request: SubWorkflowRequestInfo, ctx: WorkflowContext) -> None:
        for request_type, handler_info in self._request_handlers.items():
            if isinstance(request.data, request_type):
                result = await handler_info['method'](request.data, ctx)
                
                if result is FORWARD_REQUEST:
                    # Forward to external RequestInfoExecutor
                    await ctx.send_message(request.data)
                else:
                    # Send response back to sub-workflow
                    await ctx.send_message(
                        SubWorkflowResponse(request_id=request.request_id, data=result),
                        target_id=request.sub_workflow_id
                    )
                return
```

**Pros**: Simple, clear intent
**Cons**: Type checking becomes complex with union types

### Option 2: Raise ForwardException (Clean Control Flow)

Use an exception to indicate forwarding:

```python
from agent_framework_workflow import ForwardRequestException

class ParentOrchestrator(InterceptingExecutor):
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> bool:
        """Check domain if we can, otherwise forward."""
        
        # Check our cache
        if request.domain in self.cached_domains:
            return self.cached_domains[request.domain]
        
        # Check if it's a special domain we handle
        if request.domain.endswith(".internal"):
            return True
        
        # We can't handle this - forward it
        raise ForwardRequestException("Domain not in cache, need external check")

# Framework implementation
class InterceptingExecutor(Executor):
    @handler
    async def _handle_sub_workflow_request(self, request: SubWorkflowRequestInfo, ctx: WorkflowContext) -> None:
        for request_type, handler_info in self._request_handlers.items():
            if isinstance(request.data, request_type):
                try:
                    result = await handler_info['method'](request.data, ctx)
                    # Send response back to sub-workflow
                    await ctx.send_message(
                        SubWorkflowResponse(request_id=request.request_id, data=result),
                        target_id=request.sub_workflow_id
                    )
                except ForwardRequestException:
                    # Forward to external RequestInfoExecutor
                    await ctx.send_message(request.data)
                return
```

**Pros**: Clean type signatures, clear control flow
**Cons**: Using exceptions for control flow

### Option 3: Return Response Object (Most Flexible) - RECOMMENDED

Return a response object that can indicate handling or forwarding:

```python
from agent_framework_workflow import RequestResponse, Forward

class ParentOrchestrator(InterceptingExecutor):
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> RequestResponse:
        """Check domain if we can, otherwise forward."""
        
        # Check our cache
        if request.domain in self.cached_domains:
            return RequestResponse.handled(self.cached_domains[request.domain])
        
        # Check special cases
        if request.domain.endswith(".internal"):
            return RequestResponse.handled(True)
        
        # Can't handle - forward with optional transformation
        if request.domain.endswith(".partner"):
            # Forward to specific partner API
            return RequestResponse.forward(
                modified_request=PartnerDomainRequest(domain=request.domain, api_key="...")
            )
        
        # Simple forward
        return RequestResponse.forward()

# Framework types
@dataclass
class RequestResponse:
    """Response from a request handler."""
    handled: bool
    data: Any = None
    forward_request: Any = None
    
    @staticmethod
    def handled(data: Any) -> 'RequestResponse':
        """Create a handled response."""
        return RequestResponse(handled=True, data=data)
    
    @staticmethod
    def forward(modified_request: Any = None) -> 'RequestResponse':
        """Create a forward response."""
        return RequestResponse(handled=False, forward_request=modified_request)

# Framework implementation
class InterceptingExecutor(Executor):
    @handler
    async def _handle_sub_workflow_request(self, request: SubWorkflowRequestInfo, ctx: WorkflowContext) -> None:
        for request_type, handler_info in self._request_handlers.items():
            if isinstance(request.data, request_type):
                response = await handler_info['method'](request.data, ctx)
                
                if response.handled:
                    # Send response back to sub-workflow
                    await ctx.send_message(
                        SubWorkflowResponse(request_id=request.request_id, data=response.data),
                        target_id=request.sub_workflow_id
                    )
                else:
                    # Forward to external (possibly with modifications)
                    forward_request = response.forward_request or request.data
                    await ctx.send_message(forward_request)
                return
```

**Pros**: 
- Most flexible
- Clean types
- Supports request transformation
- Explicit about intent

**Cons**: 
- Slightly more verbose
- New type to learn

### Option 4: Handler Can Send Messages Directly (Most Control)

Allow the handler to directly control message flow:

```python
class ParentOrchestrator(InterceptingExecutor):
    
    @intercepts_request(DomainCheckRequest, manual_response=True)
    async def check_domain(
        self, 
        request: DomainCheckRequest, 
        ctx: WorkflowContext,
        request_info: SubWorkflowRequestInfo  # Added parameter
    ) -> None:
        """Full control over response handling."""
        
        # Check our cache
        if request.domain in self.cached_domains:
            # Send response back to sub-workflow
            await ctx.send_message(
                SubWorkflowResponse(
                    request_id=request_info.request_id,
                    data=self.cached_domains[request.domain]
                ),
                target_id=request_info.sub_workflow_id
            )
        else:
            # Forward to external
            await ctx.send_message(request.data)
```

**Pros**: Maximum control
**Cons**: More boilerplate, defeats the purpose of automatic routing

### Option 5: Use Return Type Overloading

Use Python's type system to indicate forwarding:

```python
from typing import Union, Literal

ForwardRequest = Literal["FORWARD"]
FORWARD: ForwardRequest = "FORWARD"

class ParentOrchestrator(InterceptingExecutor):
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(
        self, 
        request: DomainCheckRequest, 
        ctx: WorkflowContext
    ) -> Union[bool, ForwardRequest]:
        """Return the answer or FORWARD."""
        
        if request.domain in self.cached_domains:
            return self.cached_domains[request.domain]
        
        return FORWARD  # Type-safe forward indicator
```

## Recommended Approach: Option 3 (Response Objects)

This provides the best balance of:
- **Clarity**: Explicit about handling vs forwarding
- **Flexibility**: Can transform requests when forwarding
- **Type Safety**: Clean type signatures
- **Extensibility**: Can add more response types later

### Full Example with Option 3

```python
# Developer code
class SmartParentOrchestrator(InterceptingExecutor):
    
    def __init__(self):
        super().__init__()
        self.domain_cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> RequestResponse:
        """Smart domain checking with caching and forwarding."""
        
        # Check cache with TTL
        cache_key = request.domain
        if cache_key in self.domain_cache:
            cached_time, cached_result = self.domain_cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                # Cache hit
                return RequestResponse.handled(cached_result)
        
        # Check if we can determine locally
        if request.domain.endswith(".internal"):
            result = True
            self.domain_cache[cache_key] = (time.time(), result)
            return RequestResponse.handled(result)
        
        if request.domain.endswith(".blocked"):
            result = False
            self.domain_cache[cache_key] = (time.time(), result)
            return RequestResponse.handled(result)
        
        # Need external verification - forward the request
        # Could even modify the request here if needed
        return RequestResponse.forward()
    
    @intercepts_request(DatabaseQueryRequest)
    async def check_database(self, request: DatabaseQueryRequest, ctx: WorkflowContext) -> RequestResponse:
        """Handle some queries locally, forward complex ones."""
        
        if request.query.startswith("SELECT COUNT"):
            # Simple count we can handle
            result = await self.local_db.count(request.table)
            return RequestResponse.handled(result)
        
        # Complex query - need the main database
        return RequestResponse.forward(
            modified_request=DatabaseQueryRequest(
                query=request.query,
                timeout=30,  # Add timeout for external
                read_only=True  # Ensure read-only for external
            )
        )
```

## Alternative: Hybrid Approach

Support both simple returns (when you can handle) and exceptions (when you can't):

```python
@intercepts_request(DomainCheckRequest)
async def check_domain(self, request: DomainCheckRequest, ctx: WorkflowContext) -> bool:
    if request.domain in self.cached_domains:
        return self.cached_domains[request.domain]  # Simple return when handled
    
    raise ForwardRequest()  # Exception when can't handle

# Framework handles both patterns
try:
    result = await handler(request.data, ctx)
    # Send response back
    await ctx.send_message(SubWorkflowResponse(...))
except ForwardRequest:
    # Forward to external
    await ctx.send_message(request.data)
```

This gives developers flexibility to use the pattern that feels most natural for their use case.