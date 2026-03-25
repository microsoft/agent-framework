# Copyright (c) Microsoft. All rights reserved.

"""Thread management endpoints."""

import json
import logging
import uuid

import azure.functions as func
from services import (
    CosmosConversationStore,
    cosmos_span,
    get_history_provider,
    http_request_span,
)

bp = func.Blueprint()

# Cosmos DB store (lazy singleton)
_store: CosmosConversationStore | None = None


def get_store() -> CosmosConversationStore:
    """Get or create the Cosmos DB conversation store instance."""
    global _store
    if _store is None:
        _store = CosmosConversationStore()
        logging.info("Initialized Cosmos DB conversation store")
    return _store


@bp.route(route="threads", methods=["POST"])
async def create_thread(req: func.HttpRequest) -> func.HttpResponse:
    """
    Create a new conversation thread.

    Request:
        POST /api/threads
        Body: {"user_id": "...", "title": "...", "metadata": {...}}

    Response:
        201 Created
        {"id": "thread_xxx", "created_at": "...", ...}
    """
    try:
        body = req.get_json() if req.get_body() else {}
    except ValueError:
        body = {}

    thread_id = f"thread_{uuid.uuid4().hex[:12]}"
    user_id = body.get("user_id", "anonymous")
    title = body.get("title")
    metadata = body.get("metadata", {})

    async with http_request_span("POST", "/threads", user_id=user_id) as span:
        store = get_store()
        async with cosmos_span("create", "threads", thread_id):
            thread = await store.create_thread(thread_id, user_id, title, metadata)

        logging.info(f"Created thread {thread_id}")

        span.set_attribute("http.status_code", 201)
        return func.HttpResponse(
            body=json.dumps(thread),
            status_code=201,
            mimetype="application/json",
        )


@bp.route(route="threads", methods=["GET"])
async def list_threads(req: func.HttpRequest) -> func.HttpResponse:
    """
    List all conversation threads.

    Query Parameters:
        user_id: Filter by user ID (optional)
        status: Filter by status - 'active', 'archived', 'deleted' (optional)
        limit: Maximum number of threads to return (default 50, max 100)
        offset: Number of threads to skip for pagination (default 0)

    Request:
        GET /api/threads
        GET /api/threads?user_id=user_1234
        GET /api/threads?status=active&limit=20

    Response:
        200 OK
        {
            "threads": [...],
            "count": 10,
            "limit": 50,
            "offset": 0
        }
    """
    user_id = req.params.get("user_id")
    status = req.params.get("status")

    try:
        limit = min(int(req.params.get("limit", 50)), 100)
    except ValueError:
        limit = 50

    try:
        offset = max(int(req.params.get("offset", 0)), 0)
    except ValueError:
        offset = 0

    async with http_request_span("GET", "/threads", user_id=user_id) as span:
        store = get_store()
        async with cosmos_span("query", "threads", "list"):
            threads = await store.list_threads(
                user_id=user_id,
                status=status,
                limit=limit,
                offset=offset,
            )

        result = {
            "threads": threads,
            "count": len(threads),
            "limit": limit,
            "offset": offset,
        }

        logging.info(
            f"Listed {len(threads)} threads (user_id={user_id}, status={status})"
        )

        span.set_attribute("http.status_code", 200)
        return func.HttpResponse(
            body=json.dumps(result),
            mimetype="application/json",
        )


@bp.route(route="threads/{thread_id}", methods=["GET"])
async def get_thread(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get thread metadata.

    Request:
        GET /api/threads/{thread_id}

    Response:
        200 OK
        {"id": "thread_xxx", "created_at": "...", ...}
    """
    thread_id = req.route_params.get("thread_id")

    async with http_request_span(
        "GET", "/threads/{thread_id}", thread_id=thread_id
    ) as span:
        store = get_store()
        async with cosmos_span("read", "threads", thread_id):
            thread = await store.get_thread(thread_id)

        if thread is None:
            span.set_attribute("http.status_code", 404)
            return func.HttpResponse(
                body=json.dumps({"error": "Thread not found"}),
                status_code=404,
                mimetype="application/json",
            )

        span.set_attribute("http.status_code", 200)
        return func.HttpResponse(
            body=json.dumps(thread),
            mimetype="application/json",
        )


@bp.route(route="threads/{thread_id}", methods=["DELETE"])
async def delete_thread(req: func.HttpRequest) -> func.HttpResponse:
    """
    Delete a thread and its messages.

    Deletes both the thread metadata and all messages stored by
    CosmosHistoryProvider for this thread's session.

    Request:
        DELETE /api/threads/{thread_id}

    Response:
        204 No Content
    """
    thread_id = req.route_params.get("thread_id")

    async with http_request_span(
        "DELETE", "/threads/{thread_id}", thread_id=thread_id
    ) as span:
        store = get_store()

        # Delete thread metadata
        async with cosmos_span("delete", "threads", thread_id):
            deleted = await store.delete_thread(thread_id)

        if not deleted:
            span.set_attribute("http.status_code", 404)
            return func.HttpResponse(
                body=json.dumps({"error": "Thread not found"}),
                status_code=404,
                mimetype="application/json",
            )

        # Clear messages from CosmosHistoryProvider
        history_provider = get_history_provider()
        async with cosmos_span("delete", "messages", thread_id):
            await history_provider.clear(session_id=thread_id)

        logging.info(f"Deleted thread {thread_id} and cleared messages")

        span.set_attribute("http.status_code", 204)
        return func.HttpResponse(status_code=204)


@bp.route(route="debug/sessions", methods=["GET"])
async def debug_list_sessions(req: func.HttpRequest) -> func.HttpResponse:
    """
    Debug endpoint to list all session_ids that have messages in CosmosHistoryProvider.
    This helps diagnose mismatches between thread_ids and session_ids.

    GET /api/debug/sessions
    """
    history_provider = get_history_provider()

    try:
        sessions = await history_provider.list_sessions()

        return func.HttpResponse(
            body=json.dumps(
                {
                    "sessions": sessions,
                    "count": len(sessions),
                    "source_id": history_provider.source_id,
                    "note": "Session IDs from messages container. Should match thread_ids.",
                }
            ),
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"Failed to list sessions: {e}")
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )
