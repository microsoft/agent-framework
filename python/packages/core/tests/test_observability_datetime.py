# Copyright (c) Microsoft. All rights reserved.

"""Test datetime serialization in observability telemetry."""

import json
from datetime import datetime

from agent_framework._types import FunctionResultContent
from agent_framework.observability import _to_otel_part


def test_datetime_in_tool_results() -> None:
    """Test that tool results with datetime values are serialized.

    Reproduces issue #2219 where datetime objects caused TypeError.
    """
    content = FunctionResultContent(
        call_id="test-call",
        result={"timestamp": datetime(2025, 11, 16, 10, 30, 0)},
    )

    result = _to_otel_part(content)
    parsed = json.loads(result["response"])

    # Datetime should be converted to string
    assert isinstance(parsed["timestamp"], str)
