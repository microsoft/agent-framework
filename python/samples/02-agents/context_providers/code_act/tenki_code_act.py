# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable

from agent_framework import Agent, FunctionInvocationContext, function_middleware
from agent_framework.foundry import FoundryChatClient
from agent_framework_tenki import TenkiCodeActProvider
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""This sample demonstrates the Tenki CodeAct provider.

``TenkiCodeActProvider`` gives the model an ``execute_code`` tool that runs
Python inside a Tenki managed Linux micro-VM — a real userland with ``apt``,
``subprocess``, and a persistent filesystem across ``execute_code`` calls. The
provider mints a fresh sandbox per agent run and terminates it in ``after_run``,
so state does not leak across runs.

The sample task exercises Linux-only capabilities (a subprocess pipeline into
``awk``) that in-process CodeAct backends can't run. See sibling
``monty_code_act.py`` for the Monty-backed provider, which trades Linux userland
for zero-provisioning cost.

Note: ``agent-framework-tenki`` is an alpha package and is not yet part of
``agent-framework[all]``. Install it explicitly with:

    pip install agent-framework agent-framework-tenki --pre

It is imported as ``agent_framework_tenki`` (no lazy-loading namespace yet).
Requires ``TENKI_API_KEY``; also ``TENKI_PROJECT_ID`` when the key spans
multiple projects. See https://tenki.cloud/docs/sandbox/quick-start-sandbox.
"""

load_dotenv()

_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_DIM = "\033[2m"
_RESET = "\033[0m"


class _ColoredFormatter(logging.Formatter):
    """Dim logger output so it does not compete with sample prints."""

    def format(self, record: logging.LogRecord) -> str:
        return f"{_DIM}{super().format(record)}{_RESET}"


logging.basicConfig(level=logging.WARNING)
logging.getLogger().handlers[0].setFormatter(
    _ColoredFormatter("[%(asctime)s] %(levelname)s: %(message)s"),
)


@function_middleware
async def log_function_calls(
    context: FunctionInvocationContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Log tool calls, including readable execute_code blocks."""
    function_name = context.function.name
    arguments = context.arguments if isinstance(context.arguments, dict) else {}

    if function_name == "execute_code" and "code" in arguments:
        print(f"\n{_YELLOW}{'─' * 60}")
        print("▶ execute_code")
        print(f"{'─' * 60}{_RESET}")
        print(arguments["code"])
        print(f"{_YELLOW}{'─' * 60}{_RESET}")
    else:
        pairs = ", ".join(f"{name}={value!r}" for name, value in arguments.items())
        print(f"\n{_YELLOW}▶ {function_name}({pairs}){_RESET}")

    start = time.perf_counter()
    await call_next()
    elapsed = time.perf_counter() - start

    result = context.result
    if function_name == "execute_code" and isinstance(result, list):
        for output in result:
            if output.type == "text" and output.text:
                print(f"{_GREEN}stdout:\n{output.text}{_RESET}")
            elif output.type == "error" and output.error_details:
                print(f"{_YELLOW}stderr:\n{output.error_details}{_RESET}")
    else:
        print(f"{_YELLOW}◀ {function_name} → {result!r}{_RESET}")

    print(f"{_DIM}  ({elapsed:.4f}s){_RESET}")


async def main() -> None:
    """Run the Tenki CodeAct provider sample."""
    # 1. Create the Tenki-backed provider. Explicit ``sandbox_name`` becomes the
    #    prefix for run-scoped sandboxes (e.g. "tenki-codeact-sample-<8-hex>"),
    #    making them easy to identify in the Tenki dashboard.
    async with TenkiCodeActProvider(sandbox_name="tenki-codeact-sample") as codeact:
        # 2. Create the client and the agent.
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                model=os.environ["FOUNDRY_MODEL"],
                credential=AzureCliCredential(),
            ),
            name="TenkiCodeActProviderAgent",
            instructions="You are a helpful assistant.",
            context_providers=[codeact],
            middleware=[log_function_calls],
        )

        # 3. Run a task that exercises the Linux userland Tenki gives us —
        #    a real subprocess pipeline into ``awk``, and file persistence
        #    across two ``execute_code`` calls.
        query = (
            "Using execute_code, do this in TWO calls: "
            "(1) write the numbers 1..100, one per line, to /tmp/numbers.txt "
            "and print 'wrote'. "
            "(2) shell out to `awk` via `subprocess.run(['awk', ...])` to sum "
            "the squares of every number in /tmp/numbers.txt, then print the "
            "result as 'sum_of_squares=<n>'."
        )
        print(f"{_CYAN}{'=' * 60}")
        print("Tenki CodeAct provider sample")
        print(f"{'=' * 60}{_RESET}")
        print(f"{_CYAN}User: {query}{_RESET}")
        result = await agent.run(query)
        print(f"{_CYAN}Agent: {result.text}{_RESET}")


"""
Sample output (shape only):

============================================================
Tenki CodeAct provider sample
============================================================
User: Using execute_code, do this in TWO calls: ...

────────────────────────────────────────────────────────────
▶ execute_code
────────────────────────────────────────────────────────────
with open('/tmp/numbers.txt', 'w') as f:
    for n in range(1, 101):
        f.write(f"{n}\n")
print('wrote')
────────────────────────────────────────────────────────────
stdout:
wrote
  (3.5xxx s)   # first call pays the sandbox-provision cost

────────────────────────────────────────────────────────────
▶ execute_code
────────────────────────────────────────────────────────────
import subprocess
result = subprocess.run(
    ['awk', '{s += $1 * $1} END {print s}', '/tmp/numbers.txt'],
    capture_output=True, text=True, check=True,
)
print(f"sum_of_squares={result.stdout.strip()}")
────────────────────────────────────────────────────────────
stdout:
sum_of_squares=338350
  (0.5xxx s)   # second call reuses the same sandbox

Agent: The sum of squares from 1 to 100 is 338350.
"""


if __name__ == "__main__":
    asyncio.run(main())
