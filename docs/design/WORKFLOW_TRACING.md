# Workflow Tracing Design

## Overview

This document outlines the design for implementing distributed tracing in the Agent Framework workflow system using OpenTelemetry (OTel) semantic conventions. The tracing system will provide comprehensive visibility into workflow execution, message flows, and executor performance.

## Goals

1. **Comprehensive Tracing**: Trace complete workflow executions including message processing and publishing
2. **Distributed Context Propagation**: Link spans across executor boundaries using OTel trace context
3. **Message Semantics**: Follow OTel messaging semantic conventions for producer/consumer patterns
4. **Performance Monitoring**: Enable observability of workflow performance and bottlenecks
5. **Debugging Support**: Provide detailed traces for debugging workflow issues

## Architecture Overview

### Core Components

1. **WorkflowTracer**: Central tracing coordinator in `_telemetry.py`
2. **Message Extension**: Add optional trace context fields to existing `Message` class
3. **Context Propagation**: OpenTelemetry standard inject/extract in WorkflowContext
4. **EdgeRunner Integration**: Extract trace context and set execution context

### Tracing Flow

```text
Workflow Start
    │
    ├─ Workflow Span (operation: "workflow.run")
    │   │
    │   ├─ Executor Processing Span (operation: "executor.process")
    │   │   │
    │   │   ├─ Handler Span (operation: "executor.handler")
    │   │   │
    │   │   └─ Publishing Span (operation: "message.publish")
    │   │       │ (linked to source processing span)
    │   │       │
    │   │       └─ Next Executor Processing Span (operation: "executor.process")
    │   │           │ (linked to publishing span)
    │   │           └─ ...
    │   │
    │   └─ Workflow Completion
```

## Detailed Design

### 1. Instrumenting Module

**Module Name**: `agent_framework`

This follows the OTel convention where the instrumentation library name matches the instrumented library.

### 2. Span Structure

#### Workflow-Level Spans

**Workflow Execution Span**

- **Name**: `workflow.run`
- **Kind**: `SpanKind.INTERNAL`
- **Attributes**:
  - `workflow.id`: Unique workflow instance ID
  - `workflow.max_iterations`: Maximum iterations allowed
  - `workflow.current_iteration`: Current iteration number (updated during execution)
  - `workflow.total_iterations`: Final number of iterations completed
  - `workflow.status`: `running`, `completed`, `failed`
  - `workflow.completion_data`: Serialized completion data (if completed)

#### Executor-Level Spans

**Processing Span** (per executor invocation)

- **Name**: `executor.process`
- **Kind**: `SpanKind.CONSUMER` (consuming messages)
- **Attributes**:
  - `executor.id`: Unique executor ID  
  - `executor.type`: Executor class name
  - `executor.handler_method`: Name of the handler method invoked
  - `message.type`: Fully qualified name of the message type
  - `message.source_executor_id`: ID of executor that sent the message
  - `processing.iteration`: Current workflow iteration/superstep number

**Publishing Span** (per message sent)

- **Name**: `message.publish`
- **Kind**: `SpanKind.PRODUCER` (publishing messages)
- **Attributes**:
  - `message.destination_executor_id`: Target executor ID (if specified)
  - `message.type`: Fully qualified name of the message type
  - `message.count`: Number of messages published (for fan-out scenarios)

**Note**: Handler-level spans are optional and not implemented in the initial version for simplicity.

### 3. Context Propagation

#### Message Context Embedding

**Chosen Approach**: Extend the existing `Message` class with optional trace context fields. This approach provides explicit trace context propagation that works in both local and future distributed environments.

```python
# In _runner_context.py - extend existing Message class
@dataclass
class Message:
    """A class representing a message in the workflow."""
    
    data: Any
    source_id: str
    target_id: str | None = None
    
    # NEW: Optional trace context fields for OpenTelemetry propagation
    trace_context: dict[str, str] | None = None  # W3C Trace Context headers
    source_span_id: str | None = None  # Publishing span ID for linking
    
    # Benefits of this approach:
    # 1. Explicit trace context propagation 
    # 2. Works across async boundaries within processes
    # 3. Ready for future distributed execution (trace context serializes with message)
    # 4. Backward compatible (fields are optional)
    # 5. No impact when tracing is disabled
```

