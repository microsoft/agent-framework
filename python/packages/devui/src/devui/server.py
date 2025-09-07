# Copyright (c) Microsoft. All rights reserved.

"""FastAPI server for Agent Framework debug UI."""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

if TYPE_CHECKING:
    from agent_framework import AgentProtocol, AgentThread
    from agent_framework.workflow import Workflow

from .models import (
    AgentInfo,
    WorkflowInfo,
    CreateThreadRequest, 
    DebugStreamEvent,
    HealthResponse,
    RunAgentRequest,
    SessionInfo,
    ThreadInfo
)
from .registry import AgentRegistry
from .sessions import SessionManager
from .tracing import TracingManager
from .execution import ExecutionEngine

logger = logging.getLogger(__name__)

class AgentFrameworkDebugServer:
    """FastAPI server for debugging Agent Framework agents and workflows.
    
    Provides a minimal API layer over Agent Framework's native capabilities,
    following the principle of "just another view to see or test agents".
    """
    
    def __init__(
        self,
        agents_dir: Optional[str] = None,
        enable_cors: bool = True,
        cors_origins: Optional[List[str]] = None
    ) -> None:
        """Initialize the debug server.
        
        Args:
            agents_dir: Optional directory to scan for agents
            enable_cors: Whether to enable CORS middleware
            cors_origins: List of allowed CORS origins
        """
        from .registry import AgentRegistry
        from .tracing import TracingManager
        
        self.registry = AgentRegistry(agents_dir)
        self.session_manager = SessionManager()
        self.execution_engine = ExecutionEngine()
        self.enable_cors = enable_cors
        self.cors_origins = cors_origins or ["*"]
        self.tracing_manager = TracingManager()
        
        # Thread ID mapping for in-memory threads
        self._thread_ids: Dict[int, str] = {}
        
    def _dummy_trace_callback(self, event: DebugStreamEvent) -> None:
        """Dummy callback for initial tracing setup."""
        logger.debug(f"Received trace event during initialization: {event.type}")

    def _get_thread_id(self, thread: 'AgentThread') -> str:
        """Get thread ID from AgentThread, generating one if needed."""
        # Use service_thread_id if available (for service-managed threads)
        if thread.service_thread_id:
            return thread.service_thread_id
        
        # For in-memory threads, generate a unique ID based on object identity
        thread_obj_id = id(thread)
        if thread_obj_id not in self._thread_ids:
            self._thread_ids[thread_obj_id] = str(uuid.uuid4())
        
        return self._thread_ids[thread_obj_id]

    def create_app(self) -> FastAPI:
        """Create the FastAPI application with all endpoints."""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info("Starting Agent Framework Debug Server")
            # Set up one-time tracing initialization
            self.tracing_manager.setup_streaming_tracing(self._dummy_trace_callback)
            yield
            # Shutdown  
            logger.info("Shutting down Agent Framework Debug Server")
            await self.session_manager.cleanup()
            
        app = FastAPI(
            title="Agent Framework Debug Server",
            description="Lightweight debug API for Agent Framework agents and workflows",
            version="1.0.0",
            lifespan=lifespan
        )
        
        if self.enable_cors:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self.cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            
        self._register_routes(app)
        self._mount_ui(app)
        return app
    
    def register_agent(self, agent_id: str, agent: 'AgentProtocol') -> None:
        """Register an in-memory agent.
        
        Args:
            agent_id: Unique identifier for the agent
            agent: Agent Framework agent instance
        """
        self.registry.register_agent(agent_id, agent)
    
    def register_workflow(self, workflow_id: str, workflow: 'Workflow') -> None:
        """Register an in-memory workflow.
        
        Args:
            workflow_id: Unique identifier for the workflow
            workflow: Agent Framework workflow instance
        """
        self.registry.register_workflow(workflow_id, workflow)
    
    def _mount_ui(self, app: FastAPI) -> None:
        """Mount the built UI as static files."""
        from pathlib import Path
        
        # Get the directory where this module is located
        module_dir = Path(__file__).parent
        ui_dir = module_dir / "ui"
        
        # Only mount if UI directory exists
        if ui_dir.exists() and ui_dir.is_dir():
            app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")
        
    def _register_routes(self, app: FastAPI) -> None:
        """Register all API routes."""
        
        @app.get("/health", response_model=HealthResponse)
        async def health_check():
            """Health check endpoint."""
            return HealthResponse(
                status="healthy",
                agents_dir=str(self.registry.directory_scanner.agents_dir) 
                    if self.registry.directory_scanner else None
            )
            
        @app.get("/agents", response_model=List[AgentInfo])
        async def list_agents():
            """List all available agents."""
            try:
                agents = self.registry.list_agents()
                return agents
            except Exception as e:
                logger.error(f"Error listing agents: {e}")
                raise HTTPException(status_code=500, detail=f"Agent listing failed: {str(e)}")
                
        @app.get("/workflows", response_model=List[WorkflowInfo])
        async def list_workflows():
            """List all available workflows."""
            try:
                workflows = self.registry.list_workflows()
                return workflows
            except Exception as e:
                logger.error(f"Error listing workflows: {e}")
                raise HTTPException(status_code=500, detail=f"Workflow listing failed: {str(e)}")
                
        @app.get("/agents/{agent_id}/info", response_model=AgentInfo)
        async def get_agent_info(agent_id: str):
            """Get detailed information about a specific agent."""
            agent = self.registry.get_agent(agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
            agents = self.registry.list_agents()
            agent_info = next((a for a in agents if a.id == agent_id), None)
            if not agent_info:
                raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
            return agent_info
            
        @app.get("/workflows/{workflow_id}/info", response_model=WorkflowInfo)
        async def get_workflow_info(workflow_id: str):
            """Get detailed information about a specific workflow including input schema."""
            workflow = self.registry.get_workflow(workflow_id)
            if not workflow:
                raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
            
            workflows = self.registry.list_workflows()
            workflow_info = next((w for w in workflows if w.id == workflow_id), None)
            if not workflow_info:
                raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
            
            return workflow_info
            
        @app.post("/agents/{agent_id}/threads", response_model=ThreadInfo)
        async def create_thread(agent_id: str, request: CreateThreadRequest):
            """Create a new conversation thread for an agent."""
            # Get agent object
            agent_obj = self.registry.get_agent(agent_id)
            if not agent_obj:
                raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
                
            try:
                # Create thread using Agent Framework's native threading
                thread: 'AgentThread' = agent_obj.get_new_thread()
                
                # Store in session manager
                thread_id = self._get_thread_id(thread)
                session_info = self.session_manager.create_session(
                    agent_id=agent_id,
                    thread_id=thread_id,
                    thread=thread
                )
                
                return ThreadInfo(
                    id=session_info.thread_id,
                    agent_id=agent_id,
                    created_at=session_info.created_at,
                    message_count=0
                )
                
            except Exception as e:
                logger.error(f"Error creating thread for {agent_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Thread creation failed: {str(e)}")
            
        @app.get("/agents/{agent_id}/threads", response_model=List[ThreadInfo])
        async def list_threads(agent_id: str):
            """List all threads for an agent."""
            sessions = self.session_manager.list_sessions(agent_id)
            return [
                ThreadInfo(
                    id=session.thread_id,
                    agent_id=session.agent_id,
                    created_at=session.created_at,
                    message_count=len(session.messages)
                )
                for session in sessions
            ]
            
        @app.post("/agents/{agent_id}/run")
        async def run_agent(agent_id: str, request: RunAgentRequest):
            """Execute an agent (non-streaming)."""
            agent_obj = self.registry.get_agent(agent_id)
            if not agent_obj:
                raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
                
            try:
                # Get or create thread
                thread = None
                if request.thread_id:
                    thread = self.session_manager.get_thread(request.thread_id)
                    
                if thread is None:
                    thread = agent_obj.get_new_thread()
                    thread_id = self._get_thread_id(thread)
                    self.session_manager.create_session(agent_id, thread_id, thread)
                
                # Execute agent using framework's native method
                result = await agent_obj.run(request.message, thread=thread)
                
                # Store result in session
                thread_id = self._get_thread_id(thread)
                self.session_manager.add_message(thread_id, {
                    "user_message": request.message,
                    "agent_response": [msg.model_dump() if hasattr(msg, 'model_dump') else str(msg) 
                                     for msg in result.messages],
                    "timestamp": datetime.now().isoformat()
                })
                
                return {
                    "thread_id": thread_id,
                    "result": [msg.model_dump() if hasattr(msg, 'model_dump') else str(msg) 
                              for msg in result.messages],
                    "message_count": len(result.messages)
                }
                
            except Exception as e:
                logger.error(f"Error running agent {agent_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")
                
        @app.post("/workflows/{workflow_id}/run")
        async def run_workflow(workflow_id: str, request: RunAgentRequest):
            """Execute a workflow (non-streaming)."""
            workflow_obj = self.registry.get_workflow(workflow_id)
            if not workflow_obj:
                raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
                
            try:
                # Collect all events from streaming execution
                events = []
                async for event in self.execution_engine.execute_workflow_streaming(
                    workflow=workflow_obj,
                    input_data=request.message,
                    capture_traces=request.options.get('capture_traces', True) if request.options else True,
                    tracing_manager=self.tracing_manager  # Pass tracing manager for real-time trace streaming
                ):
                    events.append(event)
                
                # Return the final result
                completion_events = [e for e in events if e.type == "completion"]
                if completion_events:
                    return {
                        "result": "Workflow completed successfully",
                        "events": len(events),
                        "message_count": 1
                    }
                else:
                    return {
                        "result": "Workflow executed with events",
                        "events": len(events),
                        "message_count": len(events)
                    }
                
            except Exception as e:
                logger.error(f"Error running workflow {workflow_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")
                
        @app.post("/agents/{agent_id}/run/stream")
        async def run_agent_streaming(agent_id: str, request: RunAgentRequest):
            """Execute an agent with streaming response (SSE)."""
           
            agent_obj = self.registry.get_agent(agent_id)
            if not agent_obj:
                raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
                
            async def event_generator():
                try:
                    # Get or create thread
                    thread = None
                    if request.thread_id:
                        thread = self.session_manager.get_thread(request.thread_id)
                      
                     
                    if thread is None: 
                        thread = agent_obj.get_new_thread()
                        thread_id = self._get_thread_id(thread)
                        self.session_manager.create_session(agent_id, thread_id, thread)
                    else:
                        thread_id = self._get_thread_id(thread)
                    
                    # Execute with streaming
                    async for event in self.execution_engine.execute_agent_streaming(
                        agent=agent_obj,
                        message=request.message, 
                        thread=thread,
                        thread_id=thread_id,  # Pass thread_id to execution engine
                        capture_traces=request.options.get('capture_traces', True) if request.options else True,
                        tracing_manager=self.tracing_manager  # Pass tracing manager for real-time trace streaming
                    ):
                        yield f"data: {event.model_dump_json()}\n\n"
                        
                except Exception as e:
                    logger.error(f"Error in streaming execution for {agent_id}: {e}")
                    error_event = DebugStreamEvent(
                        type="error",
                        error=str(e),
                        timestamp=datetime.now().isoformat()
                    )
                    yield f"data: {error_event.model_dump_json()}\n\n"
                    
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*"
                }
            )
            
        @app.post("/workflows/{workflow_id}/run/stream")
        async def run_workflow_streaming(workflow_id: str, request: RunAgentRequest):
            """Execute a workflow with streaming response (SSE)."""
            workflow_obj = self.registry.get_workflow(workflow_id)
            if not workflow_obj:
                raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
                
            async def event_generator():
                try:
                    # Execute workflow
                    async for event in self.execution_engine.execute_workflow_streaming(
                        workflow=workflow_obj,
                        input_data=request.message,
                        capture_traces=request.options.get('capture_traces', True) if request.options else True,
                        tracing_manager=self.tracing_manager  # Pass tracing manager for real-time trace streaming
                    ):
                        yield f"data: {event.model_dump_json()}\n\n"
                        
                except Exception as e:
                    logger.error(f"Error in streaming execution for {workflow_id}: {e}")
                    error_event = DebugStreamEvent(
                        type="error",
                        error=str(e),
                        timestamp=datetime.now().isoformat()
                    )
                    yield f"data: {error_event.model_dump_json()}\n\n"
                    
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*"
                }
            )
            
        @app.get("/sessions/{session_id}", response_model=SessionInfo)
        async def get_session(session_id: str):
            """Get session details and message history."""
            session = self.session_manager.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
            return session
            
        @app.get("/sessions/{session_id}/traces")
        async def get_session_traces(session_id: str):
            """Get OpenTelemetry traces for a session."""
            traces = self.tracing_manager.get_session_traces(session_id)
            return {"session_id": session_id, "traces": traces}
            
        @app.delete("/cache")
        async def clear_cache():
            """Clear agent cache for hot reloading.""" 
            self.registry.clear_cache()
            return {"status": "cache_cleared"}

def create_debug_server(
    agents_dir: Optional[str] = None,
    **kwargs: Any
) -> FastAPI:
    """Create FastAPI app for embedding in larger applications.
    
    Args:
        agents_dir: Optional directory to scan for agents
        **kwargs: Additional arguments passed to AgentFrameworkDebugServer
        
    Returns:
        FastAPI application instance
    """
    server = AgentFrameworkDebugServer(agents_dir=agents_dir, **kwargs)
    return server.create_app()