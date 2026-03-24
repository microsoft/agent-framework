# Copyright (c) Microsoft. All rights reserved.

"""Thread management endpoints."""

import json
import logging
import uuid

import azure.functions as func

from services import (
    CosmosConversationStore,
    http_request_span,
    cosmos_span,
    get_history_provider,
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
            thread = await store.create_thread(
                thread_id, user_id, title, metadata
            )

        logging.info(f"Created thread {thread_id}")

        span.set_attribute("http.status_code", 201)
        return func.HttpResponse(
            body=json.dumps(thread),
            status_code=201,
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
