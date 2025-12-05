# Copyright (c) Microsoft. All rights reserved.
"""Purview specific exceptions (minimal error shaping)."""

from agent_framework.exceptions import ServiceResponseException

__all__ = [
    "PurviewAuthenticationError",
    "PurviewPaymentRequiredError",
    "PurviewRateLimitError",
    "PurviewRequestError",
    "PurviewServiceError",
]


class PurviewServiceError(ServiceResponseException):
    """Base exception for Purview errors."""


class PurviewAuthenticationError(PurviewServiceError):
    """Authentication / authorization failure (401/403)."""


class PurviewPaymentRequiredError(PurviewServiceError):
    """Payment required (402)."""


class PurviewRateLimitError(PurviewServiceError):
    """Rate limiting or throttling (429)."""


class PurviewRequestError(PurviewServiceError):
    """Other non-success HTTP errors."""
