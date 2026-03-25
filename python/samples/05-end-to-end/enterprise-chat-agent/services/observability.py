# Copyright (c) Microsoft. All rights reserved.

"""
Observability module for Enterprise Chat Agent.

Provides complementary spans for layers the Agent Framework doesn't instrument:
- HTTP request lifecycle
- Cosmos DB operations
- Request validation

Uses the framework's configure_otel_providers() and get_tracer() APIs.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from opentelemetry.trace import Span, SpanKind, Status, StatusCode

# Import framework's observability - use framework APIs, don't recreate them
from agent_framework.observability import configure_otel_providers, get_tracer

logger = logging.getLogger(__name__)


class EnterpriseAgentAttr:
    """Custom semantic attributes for enterprise chat agent."""

    # Thread/User context
    THREAD_ID = "enterprise_agent.thread.id"
    USER_ID = "enterprise_agent.user.id"

    # Cosmos DB attributes (following OpenTelemetry DB conventions)
    COSMOS_CONTAINER = "db.cosmosdb.container"
    COSMOS_OPERATION = "db.operation"
    COSMOS_PARTITION_KEY = "db.cosmosdb.partition_key"


def init_observability() -> None:
    """Initialize observability using the Agent Framework's setup.

    Call once at Azure Functions app startup.

    The framework handles:
    - TracerProvider configuration
    - MeterProvider configuration
    - LoggerProvider configuration
    - OTLP and Azure Monitor exporters

    Environment variables used:
    - ENABLE_INSTRUMENTATION: Enable telemetry (default: false)
    - ENABLE_SENSITIVE_DATA: Log message contents (default: false)
    - ENABLE_CONSOLE_EXPORTERS: Enable console output (default: false)
    - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP collector endpoint
    - APPLICATIONINSIGHTS_CONNECTION_STRING: Azure Monitor connection
    - OTEL_SERVICE_NAME: Service name (default: agent_framework)
    """
    try:
        # Reduce verbose logging from httpx/httpcore (HTTP transport details)
        # These generate 100+ traces per request with DEBUG logging
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

        configure_otel_providers()
        logger.info("Observability initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize observability: {e}")


@asynccontextmanager
async def http_request_span(
    method: str,
    path: str,
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> AsyncIterator[Span]:
    """Create a top-level HTTP request span.

    Wraps the entire request lifecycle. Child spans (Cosmos, agent invocation)
    will be nested under this span.

    The span is yielded so callers can set http.status_code before exiting.

    Args:
        method: HTTP method (GET, POST, DELETE, etc.)
        path: Route pattern (e.g., "/threads/{thread_id}/messages")
        thread_id: Thread identifier for correlation
        user_id: User identifier for correlation

    Yields:
        The active span for setting additional attributes like status code.
    """
    tracer = get_tracer("enterprise_chat_agent")
    attributes = {
        "http.method": method,
        "http.route": path,
    }
    if thread_id:
        attributes[EnterpriseAgentAttr.THREAD_ID] = thread_id
    if user_id:
        attributes[EnterpriseAgentAttr.USER_ID] = user_id

    with tracer.start_as_current_span(
        f"http.request {method} {path}",
        kind=SpanKind.SERVER,
        attributes=attributes,
    ) as span:
        try:
            yield span
            # Check if status_code was set; determine success based on it
            status_code = span.attributes.get("http.status_code") if hasattr(
                span, 'attributes'
            ) else None
            if status_code and status_code >= 400:
                span.set_status(Status(StatusCode.ERROR))
            else:
                span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


@asynccontextmanager
async def cosmos_span(
    operation: str,
    container: str,
    partition_key: Optional[str] = None,
) -> AsyncIterator[None]:
    """Create a Cosmos DB operation span.

    Tracks database operations with OpenTelemetry database semantic conventions.

    Args:
        operation: Database operation (read, query, upsert, delete, create)
        container: Cosmos DB container name
        partition_key: Partition key value for the operation
    """
    tracer = get_tracer("enterprise_chat_agent")
    attributes = {
        "db.system": "cosmosdb",
        EnterpriseAgentAttr.COSMOS_OPERATION: operation,
        EnterpriseAgentAttr.COSMOS_CONTAINER: container,
    }
    if partition_key:
        attributes[EnterpriseAgentAttr.COSMOS_PARTITION_KEY] = partition_key

    with tracer.start_as_current_span(
        f"cosmos.{operation} {container}",
        kind=SpanKind.CLIENT,
        attributes=attributes,
    ) as span:
        try:
            yield
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


@asynccontextmanager
async def validation_span(operation: str) -> AsyncIterator[None]:
    """Create a request validation span.

    Tracks authorization and validation checks.

    Args:
        operation: Validation operation name (e.g., "verify_thread_ownership")
    """
    tracer = get_tracer("enterprise_chat_agent")

    with tracer.start_as_current_span(
        f"request.validate {operation}",
        kind=SpanKind.INTERNAL,
    ) as span:
        try:
            yield
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
