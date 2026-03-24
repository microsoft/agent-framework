# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "hyperlight-sandbox",
#     "hyperlight-sandbox-backend-wasm",
#     "hyperlight-sandbox-python-guest",
# ]
# [tool.uv.sources]
# hyperlight-sandbox = { index = "testpypi" }
# hyperlight-sandbox-backend-wasm = { index = "testpypi" }
# hyperlight-sandbox-python-guest = { index = "testpypi" }
# [[tool.uv.index]]
# name = "testpypi"
# url = "https://test.pypi.org/simple/"
# explicit = true
# ///
# Bootstrap manually with:
#   uv pip install --python 3.12 --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple \
#     hyperlight-sandbox hyperlight-sandbox-backend-wasm hyperlight-sandbox-python-guest
# Run with: uv run --python 3.12 samples/02-agents/tools/codeact_context_provider.py
#
# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from textwrap import indent
from typing import Annotated, Any, Literal

from agent_framework import (
    Agent,
    AgentSession,
    BaseContextProvider,
    Content,
    FunctionInvocationContext,
    FunctionTool,
    SessionContext,
    function_middleware,
    tool,
)
from agent_framework._tools import normalize_tools
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

try:
    from hyperlight_sandbox import Sandbox
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "This prototype expects an upstream `hyperlight_sandbox.Sandbox` "
        "implementation. Install the provisional Hyperlight package once it "
        "is available, or update this sample to match the final import path."
    ) from exc

load_dotenv()

# ANSI color helpers for distinguishing output sources.
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_RESET = "\033[0m"


class _ColoredFormatter(logging.Formatter):
    """Dim logger output so it doesn't compete with middleware and main prints."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return f"{_DIM}{msg}{_RESET}"


logging.basicConfig(level=logging.WARNING)
logging.getLogger().handlers[0].setFormatter(
    _ColoredFormatter("[%(asctime)s] %(levelname)s: %(message)s"),
)
logger = logging.getLogger(__name__)


"""This sample demonstrates a ContextProvider-driven Hyperlight CodeAct prototype.

The provider owns sandbox lifecycle and the tools registered within it.
Tools are passed directly to the provider — not the agent — so the model
only sees the single ``execute_code`` tool.

A logging function middleware is registered on the agent to show every tool
invocation (name, arguments, timing, and result) in the console output.

Per-run tools passed to ``agent.run(..., tools=...)`` are also captured by the
provider, registered with the sandbox, and removed from the model-facing tool
list.
"""


def _passthrough_result_parser(result: Any) -> str:
    """Return a Python repr so sandbox code sees native-looking values.

    Using ``repr`` instead of ``json.dumps`` ensures the text can be
    round-tripped back to a native Python value with ``ast.literal_eval``.
    """
    return repr(result)


def _make_sandbox_callback(tool_obj: FunctionTool) -> Callable[..., Any]:
    """Wrap a tool's ``invoke`` so ``call_tool`` returns native Python values.

    ``invoke()`` always returns ``list[Content]``.  This wrapper extracts
    the text, parses it back with ``ast.literal_eval``, and returns a
    single value (not a list) when there is exactly one result item.
    """

    async def _callback(**kwargs: Any) -> Any:
        import ast

        contents = await tool_obj.invoke(**kwargs)
        values: list[Any] = []
        for c in contents:
            if c.text is not None:
                try:
                    values.append(ast.literal_eval(c.text))
                except (ValueError, SyntaxError):
                    values.append(c.text)
        if len(values) == 1:
            return values[0]
        return values

    return _callback


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


def _build_codeact_instructions(
    *,
    tools: Sequence[FunctionTool],
    tools_visible_to_model: bool,
) -> str:
    """Build dynamic CodeAct instructions for the discovered tools."""

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

It runs Python in an isolated sandbox. You do NOT have direct
access to data. The ONLY way to fetch data or perform computations is by
writing Python code via execute_code that calls `call_tool()` inside the
sandbox.

`call_tool` is a built-in global inside the sandbox. No import is needed.

CRITICAL: call_tool takes the tool name as first argument, then KEYWORD
arguments only. Never pass a dict as a positional argument.

{visibility_note}

Available sandbox tools:
{tools_descriptions}

Correct examples:
  result = call_tool("tool_name", keyword=value)
  data = call_tool("fetch_data", table="users")
  x = call_tool("compute", operation="multiply", a=3, b=7)

WRONG — these will fail:
  call_tool("tool_name", {{"keyword": "value"}})   # dict as positional arg
  call_tool("tool_name", "value")                  # positional arg

call_tool returns native Python values (int, float, str, list, dict),
so you can use results directly in subsequent code:
  data = call_tool("fetch_data", table="users")
  total = call_tool("compute", operation="add", a=data[0]["price"], b=data[1]["price"])

Prefer one execute_code call per request when possible.
Do NOT hardcode data that should come from call_tool(...).
"""


