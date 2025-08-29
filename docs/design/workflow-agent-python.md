# Python WorkflowAgent Implementation Design

## Overview

This document outlines the design for porting the .NET `WorkflowHostAgent` to Python as `WorkflowAgent`. The Python implementation will enable workflows to participate in the agent ecosystem by implementing the `AIAgent` protocol, allowing seamless integration with orchestration and other agent-based systems.

## Background

### .NET WorkflowHostAgent Analysis

The .NET `WorkflowHostAgent` provides the following key capabilities:

1. **AIAgent Protocol Implementation**: Implements both `RunAsync()` and `RunStreamingAsync()` methods
2. **Workflow Integration**: Wraps a `Workflow<List<ChatMessage>>` instance 
3. **State Management**: Tracks running workflows using `_runningWorkflows` dictionary with unique run IDs
4. **Event Translation**: Converts workflow events to `AgentRunResponseUpdate`s:
   - `AgentRunUpdateEvent` → direct pass-through
   - `RequestInfoEvent` → converts to `FunctionCallContent`
5. **Thread Management**: Uses custom `WorkflowThread` that extends `AgentThread`

### Python Workflow System Analysis 

The Python workflow system has these key components:

- **Workflow**: Core workflow execution engine with `run_streaming()` method
- **Events**: Rich event system including `AgentRunEvent`, `AgentRunStreamingEvent`, `RequestInfoEvent`
- **AIAgent Protocol**: Uses `run()` and `run_streaming()` methods (async generators)
- **AgentExecutor**: Existing wrapper that allows agents to run within workflows

## Design

### Core Architecture

```python
class WorkflowAgent(AgentBase):
    """Python implementation of WorkflowHostAgent that wraps workflows as AIAgents."""
    
    def __init__(
        self,
        workflow: Workflow[list[ChatMessage]],
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ):
        # Initialize with workflow and generate unique run IDs
        
    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        # Collect all streaming updates and merge into single response
        
    def run_streaming(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        # Stream workflow events as AgentRunResponseUpdates
```

### Key Design Decisions

#### 1. Thread Management

**Problem**: Python workflows don't have an equivalent to .NET's `WorkflowThread`

**Solution**: Use a custom thread class that manages workflow state:

```python
class WorkflowAgentThread(AgentThread):
    """Custom thread for workflow agents that tracks run state."""
    
    def __init__(self, workflow_id: str, run_id: str):
        super().__init__()
        self.workflow_id = workflow_id
        self.run_id = run_id
        self._message_bookmark: int = 0  # Track processed messages
```

#### 2. State Management

**Problem**: Managing multiple concurrent workflow runs per agent instance

**Solution**: Use a run ID-based tracking system:

```python
class WorkflowAgent:
    def __init__(self, workflow: Workflow[list[ChatMessage]], ...):
        self._workflow = workflow
        self._active_runs: dict[str, Any] = {}  # Track running workflows by run_id
        
    def _generate_run_id(self) -> str:
        """Generate unique run ID for this workflow execution."""
        return f"{self.id}_{uuid.uuid4().hex[:8]}"
```

#### 3. Event Translation

**Problem**: Convert Python workflow events to AIAgent protocol events

**Solution**: Event mapping with helper functions:

```python
async def _convert_workflow_event_to_agent_update(
    self, event: WorkflowEvent, thread: WorkflowAgentThread
) -> AgentRunResponseUpdate | None:
    """Convert workflow events to agent updates."""
    
    match event:
        case AgentRunStreamingEvent(executor_id=executor_id, data=update):
            # Direct pass-through of agent streaming events
            return update
            
        case AgentRunEvent(executor_id=executor_id, data=response):
            # Convert completed agent response to update
            if response.messages:
                return AgentRunResponseUpdate(
                    contents=[msg.content for msg in response.messages],
                    role=ChatRole.ASSISTANT,
                    # ... other fields
                )
                
        case RequestInfoEvent(request_id=request_id, ...):
            # Convert to function call content
            return AgentRunResponseUpdate(
                contents=[self._request_info_to_function_call(event)],
                role=ChatRole.ASSISTANT,
                # ... other fields
            )
            
    return None
```

