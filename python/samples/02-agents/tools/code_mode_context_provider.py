# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from textwrap import indent
from typing import Annotated, Any, Literal

from agent_framework import Agent, AgentSession, BaseContextProvider, Content, FunctionTool, SessionContext, tool
from agent_framework._tools import normalize_tools
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

try:
    from hyperlight_sandbox import WasmSandbox
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "This prototype expects an upstream `hyperlight_sandbox.WasmSandbox` "
        "implementation. Install the provisional Hyperlight package once it "
        "is available, or update this sample to match the final import path."
    ) from exc

load_dotenv()

logger = logging.getLogger(__name__)


"""This sample demonstrates a ContextProvider-driven Hyperlight code-mode prototype.

The provider owns sandbox lifecycle, discovers tools from the agent,
and injects dynamic instructions plus a single `execute_code` tool at run time.

Tools passed to `agent.run(..., tools=...)` are available in
`context.options["tools"]`, so the provider can merge them into the sandbox and,
when configured, remove them from the model-facing run options too.
"""


def collect_tools(*tool_groups: Any) -> list[FunctionTool]:
    """Normalize and collect unique ``FunctionTool`` instances, excluding execute_code."""

    tools: list[FunctionTool] = []
    seen_names: set[str] = set()

    for tool_group in tool_groups:
        normalized_group: Sequence[Any]
        if (
            isinstance(tool_group, Sequence)
            and not isinstance(tool_group, (str, bytes, bytearray))
            and all(isinstance(tool_obj, FunctionTool) for tool_obj in tool_group)
        ):
            normalized_group = tool_group
        else:
            normalized_group = normalize_tools(tool_group)

        for tool_obj in normalized_group:
            if not isinstance(tool_obj, FunctionTool):
                continue

            name = tool_obj.name
            if name == "execute_code" or name in seen_names:
                continue

            seen_names.add(name)
            tools.append(tool_obj)

    return tools


def _resolve_execute_code_approval_mode(
    *,
    base_approval_mode: Literal["always_require", "never_require"] | None,
    tools: Sequence[FunctionTool],
) -> Literal["always_require", "never_require"]:
    """Return the strictest approval mode needed for execute_code."""

    if base_approval_mode == "always_require":
        return "always_require"

    if any(tool_obj.approval_mode == "always_require" for tool_obj in tools):
        return "always_require"

    return "never_require"


def _tool_signature(tools: Sequence[FunctionTool]) -> tuple[tuple[str, int], ...]:
    """Build a stable signature for a normalized tool sequence."""

    return tuple((tool_obj.name, id(tool_obj)) for tool_obj in tools)


def _build_code_mode_instructions(
    *,
    tools: Sequence[FunctionTool],
    tools_visible_to_model: bool,
) -> str:
    """Build dynamic code-mode instructions for the discovered tools."""

    if tools:
        tools_descriptions = "\n\n".join([
            f"- `{tool_obj.name}`\n"
            f"  Description: {str(tool_obj.description or '').strip() or 'No description provided.'}\n"
            "  Parameters:\n"
            f"{indent(json.dumps(tool_obj.parameters(), indent=2, sort_keys=True), '    ')}"
            for tool_obj in tools
        ])
    else:
        tools_descriptions = "- No tools are currently registered inside the sandbox."

    visibility_note = (
        "Some tools listed below may also appear as normal tools, but you should still prefer "
        "execute_code and call them from inside the sandbox. Only if you want to run just that single tool "
        "can you use it directly."
        if tools_visible_to_model
        else "The tools listed below are registered inside the sandbox even if they do not appear as "
        "normal tools. Access them through execute_code with call_tool(...)."
    )

    return f"""You have one primary tool: execute_code.

It runs Python in an isolated Hyperlight Wasm sandbox. You do NOT have direct
access to data. The ONLY way to fetch data or perform computations is by
writing Python code via execute_code that calls `call_tool()` inside the
sandbox.

`call_tool` is a built-in global inside the sandbox. No import is needed.

{visibility_note}

Available sandbox tools:
{tools_descriptions}

Correct usage:
result = call_tool("tool_name", keyword=value)

You can combine multiple call_tool(...) calls with regular Python code in the
same execute_code block, including loops, conditionals, variables, and
post-processing of tool results.

Wrong usage:
call_tool("tool_name", {{"keyword": "value"}})

Do NOT hardcode data that should come from call_tool(...).
Prefer one execute_code call per request when possible.
Always include the complete stdout from execute_code in your final answer.
"""


def _create_wasm_sandbox(*, module_path: Path) -> Any:
    """Create the provisional Hyperlight Wasm sandbox instance."""

    try:
        from hyperlight_sandbox import WasmSandbox
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "This prototype expects an upstream `hyperlight_sandbox.WasmSandbox` "
            "implementation. Install the provisional Hyperlight package once it "
            "is available, or update this sample to match the final import path."
        ) from exc
    if not module_path.exists():
        raise RuntimeError(
            "Hyperlight Wasm module not found.\n"
            f"  module: {module_path} (MISSING)\n"
            "Build the provisional python-sandbox AOT module first, or set "
            "HYPERLIGHT_MODULE to the correct path."
        )

    return WasmSandbox(module_path=str(module_path))


