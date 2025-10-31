# Copyright (c) Microsoft. All rights reserved.

"""FastAPI server implementation."""

import inspect
import json
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
from ._openai import OpenAIExecutor
from .models import AgentFrameworkRequest, MetaResponse, OpenAIError
from .models._discovery_models import DiscoveryResponse, EntityInfo

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
        ui_mode: str = "developer",
    ) -> None:
        """Initialize the development server.

        Args:
            entities_dir: Directory to scan for entities
            port: Port to run server on
            host: Host to bind server to
            cors_origins: List of allowed CORS origins
            ui_enabled: Whether to enable the UI
            ui_mode: UI interface mode - 'developer' or 'user'
        """
        self.entities_dir = entities_dir
        self.port = port
        self.host = host
        self.cors_origins = cors_origins or ["*"]
        self.ui_enabled = ui_enabled
        self.ui_mode = ui_mode
        self.executor: AgentFrameworkExecutor | None = None
        self.openai_executor: OpenAIExecutor | None = None
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
                        entity_info = await discovery.create_entity_info_from_object(entity, source="in-memory")
                        discovery.register_entity(entity_info.id, entity_info, entity)
                        logger.info(f"Registered in-memory entity: {entity_info.id}")
                    except Exception as e:
                        logger.error(f"Failed to register in-memory entity: {e}")
                self._pending_entities = None  # Clear after registration

            # Get the final entity count after all registration
            all_entities = self.executor.entity_discovery.list_entities()
            logger.info(f"Total entities available: {len(all_entities)}")

        return self.executor

    async def _ensure_openai_executor(self) -> OpenAIExecutor:
        """Ensure OpenAI executor is initialized.

        Returns:
            OpenAI executor instance

        Raises:
            ValueError: If OpenAI executor cannot be initialized
        """
        if self.openai_executor is None:
            # Initialize local executor first to get conversation_store
            local_executor = await self._ensure_executor()

            # Create OpenAI executor with shared conversation store
            self.openai_executor = OpenAIExecutor(local_executor.conversation_store)

            if self.openai_executor.is_configured:
                logger.info("OpenAI proxy mode available (OPENAI_API_KEY configured)")
            else:
                logger.info("OpenAI proxy mode disabled (OPENAI_API_KEY not set)")

        return self.openai_executor

    async def _cleanup_entities(self) -> None:
        """Cleanup entity resources (close clients, MCP tools, credentials, etc.)."""
        if not self.executor:
            return

        logger.info("Cleaning up entity resources...")
        entities = self.executor.entity_discovery.list_entities()
        closed_count = 0
        mcp_tools_closed = 0
        credentials_closed = 0
        hook_count = 0

        for entity_info in entities:
            entity_id = entity_info.id

            try:
                # Step 1: Execute registered cleanup hooks (NEW)
                cleanup_hooks = self.executor.entity_discovery.get_cleanup_hooks(entity_id)
                for hook in cleanup_hooks:
                    try:
                        if inspect.iscoroutinefunction(hook):
                            await hook()
                        else:
                            hook()
                        hook_count += 1
                        logger.debug(f"✓ Executed cleanup hook for: {entity_id}")
                    except Exception as e:
                        logger.warning(f"⚠ Cleanup hook failed for {entity_id}: {e}")

                # Step 2: Close chat clients and their credentials (EXISTING)
                entity_obj = self.executor.entity_discovery.get_entity_object(entity_id)

                if entity_obj and hasattr(entity_obj, "chat_client"):
                    client = entity_obj.chat_client

                    # Close the chat client itself
                    if hasattr(client, "close") and callable(client.close):
                        if inspect.iscoroutinefunction(client.close):
                            await client.close()
                        else:
                            client.close()
                        closed_count += 1
                        logger.debug(f"Closed client for entity: {entity_info.id}")

                    # Close credentials attached to chat clients (e.g., AzureCliCredential)
                    credential_attrs = ["credential", "async_credential", "_credential", "_async_credential"]
                    for attr in credential_attrs:
                        if hasattr(client, attr):
                            cred = getattr(client, attr)
                            if cred and hasattr(cred, "close") and callable(cred.close):
                                try:
                                    if inspect.iscoroutinefunction(cred.close):
                                        await cred.close()
                                    else:
                                        cred.close()
                                    credentials_closed += 1
                                    logger.debug(f"Closed credential for entity: {entity_info.id}")
                                except Exception as e:
                                    logger.warning(f"Error closing credential for {entity_info.id}: {e}")

                # Close MCP tools (framework tracks them in _local_mcp_tools)
                if entity_obj and hasattr(entity_obj, "_local_mcp_tools"):
                    for mcp_tool in entity_obj._local_mcp_tools:
                        if hasattr(mcp_tool, "close") and callable(mcp_tool.close):
                            try:
                                if inspect.iscoroutinefunction(mcp_tool.close):
                                    await mcp_tool.close()
                                else:
                                    mcp_tool.close()
                                mcp_tools_closed += 1
                                tool_name = getattr(mcp_tool, "name", "unknown")
                                logger.debug(f"Closed MCP tool '{tool_name}' for entity: {entity_info.id}")
                            except Exception as e:
                                logger.warning(f"Error closing MCP tool for {entity_info.id}: {e}")

            except Exception as e:
                logger.warning(f"Error cleaning up entity {entity_id}: {e}")

        if hook_count > 0:
            logger.info(f"✓ Executed {hook_count} cleanup hook(s)")
        if closed_count > 0:
            logger.info(f"✓ Closed {closed_count} entity client(s)")
        if credentials_closed > 0:
            logger.info(f"✓ Closed {credentials_closed} credential(s)")
        if mcp_tools_closed > 0:
            logger.info(f"✓ Closed {mcp_tools_closed} MCP tool(s)")

        # Close OpenAI executor if it exists
        if self.openai_executor:
            try:
                await self.openai_executor.close()
                logger.info("Closed OpenAI executor")
            except Exception as e:
                logger.warning(f"Error closing OpenAI executor: {e}")

    def create_app(self) -> FastAPI:
        """Create the FastAPI application."""

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
            # Startup
            logger.info("Starting Agent Framework Server")
            await self._ensure_executor()
            await self._ensure_openai_executor()  # Initialize OpenAI executor
            yield
            # Shutdown
            logger.info("Shutting down Agent Framework Server")

            # Cleanup entity resources (e.g., close credentials, clients)
            if self.executor:
                await self._cleanup_entities()

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
            # Use list_entities() to avoid re-discovering and re-registering entities
            entities = executor.entity_discovery.list_entities()

            return {"status": "healthy", "entities_count": len(entities), "framework": "agent_framework"}

        @app.get("/meta", response_model=MetaResponse)
        async def get_meta() -> MetaResponse:
            """Get server metadata and configuration."""
            import os

            from . import __version__

            # Ensure executors are initialized to check capabilities
            openai_executor = await self._ensure_openai_executor()

            return MetaResponse(
                ui_mode=self.ui_mode,  # type: ignore[arg-type]
                version=__version__,
                framework="agent_framework",
                capabilities={
                    "tracing": os.getenv("ENABLE_OTEL") == "true",
                    "openai_proxy": openai_executor.is_configured,
                },
            )

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
            """Get detailed information about a specific entity (triggers lazy loading)."""
            try:
                executor = await self._ensure_executor()
                entity_info = executor.get_entity_info(entity_id)

                if not entity_info:
                    raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

                # Trigger lazy loading if entity not yet loaded
                # This will import the module and enrich metadata
                entity_obj = await executor.entity_discovery.load_entity(entity_id)

                # Get updated entity info (may have been enriched during load)
                entity_info = executor.get_entity_info(entity_id) or entity_info

                # For workflows, populate additional detailed information
                if entity_info.type == "workflow" and entity_obj:
                    # Entity object already loaded by load_entity() above
                    # Get workflow structure
                    workflow_dump = None
                    if hasattr(entity_obj, "to_dict") and callable(getattr(entity_obj, "to_dict", None)):
                        try:
                            workflow_dump = entity_obj.to_dict()  # type: ignore[attr-defined]
                        except Exception:
                            workflow_dump = None
                    elif hasattr(entity_obj, "to_json") and callable(getattr(entity_obj, "to_json", None)):
                        try:
                            raw_dump = entity_obj.to_json()  # type: ignore[attr-defined]
                        except Exception:
                            workflow_dump = None
                        else:
                            if isinstance(raw_dump, (bytes, bytearray)):
                                try:
                                    raw_dump = raw_dump.decode()
                                except Exception:
                                    raw_dump = raw_dump.decode(errors="replace")
                            if isinstance(raw_dump, str):
                                try:
                                    parsed_dump = json.loads(raw_dump)
                                except Exception:
                                    workflow_dump = raw_dump
                                else:
                                    workflow_dump = parsed_dump if isinstance(parsed_dump, dict) else raw_dump
                            else:
                                workflow_dump = raw_dump
                    elif hasattr(entity_obj, "__dict__"):
                        workflow_dump = {k: v for k, v in entity_obj.__dict__.items() if not k.startswith("_")}

                    # Get input schema information
                    input_schema = {}
                    input_type_name = "Unknown"
                    start_executor_id = ""

                    try:
                        from ._utils import (
                            extract_executor_message_types,
                            generate_input_schema,
                            select_primary_input_type,
                        )

                        start_executor = entity_obj.get_start_executor()
                    except Exception as e:
                        logger.debug(f"Could not extract input info for workflow {entity_id}: {e}")
                    else:
                        if start_executor:
                            start_executor_id = getattr(start_executor, "executor_id", "") or getattr(
                                start_executor, "id", ""
                            )

                            message_types = extract_executor_message_types(start_executor)
                            input_type = select_primary_input_type(message_types)

                            if input_type:
                                input_type_name = getattr(input_type, "__name__", str(input_type))

                                # Generate schema using comprehensive schema generation
                                input_schema = generate_input_schema(input_type)

                    if not input_schema:
                        input_schema = {"type": "string"}
                        if input_type_name == "Unknown":
                            input_type_name = "string"

                    # Get executor list
                    executor_list = []
                    if hasattr(entity_obj, "executors") and entity_obj.executors:
                        executor_list = [getattr(ex, "executor_id", str(ex)) for ex in entity_obj.executors]

                    # Check if workflow supports checkpointing
                    from ._executor import workflow_supports_checkpointing

                    supports_checkpointing = workflow_supports_checkpointing(entity_obj)

                    # Create copy of entity info and populate workflow-specific fields
                    update_payload: dict[str, Any] = {
                        "workflow_dump": workflow_dump,
                        "input_schema": input_schema,
                        "input_type_name": input_type_name,
                        "start_executor_id": start_executor_id,
                        "supports_checkpointing": supports_checkpointing,
                    }
                    if executor_list:
                        update_payload["executors"] = executor_list
                    return entity_info.model_copy(update=update_payload)

                # For non-workflow entities, return as-is
                return entity_info

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting entity info for {entity_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get entity info: {e!s}") from e

        @app.post("/v1/entities/{entity_id}/reload")
        async def reload_entity(entity_id: str) -> dict[str, Any]:
            """Hot reload entity (clears cache, will reimport on next access).

            This enables hot reload during development - edit entity code, call this endpoint,
            and the next execution will use the updated code without server restart.
            """
            try:
                executor = await self._ensure_executor()

                # Check if entity exists
                entity_info = executor.get_entity_info(entity_id)
                if not entity_info:
                    raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

                # Invalidate cache
                executor.entity_discovery.invalidate_entity(entity_id)

                return {
                    "success": True,
                    "message": f"Entity '{entity_id}' cache cleared. Will reload on next access.",
                }

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error reloading entity {entity_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to reload entity: {e!s}") from e

        @app.post("/v1/responses")
        async def create_response(request: AgentFrameworkRequest, raw_request: Request) -> Any:
            """OpenAI Responses API endpoint - routes to local or OpenAI executor."""
            try:
                # Check if frontend requested OpenAI proxy mode
                proxy_mode = raw_request.headers.get("X-Proxy-Backend")

                if proxy_mode == "openai":
                    # Route to OpenAI executor
                    logger.info("🔀 Routing to OpenAI proxy mode")
                    openai_executor = await self._ensure_openai_executor()

                    if not openai_executor.is_configured:
                        error = OpenAIError.create(
                            "OpenAI proxy mode not configured. Set OPENAI_API_KEY environment variable."
                        )
                        return JSONResponse(status_code=503, content=error.to_dict())

                    # Execute via OpenAI with dedicated streaming method
                    if request.stream:
                        return StreamingResponse(
                            self._stream_openai_execution(openai_executor, request),
                            media_type="text/event-stream",
                            headers={
                                "Cache-Control": "no-cache",
                                "Connection": "keep-alive",
                                "Access-Control-Allow-Origin": "*",
                            },
                        )
                    return await openai_executor.execute_sync(request)

                # Route to local Agent Framework executor (original behavior)
                raw_body = await raw_request.body()
                logger.info(f"Raw request body: {raw_body.decode()}")
                logger.info(f"Parsed request: model={request.model}, extra_body={request.extra_body}")

                # Get entity_id using the new method
                entity_id = request.get_entity_id()
                logger.info(f"Extracted entity_id: {entity_id}")

                if not entity_id:
                    error = OpenAIError.create(f"Missing entity_id. Request extra_body: {request.extra_body}")
                    return JSONResponse(status_code=400, content=error.to_dict())

                # Get executor and validate entity exists
                executor = await self._ensure_executor()
                try:
                    entity_info = executor.get_entity_info(entity_id)
                    logger.info(f"Found entity: {entity_info.name} ({entity_info.type})")
                except Exception:
                    error = OpenAIError.create(f"Entity not found: {entity_id}")
                    return JSONResponse(status_code=404, content=error.to_dict())

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
                return JSONResponse(status_code=500, content=error.to_dict())

        # ========================================
        # OpenAI Conversations API (Standard)
        # ========================================

        @app.post("/v1/conversations", response_model=None)
        async def create_conversation(raw_request: Request) -> dict[str, Any] | JSONResponse:
            """Create a new conversation - routes to OpenAI or local based on mode."""
            try:
                # Parse request body
                request_data = await raw_request.json()

                # Check if frontend requested OpenAI proxy mode
                proxy_mode = raw_request.headers.get("X-Proxy-Backend")

                if proxy_mode == "openai":
                    # Create conversation in OpenAI
                    openai_executor = await self._ensure_openai_executor()
                    if not openai_executor.is_configured:
                        error = OpenAIError.create(
                            "OpenAI proxy mode not configured. Set OPENAI_API_KEY environment variable.",
                            type="configuration_error",
                            code="openai_not_configured",
                        )
                        return JSONResponse(status_code=503, content=error.to_dict())

                    # Use OpenAI client to create conversation
                    from openai import APIStatusError, AsyncOpenAI, AuthenticationError, PermissionDeniedError

                    client = AsyncOpenAI(
                        api_key=openai_executor.api_key,
                        base_url=openai_executor.base_url,
                    )

                    try:
                        metadata = request_data.get("metadata")
                        logger.debug(f"Creating OpenAI conversation with metadata: {metadata}")
                        conversation = await client.conversations.create(metadata=metadata)
                        logger.info(f"Created OpenAI conversation: {conversation.id}")
                        return conversation.model_dump()
                    except AuthenticationError as e:
                        # 401 - Invalid API key or authentication issue
                        logger.error(f"OpenAI authentication error creating conversation: {e}")
                        error_body = e.body if hasattr(e, "body") else {}
                        error_data = error_body.get("error", {}) if isinstance(error_body, dict) else {}
                        error = OpenAIError.create(
                            message=error_data.get("message", str(e)),
                            type=error_data.get("type", "authentication_error"),
                            code=error_data.get("code", "invalid_api_key"),
                        )
                        return JSONResponse(status_code=401, content=error.to_dict())
                    except PermissionDeniedError as e:
                        # 403 - Permission denied
                        logger.error(f"OpenAI permission denied creating conversation: {e}")
                        error_body = e.body if hasattr(e, "body") else {}
                        error_data = error_body.get("error", {}) if isinstance(error_body, dict) else {}
                        error = OpenAIError.create(
                            message=error_data.get("message", str(e)),
                            type=error_data.get("type", "permission_denied"),
                            code=error_data.get("code", "insufficient_permissions"),
                        )
                        return JSONResponse(status_code=403, content=error.to_dict())
                    except APIStatusError as e:
                        # Other OpenAI API errors (rate limit, etc.)
                        logger.error(f"OpenAI API error creating conversation: {e}")
                        error_body = e.body if hasattr(e, "body") else {}
                        error_data = error_body.get("error", {}) if isinstance(error_body, dict) else {}
                        error = OpenAIError.create(
                            message=error_data.get("message", str(e)),
                            type=error_data.get("type", "api_error"),
                            code=error_data.get("code", "unknown_error"),
                        )
                        return JSONResponse(
                            status_code=e.status_code if hasattr(e, "status_code") else 500, content=error.to_dict()
                        )

                # Local mode - use DevUI conversation store
                metadata = request_data.get("metadata")
                executor = await self._ensure_executor()
                conversation = executor.conversation_store.create_conversation(metadata=metadata)
                return conversation.model_dump()
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error creating conversation: {e}", exc_info=True)
                error = OpenAIError.create(f"Failed to create conversation: {e!s}")
                return JSONResponse(status_code=500, content=error.to_dict())

        @app.get("/v1/conversations")
        async def list_conversations(agent_id: str | None = None) -> dict[str, Any]:
            """List conversations, optionally filtered by agent_id."""
            try:
                executor = await self._ensure_executor()

                if agent_id:
                    # Filter by agent_id metadata
                    conversations = executor.conversation_store.list_conversations_by_metadata({"agent_id": agent_id})
                else:
                    # Return all conversations (for InMemoryStore, list all)
                    # Note: This assumes list_conversations_by_metadata({}) returns all
                    conversations = executor.conversation_store.list_conversations_by_metadata({})

                return {
                    "object": "list",
                    "data": [conv.model_dump() for conv in conversations],
                    "has_more": False,
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error listing conversations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to list conversations: {e!s}") from e

        @app.get("/v1/conversations/{conversation_id}")
        async def retrieve_conversation(conversation_id: str) -> dict[str, Any]:
            """Get conversation - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                conversation = executor.conversation_store.get_conversation(conversation_id)
                if not conversation:
                    raise HTTPException(status_code=404, detail="Conversation not found")
                return conversation.model_dump()
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get conversation: {e!s}") from e

        @app.post("/v1/conversations/{conversation_id}")
        async def update_conversation(conversation_id: str, request_data: dict[str, Any]) -> dict[str, Any]:
            """Update conversation metadata - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                metadata = request_data.get("metadata", {})
                conversation = executor.conversation_store.update_conversation(conversation_id, metadata=metadata)
                return conversation.model_dump()
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update conversation: {e!s}") from e

        @app.delete("/v1/conversations/{conversation_id}")
        async def delete_conversation(conversation_id: str) -> dict[str, Any]:
            """Delete conversation - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                result = executor.conversation_store.delete_conversation(conversation_id)
                return result.model_dump()
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete conversation: {e!s}") from e

        @app.post("/v1/conversations/{conversation_id}/items")
        async def create_conversation_items(conversation_id: str, request_data: dict[str, Any]) -> dict[str, Any]:
            """Add items to conversation - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                items = request_data.get("items", [])
                conv_items = await executor.conversation_store.add_items(conversation_id, items=items)
                return {"object": "list", "data": [item.model_dump() for item in conv_items]}
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error adding items to conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to add items: {e!s}") from e

        @app.get("/v1/conversations/{conversation_id}/items")
        async def list_conversation_items(
            conversation_id: str, limit: int = 100, after: str | None = None, order: str = "asc"
        ) -> dict[str, Any]:
            """List conversation items - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                items, has_more = await executor.conversation_store.list_items(
                    conversation_id, limit=limit, after=after, order=order
                )
                return {
                    "object": "list",
                    "data": [item.model_dump() for item in items],
                    "has_more": has_more,
                }
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error listing items for conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to list items: {e!s}") from e

        @app.get("/v1/conversations/{conversation_id}/items/{item_id}")
        async def retrieve_conversation_item(conversation_id: str, item_id: str) -> dict[str, Any]:
            """Get specific conversation item - OpenAI standard."""
            try:
                executor = await self._ensure_executor()
                item = executor.conversation_store.get_item(conversation_id, item_id)
                if not item:
                    raise HTTPException(status_code=404, detail="Item not found")
                return item.model_dump()
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting item {item_id} from conversation {conversation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get item: {e!s}") from e

    async def _stream_execution(
        self, executor: AgentFrameworkExecutor, request: AgentFrameworkRequest
    ) -> AsyncGenerator[str, None]:
        """Stream execution directly through executor."""
        try:
            # Collect events for final response.completed event
            events = []

            # Stream all events
            async for event in executor.execute_streaming(request):
                events.append(event)

                # IMPORTANT: Check model_dump_json FIRST because to_json() can have newlines (pretty-printing)
                # which breaks SSE format. model_dump_json() returns single-line JSON.
                if hasattr(event, "model_dump_json"):
                    payload = event.model_dump_json()  # type: ignore[attr-defined]
                elif hasattr(event, "to_json") and callable(getattr(event, "to_json", None)):
                    payload = event.to_json()  # type: ignore[attr-defined]
                    # Strip newlines from pretty-printed JSON for SSE compatibility
                    payload = payload.replace("\n", "").replace("\r", "")
                elif isinstance(event, dict):
                    # Handle plain dict events (e.g., error events from executor)
                    payload = json.dumps(event)
                elif hasattr(event, "to_dict") and callable(getattr(event, "to_dict", None)):
                    payload = json.dumps(event.to_dict())  # type: ignore[attr-defined]
                else:
                    payload = json.dumps(str(event))
                yield f"data: {payload}\n\n"

            # Aggregate to final response and emit response.completed event (OpenAI standard)
            from .models import ResponseCompletedEvent

            final_response = await executor.message_mapper.aggregate_to_response(events, request)
            completed_event = ResponseCompletedEvent(
                type="response.completed",
                response=final_response,
                sequence_number=len(events),
            )
            yield f"data: {completed_event.model_dump_json()}\n\n"

            # Send final done event
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error in streaming execution: {e}")
            error_event = {"id": "error", "object": "error", "error": {"message": str(e), "type": "execution_error"}}
            yield f"data: {json.dumps(error_event)}\n\n"

    async def _stream_openai_execution(
        self, executor: OpenAIExecutor, request: AgentFrameworkRequest
    ) -> AsyncGenerator[str, None]:
        """Stream execution through OpenAI executor.

        OpenAI events are already in final format - no conversion or aggregation needed.
        Just serialize and stream them as SSE.

        Args:
            executor: OpenAI executor instance
            request: Request to execute

        Yields:
            SSE-formatted event strings
        """
        try:
            # Stream events from OpenAI - they're already ResponseStreamEvent objects
            async for event in executor.execute_streaming(request):
                # Handle error dicts from executor
                if isinstance(event, dict):
                    payload = json.dumps(event)
                    yield f"data: {payload}\n\n"
                    continue

                # OpenAI SDK events have model_dump_json() - use it for single-line JSON
                if hasattr(event, "model_dump_json"):
                    payload = event.model_dump_json()  # type: ignore[attr-defined]
                    yield f"data: {payload}\n\n"
                else:
                    # Fallback (shouldn't happen with OpenAI SDK)
                    logger.warning(f"Unexpected event type from OpenAI: {type(event)}")
                    payload = json.dumps(str(event))
                    yield f"data: {payload}\n\n"

            # OpenAI already sends response.completed event - no aggregation needed!
            # Just send [DONE] marker
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error in OpenAI streaming execution: {e}", exc_info=True)
            # Emit proper response.failed event
            import os

            error_event = {
                "type": "response.failed",
                "response": {
                    "id": f"resp_{os.urandom(16).hex()}",
                    "status": "failed",
                    "error": {
                        "message": str(e),
                        "type": "internal_error",
                        "code": "streaming_error",
                    },
                },
            }
            yield f"data: {json.dumps(error_event)}\n\n"

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