#### Span Linking Strategy

1. **Processing-to-Publishing Link**: Processing spans create child publishing spans
2. **Publishing-to-Processing Link**: Next processing span links to previous publishing span via `trace_context`
3. **Workflow Hierarchy**: All spans are children/descendants of the workflow execution span

#### Future Distributed Execution Readiness

The chosen design is ready for distributed execution with minimal changes:

**Current (Local) Message Flow:**
```
WorkflowContext.send_message() → Message(trace_context) → EdgeRunner → Executor
```

**Future (Distributed) Message Flow:**
```
WorkflowContext.send_message() → Message(trace_context) → Network Transport → Remote EdgeRunner → Remote Executor
```

**Required Changes for Distributed Execution:**
1. **Message Serialization**: `trace_context` dict already serializes to JSON/protobuf
2. **Network Transport**: HTTP headers, message queues, or gRPC metadata will carry trace context
3. **Cross-Service Linking**: OpenTelemetry's `extract()` automatically handles distributed trace linking

**Example Future Enhancement**:
```python
# Message serialization for network transport
def serialize_message(msg: Message) -> dict[str, Any]:
    return {
        "data": msg.data,
        "source_id": msg.source_id,
        "target_id": msg.target_id,
        "trace_context": msg.trace_context,  # ✅ Ready for network transport
        "source_span_id": msg.source_span_id
    }

# HTTP transport example
async def send_message_to_remote_executor(message: Message, target_url: str):
    payload = serialize_message(message)
    headers = message.trace_context or {}  # W3C headers for HTTP
    await httpx.post(target_url, json=payload, headers=headers)
```

## Implementation Guide

### Step 1: Create Telemetry Module

**File: `agent_framework/workflow/_telemetry.py`**

```python
from typing import ClassVar
from contextlib import nullcontext
from opentelemetry import trace
from opentelemetry.trace import get_tracer, SpanKind

from agent_framework._pydantic import AFBaseSettings

class WorkflowDiagnosticSettings(AFBaseSettings):
    """Settings for workflow tracing diagnostics."""
    
    env_prefix: ClassVar[str] = "AGENT_FRAMEWORK_"
    enable_workflow_tracing: bool = False

    @property
    def ENABLED(self) -> bool:
        return self.enable_workflow_tracing

class WorkflowTracer:
    """Central tracing coordinator for workflow system."""
    
    def __init__(self):
        self.tracer = get_tracer("agent_framework")
        self.settings = WorkflowDiagnosticSettings()
    
    @property
    def enabled(self) -> bool:
        return self.settings.ENABLED
    
    def create_workflow_span(self, workflow_id: str):
        """Create a workflow execution span."""
        if not self.enabled:
            return nullcontext()
            
        return self.tracer.start_as_current_span(
            "workflow.run",
            kind=SpanKind.INTERNAL,
            attributes={"workflow.id": workflow_id}
        )
    
    def create_processing_span(self, executor_id: str, executor_type: str, message_type: str):
        """Create an executor processing span."""
        if not self.enabled:
            return nullcontext()
            
        return self.tracer.start_as_current_span(
            "executor.process",
            kind=SpanKind.CONSUMER,
            attributes={
                "executor.id": executor_id,
                "executor.type": executor_type,
                "message.type": message_type,
            }
        )
    
    def create_publishing_span(self, message_type: str, target_executor_id: str | None = None):
        """Create a message publishing span."""
        if not self.enabled:
            return nullcontext()
            
        return self.tracer.start_as_current_span(
            "message.publish",
            kind=SpanKind.PRODUCER,
            attributes={
                "message.type": message_type,
                "message.destination_executor_id": target_executor_id,
            }
        )

# Global workflow tracer instance
workflow_tracer = WorkflowTracer()
```

### Step 2: Extend Message Class

**File: `agent_framework/workflow/_runner_context.py`**

