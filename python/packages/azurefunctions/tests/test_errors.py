# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for custom exception types."""

import pytest

from agent_framework_azurefunctions._errors import IncomingRequestError


class TestIncomingRequestError:
    """Test suite for IncomingRequestError exception."""

    def test_incoming_request_error_default_status_code(self) -> None:
        """Test that IncomingRequestError has a default status code of 400."""
        error = IncomingRequestError("Invalid request")

        assert str(error) == "Invalid request"
        assert error.status_code == 400

    def test_incoming_request_error_custom_status_code(self) -> None:
        """Test that IncomingRequestError can have a custom status code."""
        error = IncomingRequestError("Unauthorized", status_code=401)

        assert str(error) == "Unauthorized"
        assert error.status_code == 401

    def test_incoming_request_error_is_value_error(self) -> None:
        """Test that IncomingRequestError inherits from ValueError."""
        error = IncomingRequestError("Test error")

        assert isinstance(error, ValueError)

    def test_incoming_request_error_can_be_raised_and_caught(self) -> None:
        """Test that IncomingRequestError can be raised and caught."""
        with pytest.raises(IncomingRequestError) as exc_info:
            raise IncomingRequestError("Bad request", status_code=400)

        assert exc_info.value.status_code == 400
