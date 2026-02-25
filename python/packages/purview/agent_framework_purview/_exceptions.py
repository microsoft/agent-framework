# Copyright (c) Microsoft. All rights reserved.
"""Purview specific exceptions mapped to the Integration exception hierarchy."""

from agent_framework.exceptions import IntegrationException, IntegrationInvalidAuthException

__all__ = [
    "PurviewAuthenticationError",
    "PurviewPaymentRequiredError",
    "PurviewRateLimitError",
    "PurviewRequestError",
    "PurviewServiceError",
]


class PurviewServiceError(IntegrationException):
    """Base exception for Purview errors."""


class PurviewAuthenticationError(IntegrationInvalidAuthException):
    """Authentication / authorization failure (401/403)."""


class PurviewPaymentRequiredError(PurviewServiceError):
    """Payment required (402)."""


class PurviewRateLimitError(PurviewServiceError):
    """Rate limiting or throttling (429)."""


class PurviewRequestError(PurviewServiceError):
    """Other non-success HTTP errors."""