class CodeActContextProvider(BaseContextProvider):
    """Inject a CodeAct surface using provider-owned tools.

    Tools passed to the provider are registered with the sandbox and made
    available to the model exclusively through ``execute_code``.  They are
    never added to the model-facing tool list — only ``execute_code`` is.

    Per-run tools passed to ``agent.run(..., tools=...)`` are captured from
    ``context.options["tools"]``, registered with the sandbox for the
    duration of the run, and removed from the model-facing run options.
    """

    DEFAULT_SOURCE_ID = "codeact_provider"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        tools: Sequence[FunctionTool] | None = None,
        approval_mode: Literal["always_require", "never_require"] | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            source_id: Unique provider source identifier.

        Keyword Args:
            tools: Sandbox-managed tools owned by the provider.
                These are available through ``call_tool(...)`` inside
                ``execute_code`` and are never surfaced to the model as
                separate tools.
            approval_mode: Base approval mode for the provider-managed
                `execute_code` tool. The effective mode is upgraded to the
                strictest mode required by the managed tools for each run.
                Default is evaluated as `never_require`.
        """

        super().__init__(source_id)
        self._provider_tools = collect_tools(tools)
        for t in self._provider_tools:
            t.result_parser = _passthrough_result_parser
        self._approval_mode = approval_mode
        self._managed_tools: list[FunctionTool] = []
        self._base_signature: tuple[tuple[str, int], ...] = ()
        self._runtime_signature: tuple[tuple[str, int], ...] = ()
        self._module_path = "python_guest.path"
        self._base_sandbox: Sandbox | None = None
        self._base_snapshot: Any = None
        self._runtime_sandbox: Sandbox | None = None
        self._runtime_snapshot: Any = None
        self._sandbox: Sandbox | None = None
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
    def _build_sandbox_and_snapshot(*, tools: Sequence[FunctionTool], module_path: str) -> tuple[Sandbox, Any]:
        """Build a sandbox and clean snapshot for the given tool set."""
        sandbox = Sandbox(backend="wasm", module_path=module_path)

        for tool_obj in tools:
            sandbox.register_tool(tool_obj.name, _make_sandbox_callback(tool_obj))

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

        if result.success:
            logger.debug("execute_code completed.")
            contents: list[Content] = []
            if result.stdout:
                contents.append(Content.from_text(result.stdout.strip()))
            if result.stderr:
                contents.append(
                    Content.from_text(
                        f"stderr:\n{result.stderr.strip()}",
                        additional_properties={"stream": "stderr"},
                    )
                )
            return contents or [Content.from_text("Code executed successfully without output.")]

        logger.debug("execute_code failed.")
        error_details = result.stderr.strip() if result.stderr else "Unknown sandbox error"
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
        """Inject CodeAct instructions and the execute_code tool before each run."""

        # Capture and remove per-run tools so they are only available in the sandbox.
        runtime_tools = collect_tools(context.options.pop("tools", None))
        for t in runtime_tools:
            t.result_parser = _passthrough_result_parser
        self._initialize_sandbox(
            base_tools=self._provider_tools,
            runtime_tools=runtime_tools,
        )
        self._execute_code_tool.approval_mode = _resolve_execute_code_approval_mode(
            base_approval_mode=self._approval_mode,
            tools=self._managed_tools,
        )

        context.extend_instructions(
            self.source_id,
            _build_codeact_instructions(
                tools=self._managed_tools,
                tools_visible_to_model=False,
            ),
        )
        context.extend_tools(self.source_id, [self._execute_code_tool])


# 1. Define a logging function middleware to observe tool invocations.
@function_middleware
async def log_function_calls(
    context: FunctionInvocationContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Log every tool call with readable code output and timing."""
    import time

    func_name = context.function.name
    args = context.arguments if isinstance(context.arguments, dict) else {}

    # For execute_code, print the generated code as a readable block.
    if func_name == "execute_code" and "code" in args:
        print(f"\n{_YELLOW}{'─' * 60}")
        print("▶ execute_code")
        print(f"{'─' * 60}{_RESET}")
        print(args["code"])
        print(f"{_YELLOW}{'─' * 60}{_RESET}")
    else:
        print(f"\n{_YELLOW}▶ {func_name}({', '.join(f'{k}={v!r}' for k, v in args.items())}){_RESET}")

    start = time.perf_counter()
    await call_next()
    elapsed = time.perf_counter() - start

    # Show the result concisely — full stdout for execute_code, repr for others.
    result = context.result
    if func_name == "execute_code" and isinstance(result, list):
        for item in result:
            text = getattr(item, "text", None)
            if text:
                print(f"{_GREEN}stdout:\n{text}{_RESET}")
    else:
        print(f"{_YELLOW}◀ {func_name} → {result!r}{_RESET}")

    print(f"{_DIM}  ({elapsed:.4f}s){_RESET}")


