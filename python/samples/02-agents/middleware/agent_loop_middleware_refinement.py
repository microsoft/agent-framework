# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, AgentLoopMiddleware, AgentResponse
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent Loop Middleware: refinement loop (should_continue + feedback tracking)

This sample demonstrates ``AgentLoopMiddleware`` driven by a ``should_continue`` predicate. The loop
keeps refining a candidate answer until the agent's latest response contains a completion marker. It
also shows feedback tracking: ``record_feedback`` logs per-iteration progress that is fed into the
next pass, ``fresh_context`` restarts each pass from the original task plus that log, and
``max_iterations`` bounds the loop as a safety cap.

``next_message`` controls the input for the next iteration (it defaults to a short "continue" nudge).
The loop is run with streaming, so the injected messages between iterations show up as ``user``
updates; the stream is printed as ``<role>: <content>`` lines.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""

COMPLETE_MARKER = "<promise>COMPLETE</promise>"


async def refinement_loop(client: FoundryChatClient) -> None:
    """Loop while the response does not yet contain a completion marker."""
    print("\n=== Refinement loop (should_continue marker + feedback tracking, capped at 5) ===")

    # 1. ``should_continue`` keeps the loop running until the agent signals it is done by including
    #    the completion marker in its latest response. It is called with the loop keyword args and
    #    returns True to run the agent again.
    def should_continue(*, last_result: AgentResponse, **kwargs: object) -> bool:
        return COMPLETE_MARKER not in last_result.text

    # 2. ``record_feedback`` captures a short progress entry each iteration. Returning a string
    #    appends it to the log (returning None falls back to the response text). The accumulated log
    #    is injected into the next iteration's input so the agent builds on prior work.
    def record_feedback(*, iteration: int, last_result: AgentResponse, **kwargs: object) -> str:
        return f"iteration {iteration}: {last_result.text.strip()[:80]}"

    # 3. ``fresh_context=True`` restarts each pass from the original task plus the progress log, and
    #    ``max_iterations`` bounds the loop as a safety cap.
    loop = AgentLoopMiddleware(
        should_continue,
        max_iterations=5,
        record_feedback=record_feedback,
        fresh_context=True,
    )

    # 4. Attach the middleware to the agent.
    agent = Agent(
        client=client,
        name="refiner",
        instructions=(
            "You are iteratively refining a product name for a note-taking app. Each turn, build on the "
            "progress log: propose an improved candidate with a short reason. When you are confident the "
            f"name is final, end your message with the exact marker {COMPLETE_MARKER}."
        ),
        middleware=[loop],
    )

    # 5. Run once with streaming. The middleware drives the iterations, feeding progress forward until
    #    the agent emits the completion marker or the iteration cap is reached. Each contiguous
    #    ``user`` block marks the boundary into the next iteration, so we count loop iterations by
    #    those boundaries (robust to function calling, where one iteration may issue several model
    #    calls; tool calls/results are never ``user`` updates).
    iterations = 1
    in_user_block = False
    assistant_open = False
    async for update in agent.run("Suggest a name for a note-taking app.", stream=True):
        if update.role == "user":
            if not in_user_block:
                iterations += 1
                in_user_block = True
            assistant_open = False
            print(f"\nuser: {update.text}", flush=True)
            continue
        in_user_block = False
        if update.text:
            if not assistant_open:
                print("\nassistant: ", end="", flush=True)
                assistant_open = True
            print(update.text, end="", flush=True)
    print(f"\n\nCompleted in {iterations} iteration(s).")


async def main() -> None:
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(credential=credential)
        await refinement_loop(client)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (abridged; exact text varies by model):

=== Refinement loop (should_continue marker + feedback tracking, capped at 5) ===
assistant: "QuickJot" — short and evokes fast capture.
user: Suggest a name for a note-taking app.
user: Progress so far:
- iteration 1: "QuickJot" — short and evokes fast capture.
user: Continue working on the task. If it is complete, say so.
assistant: How about "MarginNote" — it evokes jotting ideas in the margins. <promise>COMPLETE</promise>

Completed in 2 iteration(s).
"""
