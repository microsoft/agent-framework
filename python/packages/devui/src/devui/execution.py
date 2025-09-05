# Copyright (c) Microsoft. All rights reserved.

"""Execution engine that wraps Agent Framework's native streaming."""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from agent_framework import AgentProtocol, AgentRunResponseUpdate, AgentThread
    from agent_framework.workflow import Workflow, WorkflowEvent
    from .tracing import TracingManager

from .models import DebugStreamEvent

logger = logging.getLogger(__name__)

class ExecutionEngine:
    """Wraps Agent Framework execution with minimal overhead.
    
    Passes through native framework types with optional debug metadata.
    This ensures zero maintenance burden while preserving all framework capabilities.
    """
    
    def __init__(self) -> None:
        """Initialize the execution engine."""
        pass
    
    async def execute_agent_streaming(
        self, 
        agent: 'AgentProtocol', 
        message: str,
        thread: Optional['AgentThread'] = None,
        thread_id: Optional[str] = None,
        capture_traces: bool = True,
        tracing_manager: Optional['TracingManager'] = None
    ) -> AsyncGenerator[DebugStreamEvent, None]:
        """Execute agent and yield native AgentRunResponseUpdate wrapped in debug envelope.
        
        Args:
            agent: The Agent Framework agent to execute
            message: The message to send to the agent
            thread: Optional conversation thread
            thread_id: Optional thread identifier for session tracking
            capture_traces: Whether to capture debug metadata
            tracing_manager: Optional tracing manager for span streaming
            
        Yields:
            DebugStreamEvent containing native AgentRunResponseUpdate
        """
        # Store trace events to yield alongside regular events
        trace_events = []
        
        # Set up tracing with callback to collect trace events
        if tracing_manager and thread_id and capture_traces:
            def collect_trace_event(trace_event: DebugStreamEvent):
                trace_events.append(trace_event)
            
            tracing_manager.setup_streaming_tracing(collect_trace_event)
            
        try:
            # Create a manual span for agent execution if tracing is enabled
            if tracing_manager and thread_id:
                try:
                    from opentelemetry import trace
                    tracer = trace.get_tracer("devui.execution")
                    
                    # Create a top-level span for this agent execution
                    with tracer.start_as_current_span(
                        f"agent_execution.{getattr(agent, 'name', 'unknown')}",
                        attributes={
                            "thread_id": thread_id,
                            "agent_name": getattr(agent, 'name', 'unknown'),
                            "message": message[:100] + "..." if len(message) > 100 else message
                        }
                    ) as span:
                        span.set_attribute("devui.session_id", thread_id)
                        
                        # Execute agent using framework's native streaming
                        async for update in agent.run_stream(message, thread=thread):
                            # Yield any pending trace events first
                            while trace_events:
                                yield trace_events.pop(0)
                            
                            # Minimal wrapping - preserve native types completely
                            yield DebugStreamEvent(
                                type="agent_run_update",
                                update=update,  # Native AgentRunResponseUpdate - no modification
                                timestamp=self._get_timestamp(),
                                thread_id=thread_id,
                                debug_metadata=self._get_debug_metadata(update) if capture_traces else None
                            )
                except ImportError:
                    logger.debug("OpenTelemetry not available for manual span creation")
                    # Fall back to execution without spans
                    async for update in agent.run_stream(message, thread=thread):
                        # Yield any pending trace events first
                        while trace_events:
                            yield trace_events.pop(0)
                        
                        # Minimal wrapping - preserve native types completely
                        yield DebugStreamEvent(
                            type="agent_run_update",
                            update=update,  # Native AgentRunResponseUpdate - no modification
                            timestamp=self._get_timestamp(),
                            thread_id=thread_id,
                            debug_metadata=self._get_debug_metadata(update) if capture_traces else None
                        )
            else:
                # Execute without tracing
                async for update in agent.run_stream(message, thread=thread):
                    # Yield any pending trace events first
                    while trace_events:
                        yield trace_events.pop(0)
                    
                    # Minimal wrapping - preserve native types completely
                    yield DebugStreamEvent(
                        type="agent_run_update",
                        update=update,  # Native AgentRunResponseUpdate - no modification
                        timestamp=self._get_timestamp(),
                        thread_id=thread_id,
                        debug_metadata=self._get_debug_metadata(update) if capture_traces else None
                    )
                
            # Yield any remaining trace events
            while trace_events:
                yield trace_events.pop(0)
                
            # Signal completion
            yield DebugStreamEvent(
                type="completion",
                timestamp=self._get_timestamp(),
                thread_id=thread_id
            )
            
        except Exception as e:
            logger.error(f"Error executing agent {getattr(agent, 'name', 'unknown')}: {e}")
            yield DebugStreamEvent(
                type="error",
                error=str(e),
                timestamp=self._get_timestamp(),
                thread_id=thread_id
            )
    
    async def execute_workflow_streaming(
        self,
        workflow: 'Workflow',
        input_data: str,
        capture_traces: bool = True,
        tracing_manager: Optional['TracingManager'] = None
    ) -> AsyncGenerator[DebugStreamEvent, None]:
        """Execute workflow and yield native WorkflowEvent wrapped in debug envelope.
        
        Args:
            workflow: The Agent Framework workflow to execute
            input_data: The input data for the workflow
            capture_traces: Whether to capture debug metadata
            tracing_manager: Optional tracing manager for span streaming
            
        Yields:
            DebugStreamEvent containing native WorkflowEvent
        """
        # Store trace events to yield alongside regular events  
        trace_events = []
        
        # Set up tracing with callback to collect trace events
        if tracing_manager and capture_traces:
            def collect_trace_event(trace_event: DebugStreamEvent):
                trace_events.append(trace_event)
            
            tracing_manager.setup_streaming_tracing(collect_trace_event)
            
        try:
            # First, send workflow structure information (minimal - just raw dump)
            try:
                yield DebugStreamEvent(
                    type="workflow_structure",
                    workflow_dump=workflow.model_dump(),
                    timestamp=self._get_timestamp()
                )
            except Exception as e:
                logger.warning(f"Could not generate workflow structure: {e}")
            
            # Execute workflow using framework's native streaming
            async for event in workflow.run_stream(input_data):
                # Yield any pending trace events first
                while trace_events:
                    yield trace_events.pop(0)
                    
                # Minimal wrapping - preserve native types completely
                yield DebugStreamEvent(
                    type="workflow_event",
                    event=self._serialize_workflow_event(event),  # Convert to serializable format
                    timestamp=self._get_timestamp(),
                    debug_metadata=self._get_debug_metadata(event) if capture_traces else None
                )
                
            # Yield any remaining trace events
            while trace_events:
                yield trace_events.pop(0)
                
            # Signal completion
            yield DebugStreamEvent(
                type="completion",
                timestamp=self._get_timestamp()
            )
            
        except Exception as e:
            logger.error(f"Error executing workflow: {e}")
            yield DebugStreamEvent(
                type="error",
                error=str(e),
                timestamp=self._get_timestamp()
            )
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()
    
    def _get_debug_metadata(self, obj: Any) -> Optional[Dict[str, Any]]:
        """Extract debug metadata from framework objects."""
        metadata: Dict[str, Any] = {}
        
        # Add common metadata
        if hasattr(obj, 'message_id'):
            metadata['message_id'] = obj.message_id
        if hasattr(obj, 'response_id'):
            metadata['response_id'] = obj.response_id
        if hasattr(obj, 'role'):
            metadata['role'] = obj.role
            
        # Add timing if available
        if hasattr(obj, 'timestamp'):
            metadata['framework_timestamp'] = obj.timestamp
            
        return metadata if metadata else None
    
    def _serialize_workflow_event(self, event: Any) -> Dict[str, Any]:
        """Convert workflow event to serializable format."""
        event_dict = {
            "type": event.__class__.__name__,
            "data": None
        }
        
        # Add common attributes
        if hasattr(event, 'executor_id'):
            event_dict["executor_id"] = event.executor_id
        if hasattr(event, 'request_id'):
            event_dict["request_id"] = event.request_id
        if hasattr(event, 'source_executor_id'):
            event_dict["source_executor_id"] = event.source_executor_id
        if hasattr(event, 'request_type'):
            event_dict["request_type"] = event.request_type.__name__ if hasattr(event.request_type, '__name__') else str(event.request_type)
            
        # Serialize data based on type
        if hasattr(event, 'data') and event.data is not None:
            try:
                # Try to serialize simple types
                if isinstance(event.data, (str, int, float, bool, list, dict)):
                    event_dict["data"] = event.data
                else:
                    # Convert complex objects to string representation
                    event_dict["data"] = str(event.data)
            except Exception:
                event_dict["data"] = str(event.data)
                
        return event_dict