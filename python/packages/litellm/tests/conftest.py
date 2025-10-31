# Copyright (c) Microsoft. All rights reserved.
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pytest import fixture


# region Connector Settings fixtures
@fixture
def exclude_list(request: Any) -> list[str]:
    """Fixture that returns a list of environment variables to exclude."""
    return request.param if hasattr(request, "param") else []


@fixture
def override_env_param_dict(request: Any) -> dict[str, str]:
    """Fixture that returns a dict of environment variables to override."""
    return request.param if hasattr(request, "param") else {}


@fixture()
def lite_llm_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for client settings."""

    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "OPENAI_API_KEY": "test-dummy-key",
        "OPENAI_ORG_ID": "test_org_id",
        "LITE_LLM_MODEL_ID": "test_responses_model_id",
        "OPENAI_CHAT_MODEL_ID": "test_chat_model_id",
        "OPENAI_TEXT_MODEL_ID": "test_text_model_id",
        "OPENAI_EMBEDDING_MODEL_ID": "test_embedding_model_id",
        "OPENAI_TEXT_TO_IMAGE_MODEL_ID": "test_text_to_image_model_id",
        "OPENAI_AUDIO_TO_TEXT_MODEL_ID": "test_audio_to_text_model_id",
        "OPENAI_TEXT_TO_AUDIO_MODEL_ID": "test_text_to_audio_model_id",
        "OPENAI_REALTIME_MODEL_ID": "test_realtime_model_id",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars


@fixture
def enable_otel(request: Any) -> bool:
    """Fixture that returns a boolean indicating if Otel is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def enable_sensitive_data(request: Any) -> bool:
    """Fixture that returns a boolean indicating if sensitive data is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def span_exporter(monkeypatch, enable_otel: bool, enable_sensitive_data: bool) -> Generator[SpanExporter]:
    """Fixture to remove environment variables for ObservabilitySettings."""

    env_vars = [
        "ENABLE_OTEL",
        "ENABLE_SENSITIVE_DATA",
        "OTLP_ENDPOINT",
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
    ]

    for key in env_vars:
        monkeypatch.delenv(key, raising=False)  # type: ignore
    monkeypatch.setenv("ENABLE_OTEL", str(enable_otel))  # type: ignore
    if not enable_otel:
        # we overwrite sensitive data for tests
        enable_sensitive_data = False
    monkeypatch.setenv("ENABLE_SENSITIVE_DATA", str(enable_sensitive_data))  # type: ignore
    import importlib

    import agent_framework.observability as observability
    from opentelemetry import trace

    # Reload the module to ensure a clean state for tests, then create a
    # fresh ObservabilitySettings instance and patch the module attribute.
    importlib.reload(observability)

    # recreate observability settings with values from above and no file.
    observability_settings = observability.ObservabilitySettings(env_file_path="test.env")
    observability_settings._configure()  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(observability, "OBSERVABILITY_SETTINGS", observability_settings, raising=False)  # type: ignore

    with (
        patch("agent_framework.observability.OBSERVABILITY_SETTINGS", observability_settings),
        patch("agent_framework.observability.setup_observability"),
    ):
        exporter = InMemorySpanExporter()
        if enable_otel or enable_sensitive_data:
            tracer_provider = trace.get_tracer_provider()
            if not hasattr(tracer_provider, "add_span_processor"):
                raise RuntimeError("Tracer provider does not support adding span processors.")

            tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))  # type: ignore

        yield exporter
        # Clean up
        exporter.clear()
