# Sub-Workflows User Guide

## Introduction

This guide shows you how to use sub-workflows to build modular, reusable, and maintainable workflow systems. Sub-workflows let you compose complex workflows from simpler building blocks, similar to how you compose applications from functions and classes.

## When to Use Sub-Workflows

Use sub-workflows when you need to:
- **Reuse workflow logic** across different parent workflows
- **Encapsulate complex processes** as single workflow components
- **Build hierarchical systems** with parent-child relationships
- **Optimize external requests** through parent workflow interception
- **Test workflows in isolation** before composing them

## Getting Started

To use sub-workflows, you'll need to import the `WorkflowExecutor` class:

```python
from agent_framework_workflow import WorkflowExecutor
```

The basic pattern is:
1. Create a workflow as you normally would
2. Wrap it in a `WorkflowExecutor` to use it as a sub-workflow
3. Add the executor to your parent workflow like any other executor

## Core Concepts

### Workflow Composition
Think of sub-workflows as "workflow functions" - they take input, process it, and return output. The parent workflow doesn't need to know the internal details, and the sub-workflow doesn't need to know it's being used as a component.

### Request Interception
Parent workflows can intercept and handle requests from sub-workflows before they go to external services. This is powerful for:
- **Performance optimization** through caching
- **Business rule enforcement** at the orchestration layer
- **Mock responses** during testing
- **Request transformation** before forwarding

### Automatic Message Routing
The framework handles all the complexity of routing messages between workflows. You just focus on your business logic.

## Your First Sub-Workflow

Let's start with the simplest possible sub-workflow - a text processor that converts text to uppercase. This example shows the basic pattern you'll use for all sub-workflows.

### Step-by-Step Example

```python
import asyncio
from agent_framework.workflow import (
    Executor, WorkflowBuilder, WorkflowCompletedEvent, 
    WorkflowContext, handler
)
from agent_framework_workflow import WorkflowExecutor

# Step 1: Define your sub-workflow
class TextProcessor(Executor):
    """A simple text processor that works as a sub-workflow."""
    
    def __init__(self):
        super().__init__(id="text_processor")
    
    @handler(output_types=[])
    async def process_text(self, text: str, ctx: WorkflowContext) -> None:
        """Process text by converting to uppercase."""
        print(f"Sub-workflow processing: '{text}'")
        processed = text.upper()
        print(f"Sub-workflow result: '{processed}'")
        # Complete the sub-workflow with the result
        await ctx.add_event(WorkflowCompletedEvent(data=processed))

# Step 2: Create the sub-workflow
text_processor = TextProcessor()

processing_workflow = WorkflowBuilder().set_start_executor(text_processor).build()

# Step 3: Use it in a parent workflow
class ParentOrchestrator(Executor):
    """Parent orchestrator that manages text processing sub-workflows."""
    
    def __init__(self):
        super().__init__(id="orchestrator")
        self.results: list[str] = []
    
    @handler(output_types=[str])
    async def start(self, texts: list[str], ctx: WorkflowContext) -> None:
        """Send texts to sub-workflow for processing."""
        print(f"Parent starting processing of {len(texts)} texts")
        for text in texts:
            await ctx.send_message(text)
    
    @handler(output_types=[])
    async def collect_result(self, result: str, ctx: WorkflowContext) -> None:
        """Collect results from sub-workflow."""
        print(f"Parent collected result: '{result}'")
        self.results.append(result)

# Step 4: Wire everything together
async def main():
    parent = ParentOrchestrator()
    text_workflow_executor = WorkflowExecutor(processing_workflow, id="text_workflow")
    
    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, text_workflow_executor)
        .add_edge(text_workflow_executor, parent)
        .build()
    )
    
    # Test with sample texts
    test_texts = ["hello", "world", "sub-workflow", "example"]
    print(f"Testing with texts: {test_texts}")
    
    # Run the workflow
    result = await main_workflow.run(test_texts)
    
    print("Final Results:")
    for i, result_text in enumerate(parent.results):
        original = test_texts[i] if i < len(test_texts) else "unknown"
        print(f"'{original}' -> '{result_text}'")
    
    print(f"Processed {len(parent.results)} texts total")

if __name__ == "__main__":
    asyncio.run(main())
```