```python
# Add to existing Message class
@dataclass
class Message:
    """A class representing a message in the workflow."""
    
    data: Any
    source_id: str
    target_id: str | None = None
    
    # NEW: Optional trace context fields
    trace_context: dict[str, str] | None = None  # W3C Trace Context headers
    source_span_id: str | None = None  # Publishing span ID for linking
```

### Step 3: Update Runner for Workflow Spans

**File: `agent_framework/workflow/_runner.py`**

```python
# Add import
from ._telemetry import workflow_tracer
from opentelemetry import trace

class Runner:
    async def run_until_convergence(self) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow until no more messages are sent."""
        
        # Create workflow span for entire execution
        with workflow_tracer.create_workflow_span(self._workflow_id) as span:
            try:
                if span and span.is_recording():
                    span.set_attribute("workflow.status", "running")
                    span.set_attribute("workflow.max_iterations", self._max_iterations)
                
                # Existing workflow logic...
                self._running = True
                
                while self._iteration < self._max_iterations:
                    if span and span.is_recording():
                        span.set_attribute("workflow.current_iteration", self._iteration + 1)
                    
                    # Existing iteration logic...
                    await self._run_iteration()
                    
                    # Yield events and check convergence...
                    if not await self._ctx.has_messages():
                        break
                
                # Success
                if span and span.is_recording():
                    span.set_attribute("workflow.status", "completed")
                    span.set_attribute("workflow.total_iterations", self._iteration)
                    
            except Exception as e:
                if span and span.is_recording():
                    span.set_attribute("workflow.status", "failed")
                    span.set_status(trace.StatusCode.ERROR, str(e))
                raise
            finally:
                self._running = False
```

### Step 4: Update Executor for Processing Spans

**File: `agent_framework/workflow/_executor.py`**

```python
# Add import
from ._telemetry import workflow_tracer
from opentelemetry import context as otel_context
from opentelemetry.propagate import extract

class Executor:
    async def execute(self, message: Any, context: WorkflowContext[Any]) -> None:
        # Set trace context from WorkflowContext if available
        trace_context_manager = None
        if context._trace_context and workflow_tracer.enabled:
            extracted_context = extract(context._trace_context)
            trace_context_manager = otel_context.use_context(extracted_context)
        
        # Execute within trace context
        async def _execute_with_tracing():
            # Create processing span (inherits trace context automatically)
            with workflow_tracer.create_processing_span(
                self.id, 
                self.__class__.__name__, 
                type(message).__name__
            ):
                # Find and execute handler
                handler = self._find_handler(message)
                await handler(message, context)
        
        if trace_context_manager:
            with trace_context_manager:
                await _execute_with_tracing()
        else:
            await _execute_with_tracing()
```

### Step 5: Update WorkflowContext to Include Trace Context

**File: `agent_framework/workflow/_workflow_context.py`**

```python
# Add imports
from ._telemetry import workflow_tracer
from ._runner_context import Message
from opentelemetry import trace, context as otel_context
from opentelemetry.propagate import inject

class WorkflowContext:
    def __init__(self, executor_id: str, source_executor_ids: list[str], 
                 shared_state: SharedState, runner_context: RunnerContext,
                 trace_context: dict[str, str] | None = None):  # NEW parameter
        # Existing initialization...
        self._executor_id = executor_id
        self._source_executor_ids = source_executor_ids
        self._shared_state = shared_state
        self._runner_context = runner_context
        
        # NEW: Store trace context for this execution context
        self._trace_context = trace_context
        
        # Set trace context as current if provided
        if self._trace_context and workflow_tracer.enabled:
            from opentelemetry.propagate import extract
            extracted_context = extract(self._trace_context)
            # Note: The context will be used by the current span creation
    
    async def send_message(self, message: Any, target_id: str | None = None):
        # Create publishing span (inherits current trace context automatically)
        with workflow_tracer.create_publishing_span(type(message).__name__, target_id) as span:
            # Create Message wrapper
            msg = Message(data=message, source_id=self._executor_id, target_id=target_id)
            
            # Inject current trace context if tracing enabled
            if workflow_tracer.enabled and span and span.is_recording():
                trace_context: dict[str, str] = {}
                inject(trace_context)  # Standard OTel injection
                
                msg.trace_context = trace_context
                msg.source_span_id = format(span.get_span_context().span_id, '016x')
            
            await self._runner_context.send_message(msg)
```

