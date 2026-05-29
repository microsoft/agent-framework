# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Agent,
    AgentLoopMiddleware,
    AgentResponse,
    AgentSession,
    Content,
    TodoProvider,
    todos_remaining,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent Loop Middleware

This sample demonstrates ``AgentLoopMiddleware`` — a single, configurable middleware that re-runs an
agent in a loop. It covers the three common patterns through one class:

1. Ralph loop      — no fixed exit criteria; keep asking the agent for more, bounded by
                     ``max_iterations``. This sample also shows Ralph feedback tracking:
                     ``record_feedback`` logs per-iteration progress that is fed into the next
                     pass, ``fresh_context`` restarts each pass from the original task plus the
                     log, and ``is_complete`` stops early when the agent signals completion.
2. Callable        — a ``should_continue`` predicate decides whether to loop again. Here it is paired
                     with a ``TodoProvider`` via the ``todos_remaining`` helper, so the agent keeps
                     working while it still has open todo items.
3. ChatClient judge — a second chat client decides (via a ``JudgeVerdict`` structured output)
   whether the original request was answered; the
                     loop continues while the answer is "no".
4. Approval handling — `on_approval_request` auto-resolves function-approval requests via a callable,
                     so a looped agent does not stall waiting for human approval.

In every case ``next_message`` controls the input for the next iteration (it defaults to a short
"continue" nudge).

The first three patterns each have a convenience factory that exposes only the relevant arguments:
``AgentLoopMiddleware.ralph(...)``, ``AgentLoopMiddleware.with_predicate(...)`` and
``AgentLoopMiddleware.with_judge(...)``. They all forward to the full ``AgentLoopMiddleware(...)``
constructor, which remains available for advanced or combined configurations (such as the approval
handling shown below).

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""


async def ralph_loop(client: FoundryChatClient) -> None:
    """Pattern 1: a "Ralph" loop with feedback tracking and a completion signal."""
    print("\n=== 1. Ralph loop (feedback tracking + completion signal, capped at 5 iterations) ===")

    # 1. ``record_feedback`` captures a short progress entry each iteration. It is called with the
    #    loop keyword args; the ``progress`` kwarg holds the entries recorded so far. Returning a
    #    string appends it to the log (returning None falls back to the response text). The
    #    accumulated log is injected into the next iteration's input so the agent builds on prior work.
    def record_feedback(*, iteration: int, last_result: AgentResponse, **kwargs: object) -> str:
        return f"iteration {iteration}: {last_result.text.strip()[:80]}"

    # 2. ``is_complete`` stops the loop early when the agent signals it is done. A string is
    #    substring-matched against the last response; a callable receives the loop kwargs instead.
    #    ``fresh_context=True`` restarts each pass from the original task plus the progress log,
    #    following Ralph's "fresh context per iteration" principle.
    loop = AgentLoopMiddleware.ralph(
        max_iterations=5,
        record_feedback=record_feedback,
        fresh_context=True,
        is_complete="<promise>COMPLETE</promise>",
    )

    # 3. Attach the middleware to the agent.
    agent = Agent(
        client=client,
        name="ralph",
        instructions=(
            "You are iteratively refining a product name for a note-taking app. Each turn, build on the "
            "progress log: propose an improved candidate with a short reason. When you are confident the "
            "name is final, end your message with the exact marker <promise>COMPLETE</promise>."
        ),
        middleware=[loop],
    )

    # 4. Run once; the middleware drives the iterations, feeding progress forward until the agent
    #    emits the completion marker or the iteration cap is reached.
    response = await agent.run("Suggest a name for a note-taking app.")
    print(f"Final response:\n{response.text}")