## Handling External Requests in Sub-Workflows

Your sub-workflows will often need to fetch external data - from databases, APIs, or other services. The framework provides a clean pattern for this that works seamlessly with workflow composition.

### How to Make External Requests

When your sub-workflow needs external information, follow this pattern:

```python
from agent_framework_workflow import RequestInfoMessage, RequestInfoExecutor

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
    """Validates emails by checking domain approval."""
    
    def __init__(self):
        super().__init__(id="email_validator")
        self._pending_email = None
    
    @handler(output_types=[DomainCheckRequest, ValidationResult])
    async def validate(self, email: str, ctx: WorkflowContext) -> None:
        """Validate an email address."""
        self._pending_email = email
        domain = email.split("@")[1] if "@" in email else ""
        
        if not domain:
            result = ValidationResult(email=email, is_valid=False, reason="Invalid email format")
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            return
        
        # Request external domain check
        domain_check = DomainCheckRequest(domain=domain)
        await ctx.send_message(domain_check, target_id="request_info")
    
    @handler(output_types=[ValidationResult])
    async def handle_domain_response(
        self, response: RequestResponse[DomainCheckRequest, bool], ctx: WorkflowContext
    ) -> None:
        """Handle domain check response with correlation."""
        print(f"Domain check result: {response.original_request.domain} -> {response.data}")
        
        if self._pending_email:
            result = ValidationResult(
                email=self._pending_email,
                is_valid=response.data or False,
                reason="Domain approved" if response.data else "Domain not approved",
            )
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            self._pending_email = None

# Sub-workflow setup
email_validator = EmailValidator()
request_info = RequestInfoExecutor(id="request_info")

validation_workflow = (
    WorkflowBuilder()
    .set_start_executor(email_validator)
    .add_edge(email_validator, request_info)
    .add_edge(request_info, email_validator)
    .build()
)
```

## Intercepting Sub-Workflow Requests

One of the most powerful features of sub-workflows is request interception. Your parent workflow can intercept requests from sub-workflows and decide whether to handle them locally or forward them to external services.

### Why Intercept Requests?

Intercepting requests lets you:
- **Cache frequently requested data** to reduce external API calls
- **Apply business rules** at the orchestration layer
- **Transform requests** before sending them to external services
- **Provide mock data** during development and testing
- **Implement circuit breakers** for external service failures

### How to Intercept Requests

Use the `@intercepts_request` decorator in your parent workflow:

```python
from agent_framework_workflow import RequestResponse, intercepts_request

class SmartEmailOrchestrator(Executor):
    """Parent that can intercept domain checks for optimization."""
    
    def __init__(self):
        super().__init__(id="orchestrator")
        self.approved_domains = {"company.com", "partner.org"}
        self.results: list[ValidationResult] = []
    
    @handler(output_types=[str])
    async def start(self, emails: list[str], ctx: WorkflowContext) -> None:
        """Start email validation."""
        for email in emails:
            await ctx.send_message(email, target_id="email_workflow")
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(
        self, 
        request: DomainCheckRequest, 
        ctx: WorkflowContext
    ) -> RequestResponse[DomainCheckRequest, bool]:
        """Intercept domain checks from sub-workflows."""
        
        if request.domain in self.approved_domains:
            # We know this domain - handle locally
            print(f"Domain {request.domain} is pre-approved locally!")
            return RequestResponse[DomainCheckRequest, bool].handled(True)
        
        # We don't know - forward to external service
        print(f"Domain {request.domain} unknown, forwarding to external service...")
        return RequestResponse.forward()
    
    @handler(output_types=[])
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        """Collect validation results."""
        print(f"Email validation result: {result.email} -> {result.is_valid} ({result.reason})")
        self.results.append(result)
```

## Data Flow Diagrams

### Basic Sub-Workflow Flow

```
┌─────────────────┐    input     ┌──────────────────┐    processed
│ Parent          │─────────────►│ WorkflowExecutor │─────────────►
│ Orchestrator    │              │ (Text Processor) │
└─────────────────┘◄─────────────└──────────────────┘
                        result
```

### Request/Response Flow Without Interception

