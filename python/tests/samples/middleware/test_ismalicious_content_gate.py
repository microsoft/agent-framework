# Copyright (c) Microsoft. All rights reserved.

"""Exercise the sample through Agent's real function-calling and middleware layers.

Only HTTP and the model's responses are simulated. These fixtures test enforcement
and API shape, not IsMalicious detector accuracy. No credentials or live services.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import logging
import sys
from collections.abc import Awaitable, Callable, MutableSequence
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest
from agent_framework import (
    SKIP_PARSING,
    Agent,
    AgentSession,
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatOptions,
    ChatResponse,
    Content,
    FunctionInvocationContext,
    FunctionInvocationLayer,
    Message,
    tool,
)

SAMPLE_PATH = Path(__file__).parents[3] / "samples/02-agents/middleware/ismalicious_content_gate.py"
spec = importlib.util.spec_from_file_location("ismalicious_content_gate", SAMPLE_PATH)
assert spec is not None and spec.loader is not None
sample = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sample
spec.loader.exec_module(sample)

URL = "https://example.test/path?a=1,b=2#frag"
RAW = 'EXTERNAL-CONTENT-MARKER\nOriginal "quoted" text, café, https://unclassified.test/.'
SCAN = {
    "verdict": "allow",
    "injection": {"score": 0, "families": [], "spans": []},
    "links": [
        {"url": "https://unclassified.test/", "entity": "domain:unclassified.test", "verdict": "unknown", "sources": 0}
    ],
    "links_truncated": False,
    "mode": "fast",
    "latency_ms": 1,
    "sanitized_content": "A different replacement that must not be used.",
}


class ScriptedClient(
    FunctionInvocationLayer[ChatOptions], ChatMiddlewareLayer[ChatOptions], BaseChatClient[ChatOptions]
):
    """Fake model transport beneath the genuine framework invocation layers."""

    def __init__(self, tool_name: str, *, url: str = URL) -> None:
        super().__init__()
        self.requests: list[list[Message]] = []
        self.tool_name = tool_name
        self.url = url

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[Message],
        stream: bool,
        options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        assert not stream
        self.requests.append(deepcopy(list(messages)))
        if len(self.requests) == 1:
            return ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="selected-fetch", name=self.tool_name, arguments=json.dumps({"url": self.url})
                            ),
                        ],
                    )
                ]
            )
        return ChatResponse(messages=[Message(role="assistant", contents=["Summary completed."])])


class Scenario:
    def __init__(self, *, url_reply: Any = None, scan_reply: Any = None, body: bytes = RAW.encode()) -> None:
        self.url_reply = url_reply
        self.scan_reply = scan_reply
        self.body = body
        self.events: list[str] = []
        self.gate_requests: list[httpx.Request] = []

    def gate_request(self, request: httpx.Request) -> httpx.Response:
        self.gate_requests.append(request)
        phase = "url" if request.url.path == "/gate/url" else "scan"
        self.events.append(phase)
        reply = self.url_reply if phase == "url" else self.scan_reply
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return httpx.Response(reply, headers={"location": "https://other.test/"})
        if isinstance(reply, bytes):
            return httpx.Response(200, content=reply)
        default = {"url": URL, "entity": "domain:example.test", "verdict": "allow", "sources": 0, "latency_ms": 1}
        return httpx.Response(200, json=reply if reply is not None else (default if phase == "url" else SCAN))

    def fetch_request(self, request: httpx.Request) -> httpx.Response:
        self.events.append("fetch")
        assert "x-api-key" not in request.headers
        return httpx.Response(200, content=self.body, headers={"content-type": "text/plain; charset=utf-8"})


async def run_scenario(
    scenario: Scenario,
    *,
    allow_warn: bool = False,
    custom_result: object | None = None,
    url: str = URL,
) -> tuple[Any, ScriptedClient, list[dict[str, Any]]]:
    reports: list[dict[str, Any]] = []

    async def observe(context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
        try:
            await call_next()
        finally:
            reports.append(deepcopy(context.metadata))

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(scenario.gate_request)) as gate_http,
        httpx.AsyncClient(transport=httpx.MockTransport(scenario.fetch_request)) as fetch_http,
    ):
        fetch_tool = sample.make_text_fetch_tool(fetch_http, approved_host="example.test")
        if custom_result is not None:

            @tool(approval_mode="never_require", result_parser=SKIP_PARSING)
            async def object_result(url: str) -> object:
                return custom_result

            fetch_tool = object_result
        middleware = sample.IsMaliciousContentGate(
            sample.IsMaliciousGate(gate_http, api_key="synthetic-key", api_secret="synthetic-secret"),
            fetch_tool,
            allow_warn=allow_warn,
        )
        model = ScriptedClient(fetch_tool.name, url=url)
        async with Agent(client=model, tools=[fetch_tool], middleware=[observe, middleware]) as agent:
            session = AgentSession()
            result = await agent.run("Summarize the approved document.", session=session)
            if len(model.requests) == 1:
                assert RAW not in json.dumps(session.to_dict())
    return result, model, reports


async def test_allow_retains_exact_text_and_unknown_reputation() -> None:
    scenario = Scenario()
    _, model, reports = await run_scenario(scenario)
    assert scenario.events == ["url", "fetch", "scan"]
    assert len(model.requests) == 2
    results = [
        content.result
        for message in model.requests[1]
        for content in message.contents
        if content.type == "function_result"
    ]
    assert results == [RAW]
    report = reports[0]["ismalicious_scan"]
    assert report["links"][0]["verdict"] == "unknown"
    assert report["sanitized_content"] == SCAN["sanitized_content"]
    assert report["links_truncated"] is False
    url_request, scan_request = scenario.gate_requests
    assert url_request.url.params["u"] == URL
    assert b"%2C" in url_request.url.query and b"%23frag" in url_request.url.query
    assert str(url_request.url).startswith("https://api.ismalicious.com/gate/url?")
    assert scan_request.url == "https://api.ismalicious.com/gate/scan"
    assert json.loads(scan_request.content) == {"content": RAW, "source_url": URL, "mode": "fast"}
    token = base64.b64encode(b"synthetic-key:synthetic-secret").decode()
    assert all(request.headers["x-api-key"] == token for request in scenario.gate_requests)
    assert all(request.extensions["timeout"]["read"] == 15 for request in scenario.gate_requests)


@pytest.mark.parametrize("phase", ["url", "scan"])
@pytest.mark.parametrize(
    "failure", ["block", "warn", "unknown", "missing", "bad-type", "bad-json", 429, 302, 503, "timeout"]
)
async def test_refusal_stops_fetch_or_next_model_and_withholds_result(phase: str, failure: str | int) -> None:
    reply: Any
    if failure in {"block", "warn", "unknown"}:
        reply = {
            **(
                {"url": URL, "entity": "domain:example.test", "sources": 0, "latency_ms": 1} if phase == "url" else SCAN
            ),
            "verdict": failure,
        }
    elif failure == "missing":
        reply = {"verdict": "allow"}
    elif failure == "bad-type":
        reply = {**SCAN, "links_truncated": "false"}
    elif failure == "bad-json":
        reply = b"not JSON"
    elif failure == "timeout":
        reply = httpx.ReadTimeout("Synthetic timeout")
    else:
        reply = failure
    scenario = Scenario(**{f"{phase}_reply": reply})
    result, model, _ = await run_scenario(scenario)
    assert scenario.events == (["url"] if phase == "url" else ["url", "fetch", "scan"])
    assert len(model.requests) == 1
    assert RAW not in str(result)
    assert "EXTERNAL-CONTENT-MARKER" not in str(result)
    assert len(scenario.gate_requests) == (1 if phase == "url" else 2)  # No quota retries/redirects.


async def test_warn_requires_explicit_operator_opt_in() -> None:
    scenario = Scenario(scan_reply={**SCAN, "verdict": "warn"})
    _, model, _ = await run_scenario(scenario, allow_warn=True)
    assert len(model.requests) == 2


@pytest.mark.parametrize("changes", [{"links_truncated": True}, {"mode": "thorough"}])
async def test_incomplete_or_unexpected_scan_scope_is_refused(changes: dict[str, Any]) -> None:
    result, model, reports = await run_scenario(Scenario(scan_reply={**SCAN, **changes}))
    assert len(model.requests) == 1 and RAW not in str(result)
    assert reports[0]["ismalicious_scan"][next(iter(changes))] == next(iter(changes.values()))


@pytest.mark.parametrize("body", [b"\xff", b"x" * (sample.MAX_BODY_BYTES + 1), b"", b"\n" * 530000])
async def test_invalid_utf8_or_full_body_limit_never_reaches_next_model(body: bytes) -> None:
    scenario = Scenario(body=body)
    _, model, _ = await run_scenario(scenario)
    assert len(model.requests) == 1
    assert scenario.events == ["url", "fetch"]


async def test_arbitrary_result_fields_are_not_silently_unscanned() -> None:
    scenario = Scenario()
    result, model, _ = await run_scenario(scenario, custom_result={"text": "allowed-looking", "hidden": RAW})
    assert scenario.events == ["url"]
    assert len(model.requests) == 1 and RAW not in str(result)


async def test_unapproved_destination_is_not_fetched() -> None:
    scenario = Scenario()
    _, model, _ = await run_scenario(scenario, url="https://not-approved.test/")
    assert scenario.events == ["url"] and len(model.requests) == 1


async def test_decision_logs_contain_no_credentials_url_or_content(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="ismalicious_content_gate"):
        await run_scenario(Scenario())
    records = "\n".join(record.getMessage() for record in caplog.records if record.name == "ismalicious_content_gate")
    assert "destination verdict: allow" in records and "content verdict: allow" in records
    assert all(
        value not in records
        for value in [
            "synthetic-key",
            "synthetic-secret",
            URL,
            RAW,
            base64.b64encode(b"synthetic-key:synthetic-secret").decode(),
        ]
    )
