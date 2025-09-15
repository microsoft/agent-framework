# Copyright (c) Microsoft. All rights reserved.

"""Execution engine with simplified tracing support."""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, AsyncIterator, Dict, List, Optional, Union

from opentelemetry import trace

from .executors._base import FrameworkExecutor  # Import the correct executor base class
from .models import AgentFrameworkRequest, OpenAIResponse, ResponseStreamEvent, ResponseTraceEvent

# Type aliases for better readability
SessionData = Dict[str, Any]
RequestRecord = Dict[str, Any]
SessionSummary = Dict[str, Any]
TracingAttributes = Dict[str, Union[str, int, float, bool]]

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Execution engine with simplified tracing and session management."""

    def __init__(self, tracing_enabled: bool = False, otlp_endpoint: Optional[str] = None) -> None:
        """Initialize the execution engine.
        
        Args:
            tracing_enabled: Whether to enable tracing
            otlp_endpoint: OTLP endpoint for tracing
        """
        self.tracing_enabled = tracing_enabled
        self.otlp_endpoint = otlp_endpoint
        self.sessions: Dict[str, SessionData] = {}

        # Setup tracing
        self._setup_tracing()
        self.tracer: trace.Tracer = trace.get_tracer(__name__)

    def _setup_tracing(self) -> None:
        """Setup OpenTelemetry tracing via Agent Framework."""
        if not self.tracing_enabled:
            return

        # Set Agent Framework environment variables
        import os
        os.environ["AGENT_FRAMEWORK_ENABLE_OTEL"] = "1"
        if self.otlp_endpoint:
            os.environ["AGENT_FRAMEWORK_OTLP_ENDPOINT"] = self.otlp_endpoint
        else:
            os.environ["AGENT_FRAMEWORK_OTLP_ENDPOINT"] = "http://localhost:4317"  # Dummy
        logger.info("Enabled Agent Framework automatic telemetry")

    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new execution session.
        
        Args:
            session_id: Optional session ID, if not provided a new one is generated
            
        Returns:
            Session ID
        """
        if not session_id:
            session_id = str(uuid.uuid4())

        self.sessions[session_id] = {
            "id": session_id,
            "created_at": datetime.now(),
            "requests": [],
            "context": {},
            "active": True
        }

        logger.debug(f"Created session: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get session information.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session data or None if not found
        """
        return self.sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
        """Close and cleanup a session.
        
        Args:
            session_id: Session ID to close
        """
        if session_id in self.sessions:
            self.sessions[session_id]["active"] = False
            logger.debug(f"Closed session: {session_id}")

    @asynccontextmanager
    async def trace_execution(
        self,
        operation_name: str,
        **attributes: Union[str, int, float, bool]
    ) -> AsyncIterator[Optional[trace.Span]]:
        """Context manager for tracing execution with automatic error handling.
        
        Args:
            operation_name: Name of the operation being traced
            **attributes: Additional attributes to add to the span
            
        Yields:
            Span object if tracing is enabled, None otherwise
        """
        if not self.tracing_enabled:
            # No tracing, just yield
            yield None
            return

        span = self.tracer.start_span(operation_name)

        try:
            # Add attributes
            for key, value in attributes.items():
                span.set_attribute(key, str(value))

            span.set_attribute("execution.start_time", datetime.now().isoformat())

            yield span

            span.set_attribute("execution.status", "success")

        except Exception as e:
            span.set_attribute("execution.status", "error")
            span.set_attribute("execution.error", str(e))
            span.record_exception(e)
            raise
        finally:
            span.set_attribute("execution.end_time", datetime.now().isoformat())
            span.end()

    async def execute_streaming(
        self,
        executor: FrameworkExecutor,
        entity_id: str,
        request: AgentFrameworkRequest,
        enable_tracing: bool = True
    ) -> AsyncGenerator[Union[ResponseStreamEvent, ResponseTraceEvent], None]:
        """Execute request with streaming and optional tracing.
        
        Args:
            executor: Framework executor instance
            entity_id: ID of the entity being executed
            request: OpenAI request
            enable_tracing: Whether to enable tracing
            
        Yields:
            Stream events from the entity execution
        """
        logger.info(f"🚀 ExecutionEngine.execute_streaming called for entity: {entity_id}")

        # Get or create session
        session_id: Optional[str] = request.extra_body.get("session_id") if request.extra_body else None
        if session_id and session_id not in self.sessions:
            session_id = self.create_session(session_id)
        elif not session_id:
            session_id = self.create_session()

        session: SessionData = self.sessions[session_id]

        # Record request in session
        request_record: RequestRecord = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(),
            "entity_id": entity_id,
            "executor": executor.__class__.__name__,
            "input": request.input,
            "model": request.model,
            "stream": True
        }
        session["requests"].append(request_record)

        operation_name: str = f"{executor.__class__.__name__}.{entity_id}.execute_streaming"

        # Execute with optional tracing
        if enable_tracing:
            async with self.trace_execution(
                operation_name,
                executor=executor.__class__.__name__,
                entity_id=entity_id,
                session_id=session_id,
                request_id=request_record["id"],
                model=request.model,
                stream=True,
                input_length=len(str(request.input)) if request.input else 0
            ) as span:
                start_time: float = time.time()

                try:
                    # Get executor and run entity with streaming
                    async for event in executor.execute_streaming(request):
                        yield event

                except Exception as e:
                    # Log execution error
                    logger.exception(f"Execution error for {request_record['entity_id']}: {e}")

                    # Update session with error
                    request_record["error"] = str(e)
                    request_record["status"] = "error"

                    raise
                finally:
                    # Record execution time
                    execution_time: float = time.time() - start_time
                    request_record["execution_time"] = execution_time
                    request_record["status"] = request_record.get("status", "completed")

                    if span:
                        span.set_attribute("execution.duration_seconds", execution_time)
        else:
            # Execute without tracing
            execution_start_time: float = time.time()
            try:
                async for event in executor.execute_streaming(request):
                    yield event
            except Exception as e:
                logger.exception(f"Execution error for {request_record['entity_id']}: {e}")
                request_record["error"] = str(e)
                request_record["status"] = "error"
                raise
            finally:
                execution_time = time.time() - execution_start_time
                request_record["execution_time"] = execution_time
                request_record["status"] = request_record.get("status", "completed")

    async def execute(
        self,
        executor: FrameworkExecutor,
        entity_id: str,
        request: AgentFrameworkRequest,
        enable_tracing: bool = True
    ) -> OpenAIResponse:
        """Execute request and return complete response (uses streaming underneath).
        
        Args:
            executor: Framework executor instance
            entity_id: ID of the entity being executed
            request: OpenAI request
            enable_tracing: Whether to enable tracing
            
        Returns:
            Complete response object
        """
        # Use execute_streaming and collect all events
        return await executor.execute_sync(request)

    async def get_session_history(self, session_id: str) -> Optional[SessionSummary]:
        """Get session execution history.
        
        Args:
            session_id: Session ID
            
        Returns:
            Session history or None if not found
        """
        session = self.get_session(session_id)
        if not session:
            return None

        return {
            "session_id": session_id,
            "created_at": session["created_at"].isoformat(),
            "active": session["active"],
            "request_count": len(session["requests"]),
            "requests": [
                {
                    "id": req["id"],
                    "timestamp": req["timestamp"].isoformat(),
                    "entity_id": req["entity_id"],
                    "executor": req["executor"],
                    "model": req["model"],
                    "input_length": len(str(req["input"])) if req["input"] else 0,
                    "execution_time": req.get("execution_time"),
                    "status": req.get("status", "unknown")
                }
                for req in session["requests"]
            ]
        }

    def get_active_sessions(self) -> List[SessionSummary]:
        """Get list of active sessions.
        
        Returns:
            List of active session summaries
        """
        active_sessions = []

        for session_id, session in self.sessions.items():
            if session["active"]:
                active_sessions.append({
                    "session_id": session_id,
                    "created_at": session["created_at"].isoformat(),
                    "request_count": len(session["requests"]),
                    "last_activity": (
                        session["requests"][-1]["timestamp"].isoformat()
                        if session["requests"] else session["created_at"].isoformat()
                    )
                })

        return active_sessions

    async def cleanup_old_sessions(self, max_age_hours: int = 24) -> None:
        """Cleanup old sessions to prevent memory leaks.
        
        Args:
            max_age_hours: Maximum age of sessions to keep in hours
        """
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)

        sessions_to_remove = []
        for session_id, session in self.sessions.items():
            if session["created_at"].timestamp() < cutoff_time:
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            del self.sessions[session_id]
            logger.debug(f"Cleaned up old session: {session_id}")

        if sessions_to_remove:
            logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions")