### Step 6: Update All executor.execute() Call Sites

**File: `agent_framework/workflow/_edge_runner.py`**

```python
# Add imports
from ._telemetry import workflow_tracer
from opentelemetry import context as otel_context
from opentelemetry.propagate import extract

class EdgeRunner:
    # Update method signature
    async def _execute_on_target(
        self, target_id: str, source_id: str, message: Message,  # Full Message object
        shared_state: SharedState, ctx: RunnerContext
    ) -> None:
        """Execute a message on a target executor with trace context."""
        if target_id not in self._executors:
            raise RuntimeError(f"Target executor {target_id} not found.")

        target_executor = self._executors[target_id]
        
        # Create WorkflowContext with trace context from message
        workflow_context = WorkflowContext(
            target_id, 
            [source_id], 
            shared_state, 
            ctx,
            trace_context=message.trace_context  # Pass trace context to WorkflowContext
        )
        
        # Execute with trace context in WorkflowContext
        await target_executor.execute(message.data, workflow_context)

# Update all EdgeRunner subclasses to pass full Message
class SingleEdgeRunner(EdgeRunner):
    async def send_message(self, message: Message, shared_state: SharedState, ctx: RunnerContext) -> bool:
        # Existing logic...
        if self._can_handle(self._edge.target_id, message.data):
            if self._edge.should_route(message.data):
                await self._execute_on_target(
                    self._edge.target_id, self._edge.source_id, message,  # Pass full Message
                    shared_state, ctx
                )
            return True
        return False
```

**File: `agent_framework/workflow/_workflow.py`**

```python
# Add import
from ._telemetry import workflow_tracer

class Workflow:
    async def run_streaming(self, message: Any) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow with the given input message."""
        # Reset context for a new run if supported
        self._runner.context.reset_for_new_run(self._shared_state)

        executor = self.get_start_executor()

        # Create initial WorkflowContext with no trace context (starts new trace)
        workflow_context = WorkflowContext(
            executor.id,
            [self.__class__.__name__],
            self._shared_state,
            self._runner.context,
            trace_context=None  # No parent trace context for workflow start
        )

        await executor.execute(message, workflow_context)

        async for event in self._runner.run_until_convergence():
            yield event
```

**File: `agent_framework/workflow/_runner.py`**

```python
# Add import
from ._telemetry import workflow_tracer

class Runner:
    async def _run_iteration(self) -> None:
        """Run one iteration of the workflow superstep."""
        # ... existing logic for message processing ...
        
        # Extract messages and handle sub-workflow requests
        for sub_request in sub_requests:
            # For interceptor execution:
            for executor in self._executors.values():
                if hasattr(executor, "request_interceptors"):
                    for interceptor in executor.request_interceptors:
                        if matched := interceptor.match(sub_request):
                            await executor.execute(
                                sub_request, 
                                WorkflowContext(
                                    executor.id,
                                    ["Runner"], 
                                    self._shared_state,
                                    self._ctx,
                                    trace_context=sub_request.trace_context  # MAINTAIN trace link from sub-workflow
                                )
                            )
                            interceptor_found = True
                            break
            
            # For RequestInfoExecutor:
            if not interceptor_found and (request_info_executor := self._find_request_info_executor()):
                workflow_ctx = WorkflowContext(
                    request_info_executor.id,
                    ["Runner"],
                    self._shared_state,
                    self._ctx,
                    trace_context=sub_request.trace_context  # MAINTAIN trace link from sub-workflow
                )
                await request_info_executor.execute(sub_request, workflow_ctx)
```

**Important Note**: Sub-workflow requests need to carry trace context. Update the sub-workflow request structure:

```python
# In the sub-workflow system, ensure requests carry trace context
@dataclass
class SubWorkflowRequest:
    data: Any
    sub_workflow_id: str
    request_id: str
    # NEW: Trace context from the sub-workflow's publishing span
    trace_context: dict[str, str] | None = None
```