@tool(approval_mode="never_require")
def compute(
    operation: Annotated[str, "Math operation: add, subtract, multiply, or divide."],
    a: Annotated[float, "First numeric operand."],
    b: Annotated[float, "Second numeric operand."],
) -> float:
    """Perform a math operation used by sandbox code."""

    operations = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b else float("inf"),
    }
    return operations.get(operation, 0.0)


@tool(approval_mode="never_require")
def fetch_data(
    table: Annotated[str, "Name of the simulated table to query."],
) -> list[dict[str, Any]]:
    """Fetch simulated records from a named table."""

    return {
        "users": [
            {"id": 1, "name": "Alice", "role": "admin"},
            {"id": 2, "name": "Bob", "role": "user"},
            {"id": 3, "name": "Charlie", "role": "admin"},
        ],
        "products": [
            {"id": 101, "name": "Widget", "price": 9.99},
            {"id": 102, "name": "Gadget", "price": 19.99},
        ],
    }.get(table, [])


class CodeModeContextProvider(BaseContextProvider):
    """Inject a code-mode surface using agent-configured tools."""

    DEFAULT_SOURCE_ID = "code_mode_provider"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        tools: Sequence[FunctionTool] | None = None,
        remove_tools_from_agent: bool = True,
        approval_mode: Literal["always_require", "never_require"] | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            source_id: Unique provider source identifier.

        Keyword Args:
            tools: Additional sandbox-managed tools owned by the provider.
                These are available through ``call_tool(...)`` inside
                ``execute_code`` and are never surfaced to the model as
                separate tools.
            remove_tools_from_agent: When True, remove the
                tools from the model-facing tool list after the provider
                captures them, including tools passed at run time.
            approval_mode: Base approval mode for the provider-managed
                `execute_code` tool. The effective mode is upgraded to the
                strictest mode required by the managed tools for each run.
                Default is evaluated as `never_require`.
        """

        super().__init__(source_id)
        self._provider_tools = collect_tools(tools)
        self._remove_tools_from_agent = remove_tools_from_agent
        self._approval_mode = approval_mode
        self._agent_tools: list[FunctionTool] | None = None
        self._managed_tools: list[FunctionTool] = []
        self._base_signature: tuple[tuple[str, int], ...] = ()
        self._runtime_signature: tuple[tuple[str, int], ...] = ()
        self._module_path = Path(
            os.environ.get(
                "HYPERLIGHT_MODULE", str(Path(__file__).resolve().parents[3] / "src/python_sandbox/python-sandbox.aot")
            )
        )
        if not self._module_path.exists():
            raise RuntimeError(
                "Hyperlight Wasm module not found.\n"
                f"  module: {self._module_path} (MISSING)\n"
                "Build the provisional python-sandbox AOT module first, or set "
                "HYPERLIGHT_MODULE to the correct path."
            )
        self._base_sandbox: Any = None
        self._base_snapshot: Any = None
        self._runtime_sandbox: Any = None
        self._runtime_snapshot: Any = None
        self._sandbox: Any = None
        self._snapshot: Any = None

        self._execute_code_tool = FunctionTool(
            name="execute_code",
            description=(
                "Python code to execute in an isolated sandbox. "
                "Use call_tool(...) inside the code to access other tools."
            ),
            func=self._run_code,
            input_model={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "Python code to execute in an isolated sandbox. "
                            "Use call_tool(...) inside the code to access other tools."
                        ),
                    }
                },
                "required": ["code"],
            },
            approval_mode=self._approval_mode,
        )

    @staticmethod
    def _build_sandbox_and_snapshot(*, tools: Sequence[FunctionTool], module_path: Path) -> tuple[Any, Any]:
        """Build a sandbox and clean snapshot for the given tool set."""
        sandbox = WasmSandbox(module_path=str(module_path))

        for tool_obj in tools:
            sandbox.register_tool(tool_obj.name, tool_obj.invoke)

        sandbox.run("None")
        snapshot = sandbox.snapshot()

        logger.debug("Sandbox initialized and snapshotted.")
        return sandbox, snapshot

    def _initialize_sandbox(
        self,
        *,
        base_tools: Sequence[FunctionTool],
        runtime_tools: Sequence[FunctionTool],
    ) -> None:
        """Initialize or reuse the appropriate base/runtime sandbox snapshot."""

        managed_tools = collect_tools(base_tools, runtime_tools)

        base_signature = _tool_signature(base_tools)
        if base_signature != self._base_signature:
            self._base_signature = base_signature
            self._base_sandbox = None
            self._base_snapshot = None
            self._runtime_signature = ()
            self._runtime_sandbox = None
            self._runtime_snapshot = None

        if self._base_snapshot is None or self._base_sandbox is None:
            self._base_sandbox, self._base_snapshot = self._build_sandbox_and_snapshot(
                tools=base_tools, module_path=self._module_path
            )

        if not runtime_tools:
            self._sandbox = self._base_sandbox
            self._snapshot = self._base_snapshot
            self._managed_tools = managed_tools

        runtime_signature = _tool_signature(runtime_tools)
        if runtime_signature != self._runtime_signature:
            self._runtime_signature = runtime_signature
            self._runtime_sandbox = None
            self._runtime_snapshot = None

        if self._runtime_snapshot is None or self._runtime_sandbox is None:
            # TODO: Derive runtime snapshots from the restored base snapshot once
            # the provisional Hyperlight API makes incremental tool layering practical.
            self._runtime_sandbox, self._runtime_snapshot = self._build_sandbox_and_snapshot(
                tools=managed_tools, module_path=self._module_path
            )

        self._sandbox = self._runtime_sandbox
        self._snapshot = self._runtime_snapshot
        self._managed_tools = managed_tools

    def _run_code(self, *, code: str) -> list[Content]:
        """Restore the sandbox and execute one block of Python code."""

        if self._sandbox is None or self._snapshot is None:
            raise RuntimeError("Sandbox has not been initialized yet.")

        self._sandbox.restore(self._snapshot)
        result = self._sandbox.run(code=code)

        success = bool(getattr(result, "success", False))
        stdout = str(getattr(result, "stdout", "") or "").replace("\r\n", "\n")
        stderr = str(getattr(result, "stderr", "") or "")

        if success:
            logger.debug("execute_code completed.")
            contents: list[Content] = []
            if stdout:
                contents.append(Content.from_text(stdout))
            if stderr:
                contents.append(
                    Content.from_text(
                        f"stderr:\n{stderr}",
                        additional_properties={"stream": "stderr"},
                    )
                )
            return contents or [Content.from_text("Code executed successfully without output.")]

        logger.debug("execute_code failed.")
        error_details = stderr or "Unknown sandbox error"
        return [
            Content.from_text(f"Execution error:\n{error_details}"),
            Content.from_error(message="Execution error", error_details=error_details),
        ]

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:  # noqa: ARG002
        """Inject code-mode instructions and the execute_code tool before each run."""

        if self._agent_tools is None and isinstance(agent, Agent):
            self._agent_tools = collect_tools(agent.default_options.get("tools", []))

            if self._remove_tools_from_agent:
                agent.default_options["tools"] = [
                    tool_obj
                    for tool_obj in agent.default_options.get("tools", [])
                    if getattr(tool_obj, "name", None) == "execute_code"
                ]

        runtime_tools = collect_tools(context.options.get("tools"))
        self._initialize_sandbox(
            base_tools=collect_tools(self._provider_tools, self._agent_tools or []),
            runtime_tools=runtime_tools,
        )
        self._execute_code_tool.approval_mode = _resolve_execute_code_approval_mode(
            base_approval_mode=self._approval_mode,
            tools=self._managed_tools,
        )

        if self._remove_tools_from_agent:
            context.options.pop("tools")

        context.extend_instructions(
            self.source_id,
            _build_code_mode_instructions(
                tools=self._managed_tools,
                tools_visible_to_model=not self._remove_tools_from_agent,
            ),
        )
        context.extend_tools(self.source_id, [self._execute_code_tool])


async def main() -> None:
    """Run the provider-managed code-mode sample."""

    agent = Agent(
        client=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ),
        name="HyperlightCodeModeProviderAgent",
        instructions="You are a helpful assistant.",
        tools=[compute, fetch_data],
        context_providers=[CodeModeContextProvider(approval_mode="never_require")],
    )

    print("=" * 60)
    print("ContextProvider sample")
    print("=" * 60)
    query = (
        "Fetch all users, find admins, multiply 6*7, and print the users, admins, "
        "and multiplication result. Use one execute_code call."
    )
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result.text}")


"""
Sample output (shape only):

Sandbox initialized and snapshotted (...)
============================================================
ContextProvider sample
============================================================
remove_tools_from_agent=True
approval_mode=never_require
User: Fetch all users, find admins, multiply 6*7, and print the users, admins,
and multiplication result. Use one execute_code call.
Agent: ...

Notes:
- Pass tools to `CodeModeContextProvider(tools=[...])` to register sandbox-only
  tools that are available through `call_tool(...)` but never exposed to the
  model as separate tools.
- `remove_tools_from_agent` defaults to `True`, so the provider hides both
  agent-configured and per-run tools from the model-facing tool list unless
  you opt out.
- Set `approval_mode` on `CodeModeContextProvider(...)` to control the approval
  behavior of the provider-managed `execute_code` tool.
- Pass tools to `agent.run(..., tools=runtime_tools)` to expose them as per-run
  tools. The provider reads them from `context.options["tools"]`, registers
  them with the sandbox, and clears them from the run options when removal is
  enabled.
- This sample prioritizes the intended API shape over confirmed Hyperlight
  runtime integration.
"""


if __name__ == "__main__":
    asyncio.run(main())