```
┌─────────────────┐     email      ┌──────────────────┐
│ Parent          │───────────────►│ WorkflowExecutor │
│ Orchestrator    │                │ (Email Validator)│
└─────────────────┘                └──────────────────┘
        ▲                                    │
        │                                    │ DomainCheckRequest
        │                                    ▼
        │                          ┌─────────────────┐
        │ ValidationResult         │ RequestInfo     │
        │                          │ Executor        │
        │                          └─────────────────┘
        │                                    │
        │                                    │ RequestInfoEvent
        │                                    ▼
        │                          ┌─────────────────┐
        └──────────────────────────│ External        │
                                   │ Handler         │
                                   └─────────────────┘
```

### Request/Response Flow With Interception

```
┌─────────────────┐     email      ┌──────────────────┐
│ Parent          │───────────────►│ WorkflowExecutor │
│ Orchestrator    │                │ (Email Validator)│
│                 │                └──────────────────┘
│ @intercepts_    │                          │
│ request         │                          │ DomainCheckRequest
│                 │                          ▼
│                 │◄─────────────────────────┤ (intercepted)
│                 │ SubWorkflowRequestInfo   │
│                 │                          │
│ if known domain:│                          │
│   handled(True) │                          │
│ else:           │                          │
│   forward()     │─────────────────────────►│
│                 │                          ▼
│                 │                ┌─────────────────┐
│                 │                │ RequestInfo     │
│                 │                │ Executor        │
│                 │                └─────────────────┘
└─────────────────┘                          │
        ▲                                    │ RequestInfoEvent
        │                                    ▼
        │                          ┌─────────────────┐
        │ ValidationResult         │ External        │
        └──────────────────────────│ Handler         │
                                   └─────────────────┘
```

## Common Patterns and Best Practices

### Pattern 1: Caching with TTL

Here's how to implement a cache with time-to-live (TTL) in your parent workflow:

```python
class CachingOrchestrator(Executor):
    """Parent with intelligent caching and forwarding."""
    
    def __init__(self):
        super().__init__(id="caching_orchestrator")
        self.domain_cache = {}  # domain -> (timestamp, result)
        self.cache_ttl = 300    # 5 minutes
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(
        self, 
        request: DomainCheckRequest, 
        ctx: WorkflowContext
    ) -> RequestResponse:
        """Check cache first, then conditionally forward."""
        
        # Check cache with TTL
        if request.domain in self.domain_cache:
            cached_time, cached_result = self.domain_cache[request.domain]
            if time.time() - cached_time < self.cache_ttl:
                return RequestResponse.handled(cached_result)
        
        # Check business rules
        if request.domain.endswith(".internal"):
            result = True
            self.domain_cache[request.domain] = (time.time(), result)
            return RequestResponse.handled(result)
        
        # Need external verification
        return RequestResponse.forward()
```

### Pattern 2: Different Rules for Different Sub-Workflows

When you have multiple sub-workflows, you can apply different interception rules to each:

```python
class MultiWorkflowOrchestrator(Executor):
    """Handle different rules for different sub-workflows."""
    
    def __init__(self):
        super().__init__(id="multi_orchestrator")
    
    @intercepts_request(DomainCheckRequest, from_workflow="email_validator")
    async def check_email_domain(
        self, 
        request: DomainCheckRequest, 
        ctx: WorkflowContext
    ) -> RequestResponse:
        """Strict rules for email validation."""
        if request.domain in {"company.com", "partner.org"}:
            return RequestResponse.handled(True)
        return RequestResponse.forward()
    
    @intercepts_request(DomainCheckRequest, from_workflow="api_validator")
    async def check_api_domain(
        self, 
        request: DomainCheckRequest, 
        ctx: WorkflowContext
    ) -> RequestResponse:
        """Different rules for API validation."""
        if request.domain.endswith(".api.company.com"):
            return RequestResponse.handled(True)
        return RequestResponse.forward()
```

## Complete Working Example

Let's put it all together with a complete email validation system that demonstrates all the key concepts. You can copy this code and run it directly:

```python
import asyncio
from dataclasses import dataclass
from agent_framework.workflow import (
    Executor, RequestInfoExecutor, WorkflowBuilder, WorkflowCompletedEvent,
    WorkflowContext, handler
)
from agent_framework_workflow import (
    RequestInfoMessage, RequestResponse, WorkflowExecutor, intercepts_request
)

# Domain types
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

# Sub-workflow: Email Validator
class EmailValidator(Executor):
    """Validates emails by checking domain approval."""
    
    def __init__(self):
        super().__init__(id="email_validator")
        self._pending_email = None
    
    @handler(output_types=[DomainCheckRequest, ValidationResult])
    async def validate(self, email: str, ctx: WorkflowContext) -> None:
        """Validate an email address."""
        self._pending_email = email
        domain = email.split("@")[1] if "@" in email else ""
        
        if not domain:
            result = ValidationResult(email=email, is_valid=False, reason="Invalid email format")
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            return
        
        # Request external domain check
        domain_check = DomainCheckRequest(domain=domain)
        await ctx.send_message(domain_check, target_id="request_info")
    
    @handler(output_types=[ValidationResult])
    async def handle_domain_response(
        self, response: RequestResponse[DomainCheckRequest, bool], ctx: WorkflowContext
    ) -> None:
        """Handle domain check response with correlation."""
        print(f"Domain check result: {response.original_request.domain} -> {response.data}")
        
        if self._pending_email:
            result = ValidationResult(
                email=self._pending_email,
                is_valid=response.data or False,
                reason="Domain approved" if response.data else "Domain not approved",
            )
            await ctx.add_event(WorkflowCompletedEvent(data=result))
            self._pending_email = None

# Parent workflow with intelligent interception
class SmartEmailOrchestrator(Executor):
    """Parent that can intercept domain checks for optimization."""
    
    def __init__(self):
        super().__init__(id="orchestrator")
        self.approved_domains = {"company.com", "partner.org"}
        self.results: list[ValidationResult] = []
    
    @handler(output_types=[str])
    async def start(self, emails: list[str], ctx: WorkflowContext) -> None:
        """Start email validation."""
        for email in emails:
            await ctx.send_message(email, target_id="email_workflow")
    
    @intercepts_request(DomainCheckRequest)
    async def check_domain(
        self, 
        request: DomainCheckRequest, 
        ctx: WorkflowContext
    ) -> RequestResponse[DomainCheckRequest, bool]:
        """Intercept domain checks from sub-workflows."""
        
        if request.domain in self.approved_domains:
            # We know this domain - handle locally
            print(f"Domain {request.domain} is pre-approved locally!")
            return RequestResponse[DomainCheckRequest, bool].handled(True)
        
        # We don't know - forward to external service
        print(f"Domain {request.domain} unknown, forwarding to external service...")
        return RequestResponse.forward()
    
    @handler(output_types=[])
    async def collect_result(self, result: ValidationResult, ctx: WorkflowContext) -> None:
        """Collect validation results."""
        print(f"Email validation result: {result.email} -> {result.is_valid} ({result.reason})")
        self.results.append(result)

# Setup and execution
async def main():
    """Main function to run the request interception example."""
    print("Setting up sub-workflow with request interception...")
    
    # Sub-workflow setup
    email_validator = EmailValidator()
    request_info = RequestInfoExecutor(id="request_info")
    
    validation_workflow = (
        WorkflowBuilder()
        .set_start_executor(email_validator)
        .add_edge(email_validator, request_info)
        .add_edge(request_info, email_validator)
        .build()
    )
    
    # Parent workflow setup with interception
    orchestrator = SmartEmailOrchestrator()
    email_workflow = WorkflowExecutor(validation_workflow, id="email_workflow")
    main_request_info = RequestInfoExecutor()
    
    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(orchestrator)
        .add_edge(orchestrator, email_workflow)
        .add_edge(email_workflow, orchestrator)
        .add_edge(orchestrator, main_request_info)  # For forwarded requests
        .add_edge(main_request_info, orchestrator)
        .build()
    )
    
    # Test emails - mix of known and unknown domains
    test_emails = [
        "user@company.com",    # Will be intercepted and approved
        "admin@partner.org",   # Will be intercepted and approved  
        "guest@external.com"   # Will be forwarded to external check
    ]
    
    print(f"Testing with emails: {test_emails}")
    print("=" * 60)
    
    # Run the workflow
    result = await main_workflow.run(test_emails)
    
    # Handle any external requests that were forwarded
    request_events = result.get_request_info_events()
    if request_events:
        print(f"\nGot {len(request_events)} external request(s) to handle")
        
        # Simulate external service responses
        external_responses = {}
        for event in request_events:
            print(f"External request for domain: {event.data.domain}")
            # For demo purposes, approve external.com
            approved = event.data.domain == "external.com"
            external_responses[event.request_id] = approved
            print(f"External service response: {approved}")
        
        # Send responses back to the workflow
        await main_workflow.send_responses(external_responses)
    else:
        print("\nAll requests were intercepted and handled locally!")
    
    print("\nValidation Results:")
    print("=" * 60)
    for result in orchestrator.results:
        status = "VALID" if result.is_valid else "INVALID"
        print(f"{status} {result.email}: {result.reason}")
    
    print(f"\nProcessed {len(orchestrator.results)} emails total")

if __name__ == "__main__":
    asyncio.run(main())
```

