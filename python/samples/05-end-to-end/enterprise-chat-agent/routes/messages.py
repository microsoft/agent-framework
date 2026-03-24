# Copyright (c) Microsoft. All rights reserved.

"""Message endpoints for thread conversations."""

import json
import logging
from datetime import datetime, timezone

import azure.functions as func

from services import (
    http_request_span,
    cosmos_span,
    get_agent,
    get_history_provider,
    get_mcp_tool,
)
from routes.threads import get_store

bp = func.Blueprint()


@bp.route(route="threads/{thread_id}/messages", methods=["POST"])
async def send_message(req: func.HttpRequest) -> func.HttpResponse:
    """
    Send a message to the agent and get a response.

    The agent uses:
    - CosmosHistoryProvider for automatic conversation history persistence
    - MCPStreamableHTTPTool for Microsoft Learn documentation search
    - Local tools for weather, calculator, and knowledge base

    Request:
        POST /api/threads/{thread_id}/messages
        Body: {"content": "What's the weather in Seattle?"}

    Response:
        200 OK
        {
            "thread_id": "thread_xxx",
            "role": "assistant",
            "content": "The weather in Seattle is...",
            "tool_calls": [...],
            "timestamp": "..."
        }
    """
    thread_id = req.route_params.get("thread_id")

    async with http_request_span(
        "POST", "/threads/{thread_id}/messages", thread_id=thread_id
    ) as span:
        store = get_store()

        # Check if thread exists
        async with cosmos_span("read", "threads", thread_id):
            thread_exists = await store.thread_exists(thread_id)

        if not thread_exists:
            span.set_attribute("http.status_code", 404)
            return func.HttpResponse(
                body=json.dumps({"error": "Thread not found"}),
                status_code=404,
                mimetype="application/json",
            )

        try:
            body = req.get_json()
            content = body.get("content")
            if not content:
                span.set_attribute("http.status_code", 400)
                return func.HttpResponse(
                    body=json.dumps(
                        {"error": "Missing 'content' in request body"}
                    ),
                    status_code=400,
                    mimetype="application/json",
                )
        except ValueError:
            span.set_attribute("http.status_code", 400)
            return func.HttpResponse(
                body=json.dumps({"error": "Invalid JSON body"}),
                status_code=400,
                mimetype="application/json",
            )

        # Get agent (configured with CosmosHistoryProvider and local tools)
        agent = get_agent()

        # Run agent with MCP tools for Microsoft Learn documentation
        # The agent combines:
        # - Local tools: get_weather, calculate, search_knowledge_base
        # - MCP tools: microsoft_docs_search, microsoft_code_sample_search
        async with get_mcp_tool() as mcp:
            response = await agent.run(
                content,
                session_id=thread_id,
                tools=mcp,  # Add MCP tools for this run
            )

        # Extract response content and tool calls
        response_content = response.text or ""
        tool_calls = []

        # Parse tool calls from response if any
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_calls.append({
                    "tool": getattr(tool_call, "name", str(tool_call)),
                    "arguments": getattr(tool_call, "arguments", {}),
                })

        # Update thread metadata with last message preview
        async with cosmos_span("update", "threads", thread_id):
            preview = response_content[:100] + "..." if len(response_content) > 100 else response_content
            await store.update_thread(
                thread_id=thread_id,
                last_message_preview=preview,
            )

        logging.info(
            f"Processed message for thread {thread_id}, "
            f"tools used: {[t['tool'] for t in tool_calls]}"
        )

        # Build response
        result = {
            "thread_id": thread_id,
            "role": "assistant",
            "content": response_content,
            "tool_calls": tool_calls if tool_calls else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        span.set_attribute("http.status_code", 200)
        return func.HttpResponse(
            body=json.dumps(result),
            mimetype="application/json",
        )


@bp.route(route="threads/{thread_id}/messages", methods=["GET"])
async def get_messages(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get conversation history for a thread from CosmosHistoryProvider.

    Request:
        GET /api/threads/{thread_id}/messages

    Response:
        200 OK
        {"messages": [...]}
    """
    thread_id = req.route_params.get("thread_id")

    async with http_request_span(
        "GET", "/threads/{thread_id}/messages", thread_id=thread_id
    ) as span:
        store = get_store()

        # Check if thread exists
        async with cosmos_span("read", "threads", thread_id):
            thread_exists = await store.thread_exists(thread_id)

        if not thread_exists:
            span.set_attribute("http.status_code", 404)
            return func.HttpResponse(
                body=json.dumps({"error": "Thread not found"}),
                status_code=404,
                mimetype="application/json",
            )

        # Get messages from CosmosHistoryProvider
        history_provider = get_history_provider()
        async with cosmos_span("query", "messages", thread_id):
            messages = await history_provider.get_messages(session_id=thread_id)

        # Convert Message objects to serializable dicts
        message_list = []
        for msg in messages:
            message_list.append({
                "role": msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                "content": msg.content if hasattr(msg, "content") else str(msg),
            })

        span.set_attribute("http.status_code", 200)
        return func.HttpResponse(
            body=json.dumps({"messages": message_list}),
            mimetype="application/json",
        )
