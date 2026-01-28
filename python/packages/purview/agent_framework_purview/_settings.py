# Copyright (c) Microsoft. All rights reserved.

from enum import Enum

from agent_framework._settings import AFSettings
from pydantic import BaseModel, Field


class PurviewLocationType(str, Enum):
    """The type of location for Purview policy evaluation."""

    APPLICATION = "application"
    URI = "uri"
    DOMAIN = "domain"


class PurviewAppLocation(BaseModel):
    """Identifier representing the app's location for Purview policy evaluation."""

    location_type: PurviewLocationType = Field(..., description="The location type.")
    location_value: str = Field(..., description="The location value.")

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


class PurviewSettings(AFSettings):
    """Settings for Purview integration mirroring .NET PurviewSettings.

    Keyword Args:
        app_name: Public app name (required).
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

    app_name: str | None = None
    app_version: str | None = None
    tenant_id: str | None = None
    purview_app_location: PurviewAppLocation | None = None
    graph_base_uri: str = "https://graph.microsoft.com/v1.0/"
    blocked_prompt_message: str = "Prompt blocked by policy"
    blocked_response_message: str = "Response blocked by policy"
    ignore_exceptions: bool = False
    ignore_payment_required: bool = False
    cache_ttl_seconds: int = 14400
    max_cache_size_bytes: int = 200 * 1024 * 1024

    def get_scopes(self) -> list[str]:
        from urllib.parse import urlparse

        host = urlparse(self.graph_base_uri).hostname or "graph.microsoft.com"
        return [f"https://{host}/.default"]
