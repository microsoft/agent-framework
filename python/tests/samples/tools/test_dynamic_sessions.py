# Copyright (c) Microsoft. All rights reserved.

"""Exercise the sample tool without Azure credentials or a model invocation."""

import ast
import traceback
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any
from unittest.mock import AsyncMock

import httpx
import pytest


@pytest.mark.parametrize("outcome", ["success", "http_error", "transport_error"])
async def test_session_identifier_is_not_exposed(outcome):
    sample = Path(__file__).parents[3] / "samples/02-agents/tools/container_apps_dynamic_sessions.py"
    tree = ast.parse(sample.read_text())
    function = next(
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute_python"
    )
    function.decorator_list = []
    session_id = "private-session-id"
    request = httpx.Request("POST", f"https://pool.example/executions?identifier={session_id}")
    output = {"stdout": "63", "stderr": "", "executionResult": None}
    response = httpx.Response(
        403 if outcome == "http_error" else 200,
        json={"identifier": session_id, "id": "private-operation-id", "status": "Succeeded", "result": output},
        request=request,
    )
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    if outcome == "transport_error":
        client.post.side_effect = httpx.ConnectError(str(request.url), request=request)
    namespace = {
        "Annotated": Annotated,
        "Any": Any,
        "httpx": httpx,
        "credential": SimpleNamespace(get_token=AsyncMock(return_value=SimpleNamespace(token="token"))),
        "http_client": client,
        "pool_endpoint": "https://pool.example",
        "session_id": session_id,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(sample), "exec"), namespace)
    if outcome == "success":
        assert await namespace["execute_python"]("print(63)") == {"status": "Succeeded", "result": output}
    else:
        with pytest.raises(RuntimeError) as caught:
            await namespace["execute_python"]("print(63)")
        rendered = "".join(traceback.format_exception(caught.value))
        assert session_id not in rendered
        assert "https://pool.example" not in rendered
        assert "403" in str(caught.value) if outcome == "http_error" else "request failed" in str(caught.value)
    assert client.post.call_args.kwargs["params"]["identifier"] == session_id