async def todo_loop(client: FoundryChatClient) -> None:
    """Pattern 2: loop while a TodoProvider still has open items."""
    print("\n=== 2. Callable criterion (loop while todos remain) ===")

    # 1. A TodoProvider gives the agent tools to plan and track work as todo items.
    todo_provider = TodoProvider()

    # 2. ``todos_remaining`` builds a ``should_continue`` predicate that returns True while any todo
    #    item is still open. ``max_iterations`` guarantees the loop stops even if the agent stalls.
    loop = AgentLoopMiddleware.with_predicate(
        todos_remaining(todo_provider),
        max_iterations=6,
    )

    agent = Agent(
        client=client,
        name="planner",
        instructions=(
            "You are a planning assistant. First break the task into todo items using your todo tools. "
            "Then, on each turn, make progress and mark completed items as done. "
            "When all items are complete, summarize the result."
        ),
        context_providers=[todo_provider],
        middleware=[loop],
    )

    # 3. Reuse a single session so todo state persists across loop iterations.
    session = AgentSession()
    response = await agent.run(
        "Plan and outline a 3-section blog post about Rayleigh scattering.",
        session=session,
    )
    print(f"Final response:\n{response.text}")


async def judge_loop(client: FoundryChatClient, judge_client: FoundryChatClient) -> None:
    """Pattern 3: a second chat client judges whether the request was answered."""
    print("\n=== 3. ChatClient judge (loop until the request is answered) ===")

    # 1. Provide a ``judge_client``. The middleware asks it (via a ``JudgeVerdict`` structured
    #    output) whether the original request has been fully addressed and continues while the
    #    answer is "no". Judge loops default to a small ``max_iterations`` cap because each pass
    #    costs an extra model call.
    loop = AgentLoopMiddleware.with_judge(
        judge_client,
        max_iterations=4,
    )

    agent = Agent(
        client=client,
        name="answerer",
        instructions="You are a helpful assistant. Answer the user's question thoroughly.",
        middleware=[loop],
    )

    response: AgentResponse = await agent.run("Explain why the sky is blue, then also explain why sunsets are red.")
    print(f"Final response:\n{response.text}")


@tool(approval_mode="always_require")
def deploy_service(service: str) -> str:
    """Deploy a service to production (requires approval)."""
    return f"Deployed {service} to production."


async def approval_loop(client: FoundryChatClient) -> None:
    """Pattern 4: auto-resolve function-approval requests with a callable."""
    print("\n=== 4. Approval handling (auto-approve tool calls in the loop) ===")

    # 1. ``on_approval_request`` is called once per pending approval request. Returning a bool
    #    approves/rejects function calls; the loop feeds the response back and re-runs the agent.
    #    Approval rounds are exempt from ``max_iterations`` but bounded by ``max_approval_rounds``.
    def on_approval_request(*, request: Content, **kwargs: object) -> bool:
        call = request.function_call
        print(f"  Approving: {call.name if call else request.type}")
        return True

    loop = AgentLoopMiddleware(
        max_iterations=2,
        on_approval_request=on_approval_request,
        max_approval_rounds=3,
    )

    agent = Agent(
        client=client,
        name="operator",
        instructions="You are a deployment operator. Use the deploy_service tool to fulfil requests.",
        tools=[deploy_service],
        middleware=[loop],
    )

    # 2. A session lets the loop send just the approval response on each re-run.
    session = AgentSession()
    response = await agent.run("Deploy the billing service.", session=session)
    print(f"Final response:\n{response.text}")


async def main() -> None:
    # A single credential and client are reused; the judge uses its own client instance.
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(credential=credential)
        judge_client = FoundryChatClient(credential=credential)

        await ralph_loop(client)
        await todo_loop(client)
        await judge_loop(client, judge_client)
        await approval_loop(client)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (abridged; exact text varies by model):

=== 1. Ralph loop (no exit criteria, capped at 3 iterations) ===
Final response:
How about "MarginNote" — it evokes jotting ideas in the margins of a page.

=== 2. Callable criterion (loop while todos remain) ===
Final response:
All sections are drafted: (1) What light is, (2) How Rayleigh scattering works, (3) Why the sky is blue.

=== 3. ChatClient judge (loop until the request is answered) ===
Final response:
The sky is blue because shorter (blue) wavelengths scatter more (Rayleigh scattering). At sunset,
light travels through more atmosphere, scattering away blue and leaving red/orange hues.

=== 4. Approval handling (auto-approve tool calls in the loop) ===
  Approving: deploy_service
Final response:
Deployed billing service to production.
"""
