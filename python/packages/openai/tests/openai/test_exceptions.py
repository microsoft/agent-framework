# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from openai import BadRequestError

from agent_framework_openai import OpenAIContentFilterException
from agent_framework_openai._exceptions import ContentFilterCodes, ContentFilterResult, ContentFilterResultSeverity


@pytest.mark.parametrize(
    ("inner_code", "expected_code"),
    [
        ("ResponsibleAIPolicyViolation", "ResponsibleAIPolicyViolation"),
        ("ContentFiltered", "ContentFiltered"),
        ("FutureContentFilterCode", "Unknown"),
        (None, "ResponsibleAIPolicyViolation"),
    ],
)
def test_content_filter_exception_codes(inner_code: str | None, expected_code: str) -> None:
    inner_error: dict[str, Any] = {
        "content_filter_result": {"self_harm": {"filtered": True, "severity": "medium"}},
    }
    if inner_code is not None:
        inner_error["code"] = inner_code
    error = BadRequestError(
        "Prompt blocked by content filter",
        response=MagicMock(status_code=400),
        body={"code": "content_filter", "param": "prompt", "innererror": inner_error},
    )

    exception = OpenAIContentFilterException("Content filtered", error)

    assert isinstance(exception.content_filter_code, ContentFilterCodes)
    assert exception.content_filter_code.value == expected_code
    assert exception.param == "prompt"
    assert exception.content_filter_result == {
        "self_harm": ContentFilterResult(filtered=True, severity=ContentFilterResultSeverity.MEDIUM),
    }
