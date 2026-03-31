# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pytest import fixture


def _reset_env(monkeypatch, env_names: list[str]) -> None:  # type: ignore
    for env_name in env_names:
        monkeypatch.delenv(env_name, raising=False)  # type: ignore


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
def openai_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for OpenAISettings."""
    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    _reset_env(
        monkeypatch,
        [
            "OPENAI_API_KEY",
            "OPENAI_ORG_ID",
            "OPENAI_MODEL",
            "OPENAI_EMBEDDING_MODEL",
            "OPENAI_CHAT_MODEL",
            "OPENAI_RESPONSES_MODEL",
            "OPENAI_TEXT_MODEL_ID",
            "OPENAI_TEXT_TO_IMAGE_MODEL_ID",
            "OPENAI_AUDIO_TO_TEXT_MODEL_ID",
            "OPENAI_TEXT_TO_AUDIO_MODEL_ID",
            "OPENAI_REALTIME_MODEL_ID",
            "OPENAI_API_VERSION",
            "OPENAI_BASE_URL",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_BASE_URL",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",
            "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME",
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
            "AZURE_OPENAI_API_VERSION",
        ],
    )

    env_vars = {
        "OPENAI_API_KEY": "test-dummy-key",
        "OPENAI_ORG_ID": "test_org_id",
        "OPENAI_MODEL": "test_model_id",
        "OPENAI_EMBEDDING_MODEL": "test_embedding_model_id",
        "OPENAI_TEXT_MODEL_ID": "test_text_model_id",
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


@fixture()
def azure_openai_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for Azure-backed OpenAI tests."""
    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    _reset_env(
        monkeypatch,
        [
            "OPENAI_API_KEY",
            "OPENAI_ORG_ID",
            "OPENAI_MODEL",
            "OPENAI_EMBEDDING_MODEL",
            "OPENAI_CHAT_MODEL",
            "OPENAI_RESPONSES_MODEL",
            "OPENAI_TEXT_MODEL_ID",
            "OPENAI_TEXT_TO_IMAGE_MODEL_ID",
            "OPENAI_AUDIO_TO_TEXT_MODEL_ID",
            "OPENAI_TEXT_TO_AUDIO_MODEL_ID",
            "OPENAI_REALTIME_MODEL_ID",
            "OPENAI_API_VERSION",
            "OPENAI_BASE_URL",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_BASE_URL",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",
            "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME",
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
            "AZURE_OPENAI_API_VERSION",
        ],
    )

    env_vars = {
        "AZURE_OPENAI_ENDPOINT": "https://test-endpoint.openai.azure.com",
        "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME": "test_chat_deployment",
        "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME": "test_responses_deployment",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME": "test_embedding_deployment",
        "AZURE_OPENAI_DEPLOYMENT_NAME": "test_deployment",
        "AZURE_OPENAI_API_KEY": "test_api_key",
        "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars


# region Observability fixtures
@fixture
def enable_instrumentation(request: Any) -> bool:
    """Fixture that returns a boolean indicating if Otel is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def enable_sensitive_data(request: Any) -> bool:
    """Fixture that returns a boolean indicating if sensitive data is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def span_exporter(monkeypatch, enable_instrumentation: bool, enable_sensitive_data: bool) -> Generator[SpanExporter]:
    """Fixture to remove environment variables for ObservabilitySettings."""
    env_vars = [
        "ENABLE_INSTRUMENTATION",
        "ENABLE_SENSITIVE_DATA",
        "ENABLE_CONSOLE_EXPORTERS",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
        "OTEL_EXPORTER_OTLP_METRICS_HEADERS",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
        "OTEL_SERVICE_NAME",
        "OTEL_SERVICE_VERSION",
        "OTEL_RESOURCE_ATTRIBUTES",
    ]

    for key in env_vars:
        monkeypatch.delenv(key, raising=False)  # type: ignore
    monkeypatch.setenv("ENABLE_INSTRUMENTATION", str(enable_instrumentation))  # type: ignore
    if not enable_instrumentation:
        enable_sensitive_data = False
    monkeypatch.setenv("ENABLE_SENSITIVE_DATA", str(enable_sensitive_data))  # type: ignore
    import importlib

    import agent_framework.observability as observability
    from opentelemetry import trace

    importlib.reload(observability)

    observability_settings = observability.ObservabilitySettings()

    if enable_instrumentation or enable_sensitive_data:
        from opentelemetry.sdk.trace import TracerProvider

        tracer_provider = TracerProvider(resource=observability_settings._resource)
        trace.set_tracer_provider(tracer_provider)

    monkeypatch.setattr(observability, "OBSERVABILITY_SETTINGS", observability_settings, raising=False)  # type: ignore

    with (
        patch("agent_framework.observability.OBSERVABILITY_SETTINGS", observability_settings),
        patch("agent_framework.observability.configure_otel_providers"),
    ):
        exporter = InMemorySpanExporter()
        if enable_instrumentation or enable_sensitive_data:
            tracer_provider = trace.get_tracer_provider()
            if not hasattr(tracer_provider, "add_span_processor"):
                raise RuntimeError("Tracer provider does not support adding span processors.")

            tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))  # type: ignore

        yield exporter
        exporter.clear()
