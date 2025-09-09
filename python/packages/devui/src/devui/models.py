# Copyright (c) Microsoft. All rights reserved.

"""Pydantic models for the Agent Framework Debug UI backend."""

from typing import Any, Dict, List, Literal, Optional, Union, TYPE_CHECKING
from pydantic import BaseModel, Field

# Import required types with proper type handling
if TYPE_CHECKING:
    # For type checking, import the real types
    from agent_framework import AgentRunResponseUpdate
    from agent_framework_workflow._events import WorkflowEvent
else:
    # At runtime, try to import but fallback gracefully
    try:
        from agent_framework import AgentRunResponseUpdate
    except ImportError:
        AgentRunResponseUpdate = Dict[str, Any]
        
    try:
        from agent_framework_workflow._events import WorkflowEvent
    except ImportError:
        WorkflowEvent = Dict[str, Any]

class AgentInfo(BaseModel):
    """Information about a discovered agent."""
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    type: Literal["agent"] = "agent"
    source: Literal["directory", "in_memory"]
    tools: List[str] = Field(default_factory=list)
    has_env: bool = False
    module_path: Optional[str] = None

class WorkflowInfo(BaseModel):
    """Information about a discovered workflow."""
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    type: Literal["workflow"] = "workflow"
    source: Literal["directory", "in_memory"]
    executors: List[str] = Field(default_factory=list)
    has_env: bool = False
    module_path: Optional[str] = None
    
    # Workflow structure
    workflow_dump: Dict[str, Any]
    mermaid_diagram: Optional[str] = None
    
    # Input specification
    input_schema: Dict[str, Any]  # JSON Schema for workflow input
    input_type_name: str  # Human-readable input type name
    start_executor_id: str

class RunAgentRequest(BaseModel):
    """Request to execute an agent.
    
    Supports both simple string messages and rich message arrays with attachments.
    """
    messages: Union[str, List[Dict[str, Any]]]
    thread_id: Optional[str] = None
    options: Optional[Dict[str, Any]] = None

class RunWorkflowRequest(BaseModel):
    """Request to execute a workflow."""
    input_data: Dict[str, Any]  # Structured input data matching the workflow's schema

class CreateThreadRequest(BaseModel):
    """Request to create a new thread."""
    pass  # No additional fields needed

class ThreadInfo(BaseModel):
    """Information about a conversation thread."""
    id: str
    agent_id: str
    created_at: str
    message_count: int

class SessionInfo(BaseModel):
    """Information about a debug session."""
    thread_id: str
    agent_id: str
    created_at: str
    messages: List[Dict[str, Any]]
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TraceSpan(BaseModel):
    """Real-time trace span data for streaming."""
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    status: str = "OK"
    raw_span: Optional[Dict[str, Any]] = None  # Complete OpenTelemetry span data

class DebugStreamEvent(BaseModel):
    """Wrapper for streaming events with debug metadata."""
    model_config = {"arbitrary_types_allowed": True}
    
    type: Literal["agent_run_update", "workflow_event", "workflow_structure", "completion", "error", "debug_trace", "trace_span"]
    update: Optional[AgentRunResponseUpdate] = None  # Properly typed AgentRunResponseUpdate
    event: Optional[Union[WorkflowEvent, Dict[str, Any]]] = None   # Accept WorkflowEvent instance or serialized dict
    trace_span: Optional[TraceSpan] = None  # Real-time trace span
    # Workflow structure data (minimal)
    workflow_dump: Optional[Dict[str, Any]] = None
    mermaid_diagram: Optional[str] = None
    timestamp: str
    debug_metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    thread_id: Optional[str] = None  # Thread ID for session tracking

class HealthResponse(BaseModel):
    """Health check response."""
    status: Literal["healthy"]
    agents_dir: Optional[str] = None
    version: str = "1.0.0"