#### 4. Message Flow Integration

**Problem**: Workflows expect `list[ChatMessage]` as input, but threads maintain message history

**Solution**: Bookmark-based message processing:

```python
async def _prepare_workflow_messages(
    self, input_messages: list[ChatMessage], thread: WorkflowAgentThread
) -> list[ChatMessage]:
    """Prepare messages for workflow execution using bookmark system."""
    
    # Add input messages to thread
    if input_messages:
        await thread.add_messages(input_messages)
    
    # Get messages from bookmark position (unprocessed messages)
    all_messages = await thread.list_messages() or []
    new_messages = all_messages[thread._message_bookmark:]
    
    return new_messages
```

### Implementation Plan

#### Phase 1: Core Implementation

1. **Create `_agent.py`** with basic `WorkflowAgent` class
2. **Implement `WorkflowAgentThread`** for state management  
3. **Add basic `run()` method** that collects streaming results
4. **Add `run_streaming()` method** with event conversion

#### Phase 2: Event Translation

1. **Implement event conversion logic** for all relevant workflow event types
2. **Add `RequestInfoEvent` to function call conversion**
3. **Test event streaming with various workflow patterns**

#### Phase 3: Advanced Features

1. **Add workflow checkpointing support** if needed for long-running workflows
2. **Implement workflow cancellation** through cancellation tokens
3. **Add comprehensive error handling and logging**

### Usage Examples

#### Basic Usage

```python
from agent_framework_workflow import Workflow, WorkflowAgent

# Create workflow (example)
workflow = Workflow(...)

# Wrap as agent
agent = WorkflowAgent(workflow, name="MyWorkflowAgent")

# Use like any other agent
response = await agent.run("Hello workflow!")

# Or stream responses  
async for update in agent.run_streaming("Process this data"):
    print(f"Update: {update}")
```

#### Integration with Orchestration

```python
from agent_framework.orchestration import SequentialOrchestration

# Create multiple agents including workflow agent
workflow_agent = WorkflowAgent(my_workflow)
chat_agent = ChatClientAgent(...)

# Use in orchestration
orchestration = SequentialOrchestration([workflow_agent, chat_agent])
result = await orchestration.run("Complex task requiring workflow")
```

## Technical Considerations

### Performance

- **Streaming Efficiency**: Python async generators provide efficient streaming
- **Memory Usage**: Workflow state is managed per run, allowing concurrent executions
- **Event Processing**: Minimal overhead for event type conversion

### Error Handling

- **Workflow Errors**: Propagate workflow exceptions as `AgentExecutionException`
- **Type Mismatches**: Validate workflow input/output types at runtime
- **Cancellation**: Support proper cleanup of workflow resources

### Testing Strategy

1. **Unit Tests**: Test event conversion logic independently
2. **Integration Tests**: Test with real workflows and agent orchestration  
3. **Performance Tests**: Validate streaming performance with large workflows
4. **Compatibility Tests**: Ensure compatibility with existing agent infrastructure

## Alternative Approaches Considered

### 1. Extend AgentExecutor Instead

**Pros**: Reuse existing workflow integration logic
**Cons**: AgentExecutor is designed to wrap agents, not expose workflows as agents

### 2. Direct Workflow Protocol Implementation  

**Pros**: Simpler, direct implementation
**Cons**: Bypasses agent framework benefits like telemetry, error handling, thread management

### 3. Async Wrapper Pattern

**Pros**: Clean separation of concerns  
**Cons**: Added complexity, potential for deadlocks with async workflows

## Conclusion

The proposed `WorkflowAgent` design provides a clean, efficient way to expose Python workflows as AIAgents. By following the established patterns from the .NET implementation while adapting to Python's async/streaming model, this implementation will enable seamless integration of workflows into the broader agent ecosystem.

The phased implementation approach allows for iterative development and testing, ensuring robustness and compatibility with existing systems.