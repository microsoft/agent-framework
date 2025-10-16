# Copyright (c) Microsoft. All rights reserved.

"""Configure Agent Framework telemetry to stream into Opik.

Prerequisites:
  * Install Opik: `pip install opik`
  * Set one of the OTLP endpoints below before running the script:
      - Opik Cloud:
        ```
        export OTEL_EXPORTER_OTLP_ENDPOINT=https://www.comet.com/opik/api/v1/private/otel
        export OTEL_EXPORTER_OTLP_HEADERS='Authorization=<your-api-key>,Comet-Workspace=<workspace>,projectName=<project>'
        ```
      - Opik Enterprise:
        ```
        export OTEL_EXPORTER_OTLP_ENDPOINT=https://<your-comet-domain>/opik/api/v1/private/otel
        export OTEL_EXPORTER_OTLP_HEADERS='Authorization=<your-api-key>,Comet-Workspace=<workspace>,projectName=<project>'
        ```
      - Self-hosted Opik:
        ```
        export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:5173/api/v1/private/otel
        export OTEL_EXPORTER_OTLP_HEADERS='projectName=<project>'
        ```

Run the sample:

```bash
python setup_observability_with_opik.py
```

The script sends a single prompt through the OpenAI Responses client. Open the
trace ID printed in the console inside Opik to inspect the agent → tool → model
spans, token usage, and cost breakdown.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from agent_framework.observability import get_tracer, setup_observability
from agent_framework.openai import OpenAIResponsesClient
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.trace.span import format_trace_id

REQUIRED_ENV_VARS = ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_HEADERS")


def _require_env(name: str) -> str:
    value: Optional[str] = os.getenv(name)
    if value:
        return value
    raise EnvironmentError(
        f"Environment variable '{name}' is required for this sample."
    )


def _validate_environment() -> None:
    for var in REQUIRED_ENV_VARS:
        _require_env(var)


async def main() -> None:
    """Emit a sample trace to Opik using the OTLP HTTP exporter."""

    _validate_environment()

    setup_observability(
        exporters=[OTLPSpanExporter()],
        enable_sensitive_data=True,
    )

    tracer = get_tracer()
    client = OpenAIResponsesClient()

    with tracer.start_as_current_span("Opik Telemetry Demo", kind=trace.SpanKind.CLIENT) as span:
        trace_id = format_trace_id(span.get_span_context().trace_id)
        print(f"Trace ID: {trace_id}")
        response = await client.get_response(
            "Summarize how observability helps debug agent workflows."
        )
        print("Assistant:", response)


if __name__ == "__main__":
    asyncio.run(main())
