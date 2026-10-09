# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import subprocess
import sys
from textwrap import dedent

import pytest

import agent_framework
import agent_framework.observability as observability
from agent_framework import Agent


def _hide_otel_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__
    for module_name in list(sys.modules):
        if module_name == "opentelemetry.sdk" or module_name.startswith("opentelemetry.sdk."):
            sys.modules.pop(module_name, None)

    def _import_without_otel_sdk(
        name: str,
        globals_: dict[str, object] | None = None,
        locals_: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "opentelemetry.sdk" or name.startswith("opentelemetry.sdk."):
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import_without_otel_sdk)


def test_create_resource_requires_otel_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    _hide_otel_sdk(monkeypatch)

    with pytest.raises(ModuleNotFoundError, match="opentelemetry-sdk"):
        observability.create_resource()


def test_observability_settings_initializes_without_cached_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    _hide_otel_sdk(monkeypatch)

    settings = observability.ObservabilitySettings()

    assert not hasattr(settings, "_resource")


def test_configure_otel_providers_requires_otel_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    _hide_otel_sdk(monkeypatch)
    for key in [
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "VS_CODE_EXTENSION_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ModuleNotFoundError, match="opentelemetry-sdk"):
        observability.configure_otel_providers()


def test_agent_framework_mcp_exports_remain_importable_without_mcp() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            dedent(
                """
                import builtins
                import sys

                real_import = builtins.__import__

                def import_without_mcp(name, globals=None, locals=None, fromlist=(), level=0):
                    if name == "mcp" or name.startswith("mcp."):
                        raise ModuleNotFoundError("No module named 'mcp'", name=name)
                    return real_import(name, globals, locals, fromlist, level)

                builtins.__import__ = import_without_mcp

                import agent_framework

                tool_type = agent_framework.MCPStdioTool
                assert "mcp" not in sys.modules

                try:
                    tool_type(name="test", command="python").get_mcp_client()
                except ModuleNotFoundError as exc:
                    assert str(exc).endswith("Please install `mcp`.")
                else:
                    raise AssertionError("get_mcp_client() unexpectedly succeeded without mcp")
                """
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_mcp_streamable_http_tool_requires_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _import_without_mcp(
        name: str,
        globals_: dict[str, object] | None = None,
        locals_: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "mcp" or name.startswith("mcp."):
            raise ModuleNotFoundError("No module named 'mcp'")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import_without_mcp)

    with pytest.raises(ModuleNotFoundError, match=r"Please install `mcp`\.$"):
        agent_framework.MCPStreamableHTTPTool(name="test", url="https://example.com").get_mcp_client()


def test_agent_as_mcp_server_requires_mcp(client, monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _import_without_mcp(
        name: str,
        globals_: dict[str, object] | None = None,
        locals_: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "mcp" or name.startswith("mcp."):
            raise ModuleNotFoundError("No module named 'mcp'")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import_without_mcp)

    agent = Agent(client=client)  # type: ignore[arg-type]

    with pytest.raises(ModuleNotFoundError, match=r"Please install `mcp`\.$"):
        agent.as_mcp_server()
