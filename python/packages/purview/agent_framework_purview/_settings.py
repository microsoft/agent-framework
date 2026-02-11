# Copyright (c) Microsoft. All rights reserved.

import sys
from enum import Enum

from pydantic import BaseModel

if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


class PurviewLocationType(str, Enum):
    """The type of location for Purview policy evaluation."""

    APPLICATION = "application"
    URI = "uri"
    DOMAIN = "domain"


class PurviewAppLocation(BaseModel):
    """Identifier representing the app's location for Purview policy evaluation."""

    location_type: PurviewLocationType
    location_value: str

    def get_policy_location(self) -> dict[str, str]:
        ns = "microsoft.graph"
        if self.location_type == PurviewLocationType.APPLICATION:
            dt = f"{ns}.policyLocationApplication"
        elif self.location_type == PurviewLocationType.URI:
            dt = f"{ns}.policyLocationUrl"
        elif self.location_type == PurviewLocationType.DOMAIN:
            dt = f"{ns}.policyLocationDomain"
        else:  # pragma: no cover - defensive
            raise ValueError("Invalid Purview location type")
        return {"@odata.type": dt, "value": self.location_value}


class PurviewSettings(TypedDict, total=False):
    """Settings for Purview integration mirroring .NET PurviewSettings.

    Attributes:
        app_name: Public app name.
        app_version: Optional version string of the application.
        tenant_id: Optional tenant id (guid) of the user making the request.
        purview_app_location: Optional app location for policy evaluation.
        graph_base_uri: Base URI for Microsoft Graph.
        blocked_prompt_message: Custom message to return when a prompt is blocked by policy.
        blocked_response_message: Custom message to return when a response is blocked by policy.
        ignore_exceptions: If True, all Purview exceptions will be logged but not thrown in middleware.
        ignore_payment_required: If True, 402 payment required errors will be logged but not thrown.
        cache_ttl_seconds: Time to live for cache entries in seconds (default 14400 = 4 hours).
        max_cache_size_bytes: Maximum cache size in bytes (default 200MB).
    """

    app_name: str | None
    app_version: str | None
    tenant_id: str | None
    purview_app_location: PurviewAppLocation | None
    graph_base_uri: str | None
    blocked_prompt_message: str | None
    blocked_response_message: str | None
    ignore_exceptions: bool | None
    ignore_payment_required: bool | None
    cache_ttl_seconds: int | None
    max_cache_size_bytes: int | None


def get_purview_scopes(settings: PurviewSettings) -> list[str]:
    """Get the OAuth scopes for the Purview Graph API.

    Args:
        settings: The Purview settings containing graph_base_uri.

    Returns:
        A list of OAuth scope strings.
    """
    from urllib.parse import urlparse

    graph_base_uri = settings.get("graph_base_uri", "https://graph.microsoft.com/v1.0/")
    host = urlparse(str(graph_base_uri)).hostname or "graph.microsoft.com"
    return [f"https://{host}/.default"]
