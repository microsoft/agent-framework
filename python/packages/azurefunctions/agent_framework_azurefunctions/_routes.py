# Copyright (c) Microsoft. All rights reserved.

"""Single source of truth for the AgentFunctionApp HTTP route prefix and HITL URLs.

The server endpoints (:mod:`._app`) and the in-workflow addressing helper
(:mod:`._hitl_context`) build the same ``{prefix}/workflow/{name}/...`` URLs. Keeping the
shape and the prefix logic here stops the two sides from drifting -- previously they were
only kept in sync by an integration test asserting the two strings match -- and lets a
customized ``routePrefix`` be honored instead of a hardcoded ``api`` that would 404 on
resume. The server derives the prefix from the incoming request URL (the value the host
actually routed); the helper, which runs inside an executor with no request context,
reads it from ``host.json``.
"""

from __future__ import annotations

import functools
import json
import logging
import os
from typing import Any, cast
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

# Azure Functions' default HTTP route prefix, applied when host.json does not override
# ``extensions.http.routePrefix``.
DEFAULT_ROUTE_PREFIX = "api"


@functools.lru_cache(maxsize=1)
def route_prefix() -> str:
    """Return the app's HTTP route prefix, honoring ``host.json``.

    Azure Functions prepends ``extensions.http.routePrefix`` (default ``api``) to every
    HTTP route, and it can be customized or set to an empty string. That value is not
    exposed through an environment variable, so it is read from ``host.json`` under the
    script root (``AzureWebJobsScriptRoot``, falling back to the current working
    directory) and cached for the process. Any failure to locate or parse the file falls
    back to the ``api`` default. Tests that vary ``host.json`` call ``route_prefix.cache_clear()``.
    """
    return _read_route_prefix()


def _read_route_prefix() -> str:
    # AzureWebJobsScriptRoot is the host-set path to the app root (mixed case is the real
    # variable name and is case-sensitive on Linux, so it must not be upper-cased).
    script_root = os.environ.get("AzureWebJobsScriptRoot") or os.getcwd()  # ruff:ignore[uncapitalized-environment-variables]
    host_json_path = os.path.join(script_root, "host.json")
    try:
        with open(host_json_path, encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, ValueError):
        logger.debug("Could not read '%s'; defaulting route prefix to '%s'.", host_json_path, DEFAULT_ROUTE_PREFIX)
        return DEFAULT_ROUTE_PREFIX
    if not isinstance(loaded, dict):
        return DEFAULT_ROUTE_PREFIX
    extensions = cast("dict[str, Any]", loaded).get("extensions")
    if not isinstance(extensions, dict):
        return DEFAULT_ROUTE_PREFIX
    http = cast("dict[str, Any]", extensions).get("http")
    if not isinstance(http, dict):
        return DEFAULT_ROUTE_PREFIX
    prefix = cast("dict[str, Any]", http).get("routePrefix")
    return prefix.strip("/") if isinstance(prefix, str) else DEFAULT_ROUTE_PREFIX


def _prefix_segment(prefix: str | None) -> str:
    """Return the route-prefix path segment with a trailing slash, or ``""`` when empty."""
    resolved = route_prefix() if prefix is None else prefix.strip("/")
    return f"{resolved}/" if resolved else ""


def build_workflow_respond_url(
    base_url: str,
    workflow_name: str,
    instance_id: str,
    request_id: str,
    *,
    prefix: str | None = None,
) -> str:
    """Build the canonical HITL respond URL a reviewer POSTs to.

    ``{base}/{prefix}/workflow/{name}/respond/{instanceId}/{requestId}``. When ``prefix``
    is omitted it is resolved from ``host.json``. ``request_id`` may be a literal
    ``{requestId}`` placeholder to produce the templated form the run endpoint returns.
    """
    return f"{base_url}/{_prefix_segment(prefix)}workflow/{workflow_name}/respond/{instance_id}/{request_id}"


def build_workflow_status_url(
    base_url: str,
    workflow_name: str,
    instance_id: str,
    *,
    prefix: str | None = None,
) -> str:
    """Build the workflow status URL: ``{base}/{prefix}/workflow/{name}/status/{instanceId}``."""
    return f"{base_url}/{_prefix_segment(prefix)}workflow/{workflow_name}/status/{instance_id}"


def split_request_url(request_url: str) -> tuple[str, str]:
    """Return ``(base_url, route_prefix)`` derived from an incoming request URL.

    On the server the request URL is the authoritative source for the prefix, since the
    host served it through the configured ``routePrefix``. The scheme and host form the
    base URL, and the path before the first ``/workflow/`` segment is the prefix (empty
    when the routes sit directly under the host). Falls back to ``(request_url, "")`` when
    the value is not an absolute URL.
    """
    parts = urlsplit(request_url)
    if not (parts.scheme and parts.netloc):
        return request_url.rstrip("/"), ""
    base_url = f"{parts.scheme}://{parts.netloc}"
    index = parts.path.find("/workflow/")
    prefix = parts.path[:index].strip("/") if index != -1 else ""
    return base_url, prefix
