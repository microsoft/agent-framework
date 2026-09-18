# Copyright (c) Microsoft. All rights reserved.

import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("component", ["agent", "chat_client"])
def test_azure_monitor_propagates_context_from_existing_http_client(component: str) -> None:
    """Azure Monitor must instrument the OpenAI transport, even when the client already exists."""
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            textwrap.dedent(
                """
                import asyncio
                import os
                import sys
                from importlib import import_module
                from unittest.mock import AsyncMock, MagicMock, patch

                os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "false"
                os.environ["ENABLE_INSTRUMENTATION"] = "true"
                os.environ["OTEL_SDK_DISABLED"] = "false"
                os.environ["OTEL_PROPAGATORS"] = "tracecontext"
                os.environ.pop("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", None)

                from agent_framework_foundry import FoundryAgent, FoundryChatClient
                from agent_framework_foundry._feature_usage import create_foundry_feature_usage_http_client
                from openai import AsyncOpenAI, DefaultAsyncHttpxClient
                from opentelemetry import trace
                from opentelemetry.sdk.resources import Resource
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import SimpleSpanProcessor
                from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

                async def main():
                    exporter = InMemorySpanExporter()
                    provider = TracerProvider()
                    provider.add_span_processor(SimpleSpanProcessor(exporter))
                    trace.set_tracer_provider(provider)
                    httpx = import_module(DefaultAsyncHttpxClient.__mro__[1].__module__.partition(".")[0])

                    async with create_foundry_feature_usage_http_client() as http_client:
                        project = MagicMock()
                        project.get_openai_client.return_value = AsyncOpenAI(
                            api_key="test-key", http_client=http_client
                        )
                        project.telemetry.get_application_insights_connection_string = AsyncMock(
                            return_value="InstrumentationKey=00000000-0000-0000-0000-000000000000"
                        )
                        component = (
                            FoundryAgent(project_client=project, agent_name="test-agent")
                            if sys.argv[1] == "agent"
                            else FoundryChatClient(project_client=project, model="test-model")
                        )
                        # Keep real auto-instrumentation, but never create remote exporters.
                        with (
                            patch("azure.monitor.opentelemetry._configure._setup_tracing"),
                            patch("azure.monitor.opentelemetry._configure._setup_metrics"),
                            patch("azure.monitor.opentelemetry._configure._setup_logging"),
                        ):
                            await component.configure_azure_monitor(
                                enable_live_metrics=False,
                                resource=Resource({"service.name": "foundry-tracing-test"}),
                            )

                        url = httpx.URL("https://test-project.services.ai.azure.com/openai/v1/responses")
                        transport = http_client._transport_for_url(url)
                        httpcore = import_module(type(transport._pool).__module__.partition(".")[0])
                        # Mock below the instrumented HTTP transport: no socket or Azure call is made.
                        with patch.object(
                            transport._pool,
                            "handle_async_request",
                            new=AsyncMock(return_value=httpcore.Response(200, content=b"{}")),
                        ) as send:
                            with trace.get_tracer("test").start_as_current_span("application") as parent:
                                response = await http_client.post(url, json={})
                                expected_trace_id = f"{parent.get_span_context().trace_id:032x}"
                            assert response.status_code == 200
                            send.assert_awaited_once()
                            headers = dict(send.call_args.args[0].headers)
                            traceparent = headers[b"traceparent"].decode().split("-")
                            assert traceparent[1] == expected_trace_id
                            spans = exporter.get_finished_spans()
                            http_span = next(span for span in spans if span.kind == trace.SpanKind.CLIENT)
                            assert traceparent[2] == f"{http_span.context.span_id:016x}"
                            assert http_span.parent.span_id == parent.get_span_context().span_id
                    provider.shutdown()

                asyncio.run(main())
                """
            ),
            component,
        ],
        check=True,
        timeout=45,
    )
