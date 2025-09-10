# Copyright (c) Microsoft. All rights reserved.


from typing import Any

from pytest import fixture

from agent_framework.telemetry import OtelSettings, setup_telemetry


@fixture
def enable_otel(request: Any) -> bool:
    """Fixture that returns a boolean indicating if Otel is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def enable_sensitive_data(request: Any) -> bool:
    """Fixture that returns a boolean indicating if sensitive data is enabled."""
    return request.param if hasattr(request, "param") else False


@fixture
def otel_settings(enable_otel: bool, enable_sensitive_data: bool) -> OtelSettings:
    """Fixture to set environment variables for OtelSettings."""

    from agent_framework.telemetry import OTEL_SETTINGS

    setup_telemetry(enable_otel=enable_otel, enable_sensitive_data=enable_sensitive_data)

    return OTEL_SETTINGS