## Troubleshooting

### Common Issues and Solutions

#### Issue: "Results not being collected from sub-workflow"
**Cause**: Missing `WorkflowCompletedEvent` in sub-workflow  
**Solution**: Always emit `WorkflowCompletedEvent` with your result data:
```python
await ctx.add_event(WorkflowCompletedEvent(data=result))
```

#### Issue: "Request interception not working"
**Cause**: Incorrect type matching or missing generic parameters  
**Solution**: Ensure your handler accepts `RequestResponse` with proper generics:
```python
async def handle_response(
    self, response: RequestResponse[DomainCheckRequest, bool], ctx: WorkflowContext
) -> None:
```

#### Issue: "TypeError with RequestInfoMessage inheritance"
**Cause**: Missing default value for fields when inheriting from `RequestInfoMessage`  
**Solution**: Add default values to your dataclass fields:
```python
@dataclass
class MyRequest(RequestInfoMessage):
    field: str = ""  # Need default value
```

#### Issue: "Sub-workflow not receiving messages"
**Cause**: Incorrect `target_id` in parent workflow  
**Solution**: Ensure the `target_id` matches the `WorkflowExecutor` ID:
```python
workflow_executor = WorkflowExecutor(workflow, id="my_workflow")
# Later...
await ctx.send_message(data, target_id="my_workflow")  # Must match!
```

## Tips for Success

### Start Simple
Begin with basic sub-workflows without external requests. Once comfortable, add request/response patterns and finally request interception.

### Test in Isolation
Test your sub-workflows independently before integrating them:
```python
# Test sub-workflow directly
result = await my_sub_workflow.run(test_input)
assert result.get_completed_event().data == expected_output
```

### Use Type Hints
Always use proper type hints for better IDE support and error detection:
```python
@handler(output_types=[ValidationResult])
async def process(self, email: str, ctx: WorkflowContext) -> None:
```

### Monitor Request Flow
During development, add logging to track request flow:
```python
print(f"Intercepting request: {request}")
print(f"Forwarding to external: {request.domain}")
```

## When to Use Sub-Workflows vs Other Patterns

### Use Sub-Workflows When:
- You need to reuse entire workflow logic
- You want strong encapsulation between components
- You need request interception capabilities
- You're building a hierarchical system

### Use Regular Executors When:
- The logic is simple and doesn't need its own workflow
- You don't need request interception
- The component is tightly coupled to the parent workflow

### Use Multiple Workflows When:
- The workflows run independently
- There's no parent-child relationship
- You need different deployment or scaling strategies

## Next Steps

1. **Try the examples**: Run `step_09_intercept_sub_workflow.py` and `step_10_simple_sub_workflow.py`
2. **Build your own**: Start with a simple sub-workflow for your use case
3. **Add interception**: Implement caching or business rules in parent workflows
4. **Share patterns**: Document patterns that work well for your team

## Additional Resources

- [Workflow Basics Documentation](../workflow-basics.md)
- [Request/Response Pattern Guide](../request-response.md)
- [Complete API Reference](../api-reference.md)
- [Sample Code Repository](../../samples/getting_started/workflow/)

This guide enables you to build powerful, modular workflow systems using sub-workflows. Start simple, iterate, and gradually add more sophisticated patterns as your needs grow.