@tool(approval_mode="never_require")
def compute(
    operation: Annotated[
        Literal["add", "subtract", "multiply", "divide"], "Math operation: add, subtract, multiply, or divide."
    ],
    a: Annotated[float, "First numeric operand."],
    b: Annotated[float, "Second numeric operand."],
) -> float:
    """Perform a math operation, use this function instead of raw code, because it is safer."""

    logger.warning("compute called with operation=%r, a=%r, b=%r", operation, a, b)

    operations = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b else float("inf"),
    }
    return operations.get(operation, 0.0)


@tool(approval_mode="never_require")
async def fetch_data(
    table: Annotated[str, "Name of the simulated table to query."],
) -> list[dict[str, Any]]:
    """Fetch records from a named table.

    There are two tables, with the columns shown below:
    - users: id, name, role
    - products: id, name, price
    """

    logger.warning("fetch_data called with table=%r", table)

    await asyncio.sleep(0.5)  # Simulate some latency

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


async def main() -> None:
    """Run the provider-managed CodeAct sample."""

    # Tools are passed to the provider (not the agent) so they are only
    # available inside the sandbox via call_tool(...) and never appear as
    # separate model-facing tools.
    agent = Agent(
        client=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ),
        name="CodeActProviderAgent",
        instructions="You are a helpful assistant.",
        context_providers=[
            CodeActContextProvider(tools=[compute, fetch_data], approval_mode="never_require"),
        ],
        middleware=[log_function_calls],
    )

    print(f"{_CYAN}{'=' * 60}")
    print("CodeAct ContextProvider sample")
    print(f"{'=' * 60}{_RESET}")
    query = (
        "Fetch all users, find admins, multiply 7*(3*2), and print the users, admins, "
        "and multiplication result. Use the execute_code call, and try to do as much as possible inside the sandbox with call_tool(...) instead of in raw code outside."
    )
    print(f"{_CYAN}User: {query}{_RESET}")
    result = await agent.run(query)
    print(f"{_CYAN}Agent: {result.text}{_RESET}")


"""
Sample output (shape only):

============================================================
CodeAct ContextProvider sample
============================================================
User: Fetch all users, find admins, multiply 6*7, ...

────────────────────────────────────────────────────────────
▶ execute_code
────────────────────────────────────────────────────────────
users = call_tool("fetch_data", table="users")
admins = [u for u in users if u["role"] == "admin"]
result = call_tool("compute", operation="multiply", a=6, b=7)
print("Users:", users)
print("Admins:", admins)
print("6 * 7 =", result)
────────────────────────────────────────────────────────────
stdout:
Users: [...]
Admins: [...]
6 * 7 = 42.0
  (0.0452s)
Agent: ...

Notes:
- Tools are passed to `CodeActContextProvider(tools=[...])`, NOT to the agent.
  This ensures they are only available inside the sandbox via `call_tool(...)`.
  The model only sees the `execute_code` tool.
- The logging middleware prints the model-generated code as a readable block
  and shows its stdout, so you can trace exactly what the agent does.
- Set `approval_mode` on `CodeActContextProvider(...)` to control the approval
  behavior of the provider-managed `execute_code` tool.
- Pass tools to `agent.run(..., tools=runtime_tools)` to expose them as per-run
  sandbox tools. The provider captures them from `context.options["tools"]`,
  registers them with the sandbox, and removes them from the model-facing run
  options.
- This sample prioritizes the intended API shape over confirmed Hyperlight
  runtime integration.
"""


if __name__ == "__main__":
    asyncio.run(main())
