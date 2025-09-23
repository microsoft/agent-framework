# Copyright (c) Microsoft. All rights reserved.

"""FastAPI server implementation."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ._discovery import EntityDiscovery
from ._executor import AgentFrameworkExecutor
from ._mapper import MessageMapper
from .models import AgentFrameworkRequest, OpenAIError
from .models._discovery_models import DiscoveryResponse, EntityInfo

# Removed ExecutionEngine import - using direct executor approach

logger = logging.getLogger(__name__)


class DevServer:
    """Development Server - OpenAI compatible API server for debugging agents."""

    def __init__(
        self,
        entities_dir: str | None = None,
        port: int = 8080,
        host: str = "127.0.0.1",
        cors_origins: list[str] | None = None,
        ui_enabled: bool = True,
    ) -> None:
        """Initialize the development server.

        Args:
            entities_dir: Directory to scan for entities
            port: Port to run server on
            host: Host to bind server to
            cors_origins: List of allowed CORS origins
            ui_enabled: Whether to enable the UI
        """
        self.entities_dir = entities_dir
        self.port = port
        self.host = host
        self.cors_origins = cors_origins or ["*"]
        self.ui_enabled = ui_enabled
        self.executor: AgentFrameworkExecutor | None = None
        self._app: FastAPI | None = None
        self._pending_entities: list[Any] | None = None

    async def _ensure_executor(self) -> AgentFrameworkExecutor:
        """Ensure executor is initialized."""
        if self.executor is None:
            logger.info("Initializing Agent Framework executor...")

            # Create components directly
            entity_discovery = EntityDiscovery(self.entities_dir)
            message_mapper = MessageMapper()
            self.executor = AgentFrameworkExecutor(entity_discovery, message_mapper)

            # Discover entities from directory
            discovered_entities = await self.executor.discover_entities()
            logger.info(f"Discovered {len(discovered_entities)} entities from directory")

            # Register any pending in-memory entities
            if self._pending_entities:
                discovery = self.executor.entity_discovery
                for entity in self._pending_entities:
                    try:
                        entity_info = await discovery.create_entity_info_from_object(entity)
                        discovery.register_entity(entity_info.id, entity_info, entity)
                        logger.info(f"Registered in-memory entity: {entity_info.id}")
                    except Exception as e:
                        logger.error(f"Failed to register in-memory entity: {e}")
                self._pending_entities = None  # Clear after registration

            # Get the final entity count after all registration
            all_entities = self.executor.entity_discovery.list_entities()
            logger.info(f"Total entities available: {len(all_entities)}")

        return self.executor

    def create_app(self) -> FastAPI:
        """Create the FastAPI application."""

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
            # Startup
            logger.info("Starting Agent Framework Server")
            await self._ensure_executor()
            yield
            # Shutdown
            logger.info("Shutting down Agent Framework Server")

        app = FastAPI(
            title="Agent Framework Server",
            description="OpenAI-compatible API server for Agent Framework and other AI frameworks",
            version="1.0.0",
            lifespan=lifespan,
        )

        # Add CORS middleware
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

    def _register_routes(self, app: FastAPI) -> None:
        """Register API routes."""

        @app.get("/health")
        async def health_check() -> dict[str, Any]:
            """Health check endpoint."""
            executor = await self._ensure_executor()
            entities = await executor.discover_entities()

            return {"status": "healthy", "entities_count": len(entities), "framework": "agent_framework"}

        @app.get("/v1/entities", response_model=DiscoveryResponse)
        async def discover_entities() -> DiscoveryResponse:
            """List all registered entities."""
            try:
                executor = await self._ensure_executor()
                # Use list_entities() instead of discover_entities() to get already-registered entities
                entities = executor.entity_discovery.list_entities()
                return DiscoveryResponse(entities=entities)
            except Exception as e:
                logger.error(f"Error listing entities: {e}")
                raise HTTPException(status_code=500, detail=f"Entity listing failed: {e!s}") from e

        @app.get("/v1/entities/{entity_id}/info", response_model=EntityInfo)
        async def get_entity_info(entity_id: str) -> EntityInfo:
            """Get detailed information about a specific entity."""
            try:
                executor = await self._ensure_executor()
                entity_info = executor.get_entity_info(entity_id)

                if not entity_info:
                    raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

                # For workflows, populate additional detailed information
                if entity_info.type == "workflow":
                    entity_obj = executor.entity_discovery.get_entity_object(entity_id)
                    if entity_obj:
                        # Get workflow structure
                        workflow_dump = None
                        if hasattr(entity_obj, "model_dump"):
                            workflow_dump = entity_obj.model_dump()
                        elif hasattr(entity_obj, "__dict__"):
                            workflow_dump = {k: v for k, v in entity_obj.__dict__.items() if not k.startswith("_")}

                        # Get input schema information
                        input_schema = {}
                        input_type_name = "Unknown"
                        start_executor_id = ""

                        try:
                            start_executor = entity_obj.get_start_executor()
                            if start_executor and hasattr(start_executor, "_handlers"):
                                message_types = list(start_executor._handlers.keys())
                                if message_types:
                                    input_type = message_types[0]
                                    input_type_name = getattr(input_type, "__name__", str(input_type))

                                    # Basic schema generation for common types
                                    if input_type is str:
                                        input_schema = {"type": "string"}
                                    elif input_type is dict:
                                        input_schema = {"type": "object"}
                                    elif hasattr(input_type, "model_json_schema"):
                                        input_schema = input_type.model_json_schema()

                                    start_executor_id = getattr(start_executor, "executor_id", "")
                        except Exception as e:
                            logger.debug(f"Could not extract input info for workflow {entity_id}: {e}")

                        # Get executor list
                        executor_list = []
                        if hasattr(entity_obj, "executors") and entity_obj.executors:
                            executor_list = [getattr(ex, "executor_id", str(ex)) for ex in entity_obj.executors]

                        # Create copy of entity info and populate workflow-specific fields
                        enhanced_info = entity_info.model_copy()
                        enhanced_info.workflow_dump = workflow_dump
                        enhanced_info.input_schema = input_schema
                        enhanced_info.input_type_name = input_type_name
                        enhanced_info.start_executor_id = start_executor_id

                        # Update executors field if we found better data
                        if executor_list:
                            enhanced_info.executors = executor_list
                        return enhanced_info

                # For non-workflow entities, return as-is
                return entity_info

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting entity info for {entity_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get entity info: {e!s}") from e

        @app.post("/v1/responses")
        async def create_response(request: AgentFrameworkRequest, raw_request: Request) -> Any:
            """OpenAI Responses API endpoint."""
            try:
                # Debug: log the incoming request
                raw_body = await raw_request.body()
                logger.info(f"Raw request body: {raw_body.decode()}")
                logger.info(f"Parsed request: model={request.model}, extra_body={request.extra_body}")

                # Get entity_id using the new method
                entity_id = request.get_entity_id()
                logger.info(f"Extracted entity_id: {entity_id}")

                if not entity_id:
                    error = OpenAIError.create(f"Missing entity_id. Request extra_body: {request.extra_body}")
                    return JSONResponse(status_code=400, content=error.model_dump())

                # Get executor and validate entity exists
                executor = await self._ensure_executor()
                try:
                    entity_info = executor.get_entity_info(entity_id)
                    logger.info(f"Found entity: {entity_info.name} ({entity_info.type})")
                except Exception:
                    error = OpenAIError.create(f"Entity not found: {entity_id}")
                    return JSONResponse(status_code=404, content=error.model_dump())

                # Execute request
                if request.stream:
                    return StreamingResponse(
                        self._stream_execution(executor, request),
                        media_type="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "Access-Control-Allow-Origin": "*",
                        },
                    )
                return await executor.execute_sync(request)

            except Exception as e:
                logger.error(f"Error executing request: {e}")
                error = OpenAIError.create(f"Execution failed: {e!s}")
                return JSONResponse(status_code=500, content=error.model_dump())

        @app.post("/v1/threads")
        async def create_thread(request_data: dict[str, Any]) -> dict[str, Any]:
            """Create a new thread for an agent."""
            try:
                agent_id = request_data.get("agent_id")
                if not agent_id:
                    raise HTTPException(status_code=400, detail="agent_id is required")

                executor = await self._ensure_executor()
                thread_id = executor.create_thread(agent_id)

                return {
                    "id": thread_id,
                    "object": "thread",
                    "created_at": int(__import__("time").time()),
                    "metadata": {"agent_id": agent_id},
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error creating thread: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create thread: {e!s}") from e

        @app.get("/v1/threads")
        async def list_threads(agent_id: str) -> dict[str, Any]:
            """List threads for an agent."""
            try:
                executor = await self._ensure_executor()
                thread_ids = executor.list_threads_for_agent(agent_id)

                # Convert thread IDs to thread objects
                threads = []
                for thread_id in thread_ids:
                    threads.append({"id": thread_id, "object": "thread", "agent_id": agent_id})

                return {"object": "list", "data": threads}
            except Exception as e:
                logger.error(f"Error listing threads: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to list threads: {e!s}") from e

        @app.get("/v1/threads/{thread_id}")
        async def get_thread(thread_id: str) -> dict[str, Any]:
            """Get thread information."""
            try:
                executor = await self._ensure_executor()

                # Check if thread exists
                thread = executor.get_thread(thread_id)
                if not thread:
                    raise HTTPException(status_code=404, detail="Thread not found")

                # Get the agent that owns this thread
                agent_id = executor.get_agent_for_thread(thread_id)

                return {"id": thread_id, "object": "thread", "agent_id": agent_id}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting thread {thread_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get thread: {e!s}") from e

        @app.delete("/v1/threads/{thread_id}")
        async def delete_thread(thread_id: str) -> dict[str, Any]:
            """Delete a thread."""
            try:
                executor = await self._ensure_executor()
                success = executor.delete_thread(thread_id)

                if not success:
                    raise HTTPException(status_code=404, detail="Thread not found")

                return {"id": thread_id, "object": "thread.deleted", "deleted": True}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting thread {thread_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete thread: {e!s}") from e

        @app.get("/v1/threads/{thread_id}/messages")
        async def get_thread_messages(thread_id: str) -> dict[str, Any]:
            """Get messages from a thread."""
            try:
                executor = await self._ensure_executor()

                # Check if thread exists
                thread = executor.get_thread(thread_id)
                if not thread:
                    raise HTTPException(status_code=404, detail="Thread not found")

                # Get messages from thread
                messages = await executor.get_thread_messages(thread_id)

                return {"object": "list", "data": messages, "thread_id": thread_id}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting messages for thread {thread_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get thread messages: {e!s}") from e

    async def _stream_execution(
        self, executor: AgentFrameworkExecutor, request: AgentFrameworkRequest
    ) -> AsyncGenerator[str, None]:
        """Stream execution directly through executor."""
        try:
            # Direct call to executor - simple and clean
            async for event in executor.execute_streaming(request):
                yield f"data: {event.model_dump_json()}\n\n"

            # Send final done event
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error in streaming execution: {e}")
            error_event = {"id": "error", "object": "error", "error": {"message": str(e), "type": "execution_error"}}
            yield f"data: {error_event}\n\n"

    def _mount_ui(self, app: FastAPI) -> None:
        """Mount the UI as static files."""
        from pathlib import Path

        ui_dir = Path(__file__).parent / "ui"
        if ui_dir.exists() and ui_dir.is_dir() and self.ui_enabled:
            app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    def register_entities(self, entities: list[Any]) -> None:
        """Register entities to be discovered when server starts.

        Args:
            entities: List of entity objects to register
        """
        if self._pending_entities is None:
            self._pending_entities = []
        self._pending_entities.extend(entities)

    def get_app(self) -> FastAPI:
        """Get the FastAPI application instance."""
        if self._app is None:
            self._app = self.create_app()
        return self._app
