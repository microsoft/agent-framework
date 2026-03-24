# Copyright (c) Microsoft. All rights reserved.

"""Health check endpoint."""

import json
import logging

import azure.functions as func

from routes.threads import get_store

bp = func.Blueprint()


@bp.route(route="health", methods=["GET"])
async def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    Health check endpoint for monitoring.

    Request:
        GET /api/health

    Response:
        200 OK
        {"status": "healthy", "version": "1.0.0", "cosmos_connected": true}
    """
    cosmos_connected = False
    try:
        store = get_store()
        # Simple connectivity check - initializes connection if needed
        store.container
        cosmos_connected = True
    except Exception as e:
        logging.warning(f"Cosmos DB connectivity check failed: {e}")

    return func.HttpResponse(
        body=json.dumps({
            "status": "healthy",
            "version": "1.0.0",
            "cosmos_connected": cosmos_connected,
        }),
        mimetype="application/json",
    )