### Step 7: Configuration and Testing

#### Environment Configuration

```bash
# Enable workflow tracing
export AGENT_FRAMEWORK_ENABLE_WORKFLOW_TRACING=true

# OpenTelemetry configuration (optional)
export OTEL_SERVICE_NAME=agent-framework-workflow
export OTEL_TRACES_EXPORTER=console  # For testing
```

#### Testing the Implementation

```python
# test_workflow_tracing.py
import pytest
from unittest.mock import patch, MagicMock
from agent_framework.workflow._telemetry import workflow_tracer

@pytest.fixture
def enable_tracing():
    with patch.object(workflow_tracer, 'enabled', True):
        yield

def test_workflow_span_creation(enable_tracing):
    """Test that workflow spans are created correctly."""
    with patch.object(workflow_tracer.tracer, 'start_as_current_span') as mock_span:
        mock_context_manager = MagicMock()
        mock_span.return_value = mock_context_manager
        
        with workflow_tracer.create_workflow_span("test-workflow-id"):
            pass
        
        # Verify span was created with correct attributes
        mock_span.assert_called_once_with(
            "workflow.run",
            kind=SpanKind.INTERNAL,
            attributes={"workflow.id": "test-workflow-id"}
        )

def test_trace_context_propagation():
    """Test that trace context is properly injected and extracted."""
    from agent_framework.workflow._runner_context import Message
    from opentelemetry.propagate import inject, extract
    
    # Create test message with trace context
    trace_context = {"traceparent": "test-trace-parent"}
    message = Message(
        data="test data",
        source_id="source",
        trace_context=trace_context
    )
    
    # Test extraction
    extracted_context = extract(message.trace_context)
    assert extracted_context is not None

def test_disabled_tracing():
    """Test that no spans are created when tracing is disabled."""
    with patch.object(workflow_tracer, 'enabled', False):
        span = workflow_tracer.create_workflow_span("test-id")
        # Should return nullcontext when disabled
        assert span.__class__.__name__ == 'nullcontext'
```

## Summary

This implementation provides comprehensive workflow tracing with minimal performance impact. The key components work together as follows:

1. **WorkflowTracer** creates spans with proper OpenTelemetry semantics
2. **Message class extension** carries trace context across executor boundaries  
3. **Context propagation** uses standard OpenTelemetry inject/extract functions
4. **EdgeRunner integration** links spans across message routing

### Implementation Checklist

- [ ] Create `_telemetry.py` module with WorkflowTracer class
- [ ] Extend Message class with optional trace context fields
- [ ] Update Runner.run_until_convergence() for workflow spans
- [ ] Update Executor.execute() for processing spans with trace context from WorkflowContext
- [ ] Update WorkflowContext constructor to accept trace context parameter
- [ ] Update WorkflowContext.send_message() for publishing spans
- [ ] Update EdgeRunner._execute_on_target() to pass trace context to WorkflowContext
- [ ] Update Workflow.run_streaming() to pass trace_context=None for new workflows
- [ ] Update Runner._run_iteration() to pass sub-workflow trace context to interceptors and RequestInfo
- [ ] **CRITICAL**: Ensure SubWorkflowRequest carries trace context from publishing spans
- [ ] Update all EdgeRunner subclasses to pass full Message objects
- [ ] Add tests for span creation and context propagation
- [ ] Set AGENT_FRAMEWORK_ENABLE_WORKFLOW_TRACING=true to enable

### Performance Impact

- **Disabled**: Zero overhead when `AGENT_FRAMEWORK_ENABLE_WORKFLOW_TRACING=false`
- **Enabled**: Minimal overhead - only span creation and context propagation
- **Memory**: Small additional memory for trace context headers in messages

### 6. Advanced Features

#### Sampling Strategy
- **Default**: Use OTel's default sampling (usually trace-based)
- **High-volume workflows**: Implement rate-based sampling
- **Debug mode**: 100% sampling for troubleshooting

#### Performance Considerations
- **Lazy span creation**: Only create spans when tracing is enabled
- **Attribute batching**: Batch span attributes to reduce overhead
- **Async context propagation**: Use async-safe context managers

### 7. Example Trace Structure

```text
Workflow Execution (workflow.run)
├─ Executor Processing (executor.process) [UpperCaseExecutor]
│  ├─ Handler Execution (executor.handler.to_upper_case)
│  └─ Message Publishing (message.publish) → ReverseTextExecutor
│     
└─ Executor Processing (executor.process) [ReverseTextExecutor] 
   ├─ Handler Execution (executor.handler.reverse_text)
   └─ Workflow Completion Event
```

### 8. Integration Points

#### Existing Event System
- Correlate spans with existing `WorkflowEvent` instances
- Add trace IDs to events for log correlation
- Preserve existing event semantics

#### Error Handling
- Set span status to `ERROR` on exceptions
- Capture exception details in span attributes
- Maintain span hierarchy even during errors

#### Checkpointing
- Include trace context in checkpoint data
- Resume trace context when restoring from checkpoints
- Handle trace context gaps gracefully

### 9. Benefits

1. **End-to-End Visibility**: Complete trace of message flows across executors
2. **Performance Analysis**: Identify bottlenecks in workflow execution
3. **Debugging Support**: Detailed execution traces for troubleshooting
4. **Monitoring Integration**: Standard OTel format works with all APM tools
5. **Distributed Tracing**: Works across service boundaries for complex deployments

### 10. Future Enhancements

1. **Metrics Integration**: Add OTel metrics for throughput, latency, error rates
2. **Log Correlation**: Automatic trace ID injection into logs
3. **Custom Samplers**: Workflow-specific sampling strategies
4. **Baggage Support**: Carry workflow metadata across span boundaries
5. **GraphQL Integration**: Trace GraphQL query execution within workflows

## Implementation Phases

### Phase 1: Core Instrumentation
- Basic workflow and executor span creation
- Message context propagation
- Span linking between processing and publishing

### Phase 2: Advanced Features  
- Sub-workflow tracing
- Request/response correlation
- Checkpoint integration

### Phase 3: Optimization & Monitoring

- Performance tuning
- Advanced sampling strategies  
- Metrics integration

## Design Summary

This design provides comprehensive tracing coverage while following OpenTelemetry best practices and maintaining compatibility with the existing workflow system architecture.

### Key Design Decisions

#### 1. **Option A: Extend Message Class** ✅ **Chosen**
- **Rationale**: Explicit trace context propagation that works in both local and future distributed environments
- **Trade-offs**: Requires minimal changes to Message class vs. more complex context variable approach
- **Future-proofing**: Ready for distributed execution with no additional architectural changes

#### 2. **Separate `_telemetry.py` Module** ✅ **Chosen** 
- **Rationale**: Clean separation of tracing concerns from core workflow logic
- **Benefits**: Easy to disable/mock for testing, no coupling with main telemetry system
- **Configuration**: `AGENT_FRAMEWORK_ENABLE_WORKFLOW_TRACING=true`

#### 3. **Message-Level Tracing Granularity** ✅ **Chosen**
- **Processing Spans**: `executor.process` (SpanKind.CONSUMER) for message consumption
- **Publishing Spans**: `message.publish` (SpanKind.PRODUCER) for message production
- **Workflow Spans**: `workflow.run` (SpanKind.INTERNAL) for overall execution
- **Proper Linking**: Publishing spans link to processing spans via trace context

### Implementation Phases

**Phase 1: Local Tracing** (Initial Implementation)
- Extend Message class with optional trace context fields
- Implement WorkflowTracer and span creation
- Add trace context injection/extraction in WorkflowContext and EdgeRunner

**Phase 2: Enhanced Features**
- Sub-workflow tracing with proper parent-child relationships
- Checkpoint integration to preserve trace context across resumptions
- Performance optimizations and sampling strategies

**Phase 3: Distributed Ready** (Future)
- Network transport serialization (already designed in)
- Cross-service span linking (already supported via W3C Trace Context)
- Service mesh integration and advanced distributed tracing features

This architecture ensures comprehensive observability for workflow execution while maintaining clean abstractions and preparing for future distributed deployment scenarios.