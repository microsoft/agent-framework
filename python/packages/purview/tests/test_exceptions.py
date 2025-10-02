# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview exceptions."""

import pytest

from agent_framework_purview import (
    PurviewAuthenticationError,
    PurviewRateLimitError,
    PurviewRequestError,
    PurviewServiceError,
)


class TestPurviewExceptions:
    """Test custom Purview exception classes."""

    def test_purview_service_error(self) -> None:
        """Test PurviewServiceError base exception."""
        error = PurviewServiceError("Service error occurred")
        assert str(error) == "Service error occurred"
        assert isinstance(error, Exception)

    def test_purview_authentication_error(self) -> None:
        """Test PurviewAuthenticationError exception."""
        error = PurviewAuthenticationError("Authentication failed")
        assert str(error) == "Authentication failed"
        assert isinstance(error, PurviewServiceError)

    def test_purview_rate_limit_error(self) -> None:
        """Test PurviewRateLimitError exception."""
        error = PurviewRateLimitError("Rate limit exceeded")
        assert str(error) == "Rate limit exceeded"
        assert isinstance(error, PurviewServiceError)

    def test_purview_request_error(self) -> None:
        """Test PurviewRequestError exception."""
        error = PurviewRequestError("Request failed")
        assert str(error) == "Request failed"
        assert isinstance(error, PurviewServiceError)

    def test_exception_can_be_raised_and_caught(self) -> None:
        """Test exceptions can be raised and caught."""
        with pytest.raises(PurviewAuthenticationError) as exc_info:
            raise PurviewAuthenticationError("Auth error")

        assert "Auth error" in str(exc_info.value)

    def test_exception_hierarchy(self) -> None:
        """Test exception hierarchy allows catching by base class."""
        try:
            raise PurviewRateLimitError("Rate limit")
        except PurviewServiceError as e:
            assert isinstance(e, PurviewRateLimitError)
            assert "Rate limit" in str(e)

    def test_multiple_exception_types(self) -> None:
        """Test different exception types are distinct."""
        auth_error = PurviewAuthenticationError("Auth")
        rate_error = PurviewRateLimitError("Rate")
        request_error = PurviewRequestError("Request")

        assert not isinstance(auth_error, type(rate_error))
        assert not isinstance(rate_error, type(request_error))
        assert all(isinstance(e, PurviewServiceError) for e in [auth_error, rate_error, request_error])
