# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-foundry",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/02-agents/middleware/hol_guard_middleware.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import logging
import shutil
from collections.abc import Awaitable, Callable, Mapping
from enum import Enum
from random import randint
from typing import Annotated, Any

from agent_framework import (
    Agent,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareFailure,
    tool,
)
from pydantic import BaseModel, Field

"""
Official HOL Guard FunctionMiddleware example for protected tool calls (issue #7833).

HOLGuardMiddleware evaluates the tool name and validated arguments in
FunctionInvocationContext before call_next() and only proceeds on an explicit allow verdict
from HOL Guard (https://github.com/hashgraph-online/hol-guard).

Unlike ATRValidationMiddleware in this folder, which raises MiddlewareTermination on a match,
this sample raises MiddlewareFailure on deny, review-required, AND Guard-unavailable/error.
MiddlewareFailure is the framework's explicit fail-closed escape (see its docstring in
agent_framework's middleware module): it cancels the in-flight tool-call batch and propagates
to the caller of Agent.run() rather than letting the loop continue -- matching the issue's
"terminate before the wrapped tool executes" requirement for all three non-allow outcomes,
not just an outright deny.

The real HOL Guard engine is invoked locally through its documented, side-effect-free CLI
contract (`hol-guard command test <call> --json`; see "Inspect command protection without
running it" in https://github.com/hashgraph-online/hol-guard). hol-guard is intentionally NOT
listed in this file's PEP 723 dependencies -- it is not imported as a Python package here,
only shelled out to. Install it separately with `pipx install hol-guard` for real protection.
Without it on PATH, or if the call errors, the middleware fails closed by default. Pass
offline_fallback=True only for local demo/dev use without the real engine installed; it applies
a small built-in deny-list that is far weaker than actual HOL Guard.

OPEN QUESTION (resolve before merging): hol-guard's `command test` contract is documented for
shell-command-shaped strings, not typed (function_name, arguments) tool calls. This sample
renders a call as a single command-like string as a best-effort mapping onto that contract.
Confirm the intended integration surface for arbitrary FunctionMiddleware calls with the HOL
Guard maintainers (see discussion on #7833) before treating this as final.

Provider imports (FoundryChatClient, AzureCliCredential) are deferred to main() rather than
imported at module level, so HOLGuardMiddleware and evaluate_with_hol_guard stay importable
and unit-testable without the agent-framework-foundry/azure-identity extras present.
"""

logger = logging.getLogger(__name__)

_CLI_NAME = "hol-guard"
_OFFLINE_DENY_SUBSTRINGS = ("drop table", "rm -rf", "delete_production", "sudo ", "curl|sh")


class GuardDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


def _call_to_command_string(function_name: str, arguments: BaseModel | Mapping[str, Any]) -> str:
    """Render a tool call as a single command-shaped string for `hol-guard command test`."""
    values = arguments.model_dump() if isinstance(arguments, BaseModel) else dict(arguments)
    args_text = " ".join(f"{key}={value!r}" for key, value in values.items())
    return f"{function_name} {args_text}".strip()


def _offline_check(command_string: str) -> tuple[GuardDecision, str]:
    lowered = command_string.lower()
    for pattern in _OFFLINE_DENY_SUBSTRINGS:
        if pattern in lowered:
            return GuardDecision.DENY, f"offline fallback matched '{pattern}'"
    return GuardDecision.ALLOW, "offline fallback: no match (reduced protection, real engine not installed)"


async def evaluate_with_hol_guard(
    function_name: str,
    arguments: BaseModel | Mapping[str, Any],
    *,
    offline_fallback: bool = False,
    timeout_seconds: float = 5.0,
) -> tuple[GuardDecision, str]:
    """Classify a tool call with the real, local hol-guard engine. Fails closed by default:
    a missing CLI or an evaluation error returns UNAVAILABLE/ERROR, never ALLOW, unless
    offline_fallback=True.
    """
    cli_path = shutil.which(_CLI_NAME)
    command_string = _call_to_command_string(function_name, arguments)

    if cli_path is None:
        if offline_fallback:
            return _offline_check(command_string)
        return GuardDecision.UNAVAILABLE, f"{_CLI_NAME} CLI not found on PATH"

    try:
        proc = await asyncio.create_subprocess_exec(
            cli_path,
            "command",
            "test",
            command_string,
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        payload = json.loads(stdout)
        decision = GuardDecision(payload.get("decision", "deny"))
        return decision, payload.get("reason", payload.get("summary", ""))
    except Exception as exc:  # noqa: BLE001 - any failure here must fail closed
        if offline_fallback:
            return _offline_check(command_string)
        return GuardDecision.ERROR, f"{_CLI_NAME} evaluation failed: {exc}"


class HOLGuardMiddleware(FunctionMiddleware):
    """Gates tool calls behind a HOL Guard verdict; fails closed on anything but allow."""

    def __init__(self, *, offline_fallback: bool = False, timeout_seconds: float = 5.0) -> None:
        self._offline_fallback = offline_fallback
        self._timeout_seconds = timeout_seconds
        if shutil.which(_CLI_NAME) is None:
            logger.warning(
                "%s CLI not found on PATH. Install with `pipx install hol-guard` for real "
                "protection, or pass offline_fallback=True for local demo/dev use.",
                _CLI_NAME,
            )

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        decision, reason = await evaluate_with_hol_guard(
            context.function.name,
            context.arguments,
            offline_fallback=self._offline_fallback,
            timeout_seconds=self._timeout_seconds,
        )
        if decision is GuardDecision.ALLOW:
            logger.info("[HOLGuardMiddleware] Tool '%s' allowed by HOL Guard.", context.function.name)
            await call_next()
            return

        logger.warning(
            "[HOLGuardMiddleware] Blocked tool '%s': verdict=%s reason=%s",
            context.function.name,
            decision.value,
            reason,
        )
        # Fail closed: MiddlewareFailure, not MiddlewareTermination -- see module docstring.
        raise MiddlewareFailure(f"HOL Guard {decision.value} for tool '{context.function.name}': {reason}")


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


@tool(approval_mode="never_require")
def delete_production_database(
    confirm: Annotated[bool, Field(description="Confirm the deletion.")],
) -> str:
    """Deletes the production database. Obviously dangerous -- used to demo a HOL Guard deny."""
    return "Database deleted."  # pragma: no cover - should never actually run


async def main() -> None:
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import AzureCliCredential
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    print("=== HOL Guard Middleware Example ===")

    # For authentication, run `az login` in a terminal or replace AzureCliCredential with your
    # preferred authentication option.
    async with (
        AzureCliCredential() as credential,
        Agent(
            client=FoundryChatClient(credential=credential),
            name="OpsAgent",
            instructions="You are a helpful assistant with access to weather and admin tools.",
            tools=[get_weather, delete_production_database],
            # offline_fallback=True lets this demo run without the real hol-guard engine
            # installed. In production, omit it (default False) so an unavailable Guard fails
            # closed instead of falling back to the much weaker built-in deny-list.
            middleware=[HOLGuardMiddleware(offline_fallback=True)],
        ) as agent,
    ):
        print("\n--- Benign request ---")
        query = "What's the weather like in Tokyo?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text if result.text else 'No response'}\n")

        print("--- Dangerous tool call ---")
        query = "Delete the production database, confirm=true."
        print(f"User: {query}")
        try:
            result = await agent.run(query)
            print(f"Agent: {result.text if result and result.text else 'No response'}\n")
        except MiddlewareFailure as exc:
            print(f"Agent run aborted by middleware: {exc}\n")


if __name__ == "__main__":
    asyncio.run(main())
