# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "dhms-agentfuse==3.7.3",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/02-agents/middleware/agentfuse_function_middleware.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from agent_framework import FunctionInvocationContext, FunctionMiddleware, tool
from dhms_agentfuse import RuntimeGuard, RuntimeGuardDecision, ToolCallRequest
from pydantic import BaseModel


def _arguments_as_mapping(arguments: BaseModel | Mapping[str, Any]) -> Mapping[str, Any]:
    """Return validated tool arguments in the shape AgentFuse expects."""
    return arguments.model_dump() if isinstance(arguments, BaseModel) else arguments


def _blocked_result(
    *,
    tool_call_id: str | None,
    tool_name: str,
    reason_code: str,
) -> dict[str, str | bool | None]:
    """Build a host-visible terminal result without exposing tool arguments."""
    return {
        "type": "agentfuse_policy_result",
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "decision": "block",
        "reason_code": reason_code,
        "execution_outcome": "not_executed",
        "handler_invoked": False,
    }


class AgentFuseFunctionMiddleware(FunctionMiddleware):
    """Evaluate AgentFuse immediately before Microsoft Agent Framework dispatches a tool."""

    def __init__(self, guard: RuntimeGuard) -> None:
        self.guard = guard

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        raw_call_id = context.metadata.get("call_id")
        if not isinstance(raw_call_id, str) or not raw_call_id:
            context.result = _blocked_result(
                tool_call_id=None,
                tool_name=context.function.name,
                reason_code="missing_tool_call_id",
            )
            return

        try:
            decision = await self.guard.aevaluate(
                ToolCallRequest(
                    tool_call_id=raw_call_id,
                    tool_name=context.function.name,
                    arguments=_arguments_as_mapping(context.arguments),
                    safe_metadata={"integration": "microsoft-agent-framework"},
                )
            )
        except Exception:
            context.result = _blocked_result(
                tool_call_id=raw_call_id,
                tool_name=context.function.name,
                reason_code="guard_evaluation_failed",
            )
            return

        context.metadata["agentfuse_decision"] = decision
        if decision.action == "block":
            context.result = _blocked_result(
                tool_call_id=decision.tool_call_id,
                tool_name=decision.tool_name,
                reason_code=decision.reason_code,
            )
            return

        await call_next()


async def invoke_with_middleware(
    middleware: AgentFuseFunctionMiddleware,
    *,
    tool_call_id: str,
    tool_name: str,
    handler_counter: dict[str, int],
) -> tuple[object, RuntimeGuardDecision | None]:
    """Exercise the middleware and the framework's real ``FunctionTool.invoke`` path."""

    @tool(name=tool_name, approval_mode="never_require")
    def protected_tool(value: str) -> str:
        handler_counter["count"] += 1
        return f"handled:{value}"

    context = FunctionInvocationContext(
        function=protected_tool,
        arguments={"value": "fixture"},
        metadata={"call_id": tool_call_id},
    )

    async def call_next() -> None:
        context.result = await protected_tool.invoke(
            arguments=context.arguments,
            context=context,
            tool_call_id=tool_call_id,
            skip_parsing=True,
        )

    await middleware.process(context, call_next)
    decision = context.metadata.get("agentfuse_decision")
    if decision is not None and not isinstance(decision, RuntimeGuardDecision):
        raise TypeError("AgentFuse middleware stored an unexpected decision type.")
    return context.result, decision


class FailingRuntimeGuard(RuntimeGuard):
    """A deterministic guard used to prove fail-closed behavior."""

    async def aevaluate(self, tool_call: ToolCallRequest) -> RuntimeGuardDecision:
        raise RuntimeError("simulated guard failure")


async def run_contract_verification() -> dict[str, object]:
    """Run allow, block, and guard-failure cases without a model or external service."""
    allow_counter = {"count": 0}
    allow_middleware = AgentFuseFunctionMiddleware(RuntimeGuard(allow_tools={"safe_read"}))
    allow_result, allow_decision = await invoke_with_middleware(
        allow_middleware,
        tool_call_id="call-allow-1",
        tool_name="safe_read",
        handler_counter=allow_counter,
    )

    block_counter = {"count": 0}
    block_middleware = AgentFuseFunctionMiddleware(RuntimeGuard(deny_tools={"dangerous_write"}))
    block_result, block_decision = await invoke_with_middleware(
        block_middleware,
        tool_call_id="call-block-1",
        tool_name="dangerous_write",
        handler_counter=block_counter,
    )

    failure_counter = {"count": 0}
    failure_middleware = AgentFuseFunctionMiddleware(FailingRuntimeGuard())
    failure_result, failure_decision = await invoke_with_middleware(
        failure_middleware,
        tool_call_id="call-failure-1",
        tool_name="safe_read",
        handler_counter=failure_counter,
    )

    if allow_result != "handled:fixture" or allow_counter["count"] != 1:
        raise AssertionError("Allowed tool call did not execute exactly once.")
    if allow_decision is None or allow_decision.action != "allow":
        raise AssertionError("Allowed tool call did not retain its AgentFuse decision.")
    if not isinstance(block_result, dict):
        raise AssertionError("Blocked tool call did not return a terminal result.")
    if block_result["tool_call_id"] != "call-block-1" or block_result["execution_outcome"] != "not_executed":
        raise AssertionError("Blocked tool call did not preserve its terminal non-execution contract.")
    if block_counter["count"] != 0 or block_decision is None or block_decision.action != "block":
        raise AssertionError("Blocked tool call reached dispatch or lost its AgentFuse decision.")
    if not isinstance(failure_result, dict) or failure_result["reason_code"] != "guard_evaluation_failed":
        raise AssertionError("Guard failure did not produce the expected fail-closed result.")
    if failure_counter["count"] != 0 or failure_decision is not None:
        raise AssertionError("Guard failure reached dispatch or retained a nonexistent decision.")

    return {
        "allow_handler_count": allow_counter["count"],
        "block_handler_count": block_counter["count"],
        "guard_failure_handler_count": failure_counter["count"],
        "allow_tool_call_id": allow_decision.tool_call_id,
        "block_tool_call_id": block_decision.tool_call_id,
    }


async def main() -> None:
    """Print the deterministic contract proof."""
    summary = await run_contract_verification()
    for key, value in summary.items():
        print(f"{key}={value}")
    print("AGENTFUSE_AGENT_FRAMEWORK_MIDDLEWARE_PASS")


if __name__ == "__main__":
    asyncio.run(main())
