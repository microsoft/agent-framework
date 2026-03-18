# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from textwrap import indent
from typing import Annotated, Any

from agent_framework import Agent, Content, FunctionTool, tool
from agent_framework._tools import normalize_tools
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

logger = logging.getLogger(__name__)

"""This sample demonstrates a direct-tool Hyperlight code-mode prototype.

The sample creates an `Agent(client=AzureOpenAIResponsesClient(...), ...)` with a
primary `execute_code` tool plus schema-visible tools. It also supports
per-run runtime tools by registering them with the sandbox before the run and
passing them through `agent.run(..., tools=runtime_tools)`.
"""

DEFAULT_PROMPT = (
    "Fetch all users, find admins, multiply 6*7, and print the users, admins, "
    "and multiplication result. Use one execute_code call."
)

_SIMULATED_DATA: dict[str, list[dict[str, Any]]] = {
    "users": [
        {"id": 1, "name": "Alice", "role": "admin"},
        {"id": 2, "name": "Bob", "role": "user"},
        {"id": 3, "name": "Charlie", "role": "admin"},
    ],
    "products": [
        {"id": 101, "name": "Widget", "price": 9.99},
        {"id": 102, "name": "Gadget", "price": 19.99},
    ],
}


def _repo_root() -> Path:
    """Return the Python repo root used to resolve the default sandbox module path."""

    return Path(__file__).resolve().parents[3]


def _default_module_path() -> Path:
    """Return the provisional default path for the Hyperlight AOT module."""

    return _repo_root() / "src/python_sandbox/python-sandbox.aot"


def collect_tools(*tool_groups: Any) -> list[FunctionTool]:
    """Normalize and collect unique ``FunctionTool`` instances, excluding execute_code."""

    tools: list[FunctionTool] = []
    seen_names: set[str] = set()

    for tool_group in tool_groups:
        normalized_group: Sequence[Any]
        if isinstance(tool_group, Sequence) and not isinstance(tool_group, (str, bytes, bytearray)) and all(
            isinstance(tool_obj, FunctionTool) for tool_obj in tool_group
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


def build_code_mode_instructions(
    *,
    tools: Sequence[FunctionTool],
    tools_visible_to_model: bool,
) -> str:
    """Build dynamic code-mode instructions for the discovered tools."""

    if tools:
        callback_lines = "\n\n".join(
            [
                f"- `{tool_obj.name}`\n"
                f"  Description: {str(tool_obj.description or '').strip() or 'No description provided.'}\n"
                "  Parameters:\n"
                f"{indent(json.dumps(tool_obj.parameters(), indent=2, sort_keys=True), '    ')}"
                for tool_obj in tools
            ]
        )
    else:
        callback_lines = "- No tools are currently registered inside the sandbox."

    visibility_note = (
        "The tools listed below may also appear as normal tools, but you should still prefer "
        "execute_code and call them from inside the sandbox."
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
{callback_lines}

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

    return WasmSandbox(module_path=str(module_path))


class CodeModeSandboxManager:
    """Manage the provisional Hyperlight sandbox lifecycle for this sample."""

    def __init__(self, *, module_path: Path | None = None) -> None:
        """Initialize the sandbox manager."""

        self._module_path = module_path or Path(os.environ.get("HYPERLIGHT_MODULE", str(_default_module_path())))
        self._tools: list[FunctionTool] = []
        self._callback_signature: tuple[tuple[str, int], ...] = ()
        self._sandbox: Any = None
        self._snapshot: Any = None

    def set_tools(self, tools: Sequence[FunctionTool]) -> None:
        """Set the tools that should be registered with the sandbox."""

        signature = tuple((tool_obj.name, id(tool_obj)) for tool_obj in tools)
        if signature == self._callback_signature:
            return

        self._tools = list(tools)
        self._callback_signature = signature
        self._sandbox = None
        self._snapshot = None

    def initialize(self) -> None:
        """Initialize the sandbox once and capture a reusable clean snapshot."""

        if self._sandbox is not None and self._snapshot is not None:
            return

        if not self._module_path.exists():
            raise RuntimeError(
                "Hyperlight Wasm module not found.\n"
                f"  module: {self._module_path} (MISSING)\n"
                "Build the provisional python-sandbox AOT module first, or set "
                "HYPERLIGHT_MODULE to the correct path."
            )

        self._sandbox = _create_wasm_sandbox(module_path=self._module_path)

        for tool_obj in self._tools:
            self._sandbox.register_tool(tool_obj.name, tool_obj.invoke)

        self._sandbox.run("None")
        self._snapshot = self._sandbox.snapshot()

        logger.debug("Sandbox initialized and snapshotted.")

    def run_code(self, *, code: str) -> list[Content]:
        """Restore the sandbox and execute one block of Python code."""

        if self._sandbox is None or self._snapshot is None:
            raise RuntimeError("Sandbox has not been initialized yet.")

        logger.debug("--- Model generated code ---\n%s\n--- end ---\n", code)

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

    return _SIMULATED_DATA.get(table, [])


async def main() -> None:
    """Run the direct-tool code-mode sample."""

    load_dotenv()

    runtime_tools: list[Any] = []
    sandbox_manager = CodeModeSandboxManager()

    @tool(name="execute_code", approval_mode="never_require")
    async def execute_code(
        code: Annotated[
            str,
            Field(
                description=(
                    "Python code to execute in an isolated Hyperlight Wasm sandbox. "
                    "Use call_tool(...) inside the code to access registered host callbacks."
                )
            ),
        ],
    ) -> list[Content]:
        """Execute code inside the provisional sandbox wrapper."""

        return sandbox_manager.run_code(code=code)

    agent = Agent(
        client=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ),
        name="HyperlightCodeModeToolAgent",
        instructions="Temporary instructions replaced before the run.",
        tools=[execute_code, compute, fetch_data],
    )

    tools = collect_tools(agent.default_options.get("tools", []), runtime_tools)
    sandbox_manager.set_tools(tools)
    sandbox_manager.initialize()
    agent.default_options["instructions"] = build_code_mode_instructions(
        tools=tools,
        tools_visible_to_model=True,
    )

    logger.debug("%s", "=" * 60)
    logger.debug("Direct tool sample")
    logger.debug("%s", "=" * 60)
    logger.debug("runtime_tool_count=%s", len(runtime_tools))
    logger.debug("User: %s", DEFAULT_PROMPT)
    result = await agent.run(DEFAULT_PROMPT, tools=runtime_tools)
    logger.debug("Agent: %s\n", result)


"""
Sample output (shape only):

Sandbox initialized and snapshotted (...)
============================================================
Direct tool sample
============================================================
runtime_tool_count=0
User: Fetch all users, find admins, multiply 6*7, and print the users, admins,
and multiplication result. Use one execute_code call.
Agent: ...

Notes:
- Add tools to `runtime_tools` before calling `agent.run(...)` to expose them as
  per-run tools and sandbox callbacks.
- This sample prioritizes the intended API shape over confirmed Hyperlight
  runtime integration.
"""


if __name__ == "__main__":
    asyncio.run(main())
