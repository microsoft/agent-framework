# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Agent,
    AgentLoopMiddleware,
    AgentResponse,
    AgentSession,
    TodoProvider,
    todos_remaining,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent Loop Middleware

This sample demonstrates ``AgentLoopMiddleware`` — a single, configurable middleware that re-runs an
agent in a loop. It covers two common patterns through one class:

1. Callable        — a ``should_continue`` predicate decides whether to loop again. The first loop
                     keeps refining a candidate until the response contains a completion marker, and
                     also shows feedback tracking: ``record_feedback`` logs per-iteration progress
                     that is fed into the next pass, ``fresh_context`` restarts each pass from the
                     original task plus the log, and ``max_iterations`` bounds the loop as a safety
                     cap. The second loop pairs ``should_continue`` with a ``TodoProvider`` via the
                     ``todos_remaining`` helper, so the agent keeps working while it still has open
                     todo items. After the run the sample prints the todos the agent created.
2. ChatClient judge — a second chat client decides (via a ``JudgeVerdict`` structured output)
   whether the original request was answered; the
                     loop continues while the answer is "no". The judge's ``reasoning`` is fed back
                     to the agent as the next iteration's input. This loop also passes a list of
                     ``criteria``, which are injected as an extra instruction for the agent and
                     rendered into the judge's instructions.

In every case ``next_message`` controls the input for the next iteration (it defaults to a short
"continue" nudge). All loops are run with streaming, so the injected messages between iterations
show up as ``user`` updates; the stream is printed as ``<role>: <content>`` lines. Each function's
expected output is shown in a block directly beneath it.

The constructor covers pattern 1 directly (pass a ``should_continue`` predicate);
``AgentLoopMiddleware.with_judge(...)`` is a convenience factory for pattern 2 that forwards to the
same constructor.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""


async def refinement_loop(client: FoundryChatClient) -> None:
    """Pattern 1: loop while the response does not yet contain a completion marker."""
    print("\n=== 1. Refinement loop (should_continue marker + feedback tracking, capped at 5) ===")

    COMPLETE_MARKER = "<promise>COMPLETE</promise>"

    # 1. ``should_continue`` keeps the loop running until the agent signals it is done by including
    #    the completion marker in its latest response. It is called with the loop keyword args and
    #    returns True to run the agent again.
    def should_continue(*, last_result: AgentResponse, **kwargs: object) -> bool:
        return COMPLETE_MARKER not in last_result.text

    # 2. ``record_feedback`` captures a short progress entry each iteration. It is called with the
    #    loop keyword args; the ``progress`` kwarg holds the entries recorded so far. Returning a
    #    string appends it to the log (returning None falls back to the response text). The
    #    accumulated log is injected into the next iteration's input so the agent builds on prior work.
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

    # 5. Run once with streaming. The middleware drives the iterations, feeding progress forward
    #    until the agent emits the completion marker or the iteration cap is reached. In streaming
    #    mode the loop surfaces the injected "nudge"/progress messages as ``user`` updates between
    #    iterations. Each contiguous ``user`` block marks the boundary into the next iteration, so we
    #    count loop iterations by those boundaries. This is robust to function calling, where a single
    #    iteration may issue several model calls (``response_id`` changes per model call, not per loop
    #    iteration, so it is not used here). Tool calls/results are ``tool``/``assistant`` updates,
    #    never ``user``, so they do not affect the count.
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


"""
Sample output for ``refinement_loop`` (abridged; exact text varies by model):

=== 1. Refinement loop (should_continue marker + feedback tracking, capped at 5) ===
assistant: "QuickJot" — short and evokes fast capture.
user: Suggest a name for a note-taking app.
user: Progress so far:
- iteration 1: "QuickJot" — short and evokes fast capture.
user: Continue working on the task. If it is complete, say so.
assistant: How about "MarginNote" — it evokes jotting ideas in the margins. <promise>COMPLETE</promise>

Completed in 2 iteration(s).
"""


async def todo_loop(client: FoundryChatClient) -> None:
    """Pattern 1 (provider helper): loop while a TodoProvider still has open items."""
    print("\n=== 2. Callable criterion (loop while todos remain) ===")

    # 1. A TodoProvider gives the agent tools to plan and track work as todo items.
    todo_provider = TodoProvider()

    # 2. ``todos_remaining`` builds a ``should_continue`` predicate that returns True while any todo
    #    item is still open. ``max_iterations`` guarantees the loop stops even if the agent stalls.
    loop = AgentLoopMiddleware(
        should_continue=todos_remaining(todo_provider),
        max_iterations=6,
    )

    agent = Agent(
        client=client,
        name="planner",
        instructions=(
            "You are a writing assistant working through a todo list. "
            "On your FIRST turn, break the task into todo items using your todo tools and stop "
            "(do not start writing yet). On EACH SUBSEQUENT turn, complete exactly ONE remaining "
            "todo item, write its content, and mark it done using your tools — never complete more "
            "than one item per turn. When every item is done, give a brief final summary."
        ),
        context_providers=[todo_provider],
        middleware=[loop],
    )

    # 3. Reuse a single session so todo state persists across loop iterations. Each contiguous
    #    ``user`` block marks the boundary into the next iteration, so we count loop iterations by
    #    those boundaries — robust to the function calling this loop relies on (the todo tools issue
    #    several model calls per iteration, but tool calls/results are never ``user`` updates).
    session = AgentSession()
    prompt = "Plan and write a short 3-section blog post about Rayleigh scattering."
    iterations = 1
    in_user_block = False
    assistant_open = False
    async for update in agent.run(prompt, session=session, stream=True):
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

    # 4. Inspect the todos the agent created, loaded from the same store the loop predicate uses.
    items = await todo_provider.store.load_items(session, source_id=todo_provider.source_id)
    print("\nTodos after the run:")
    for item in items:
        mark = "x" if item.is_complete else " "
        print(f"  [{mark}] {item.id}. {item.title}")


"""
Sample output for ``todo_loop`` (abridged; exact text varies by model):

=== 2. Callable criterion (loop while todos remain) ===
assistant: Here is my plan. I'll create todos for each section.
user: Progress so far:
- Here is my plan. I'll create todos for each section.
user: Continue working on the task. If it is complete, say so.
assistant: Section 1 drafted. Marking it done.
user: Progress so far:
- Section 1 drafted. Marking it done.
user: Continue working on the task. If it is complete, say so.
assistant: Section 2 drafted. Marking it done.
user: Progress so far:
- Section 2 drafted. Marking it done.
user: Continue working on the task. If it is complete, say so.
assistant: Section 3 drafted. Marking it done.

Completed in 4 iteration(s).

Todos after the run:
  [x] 1. Draft "What light is" section
  [x] 2. Draft "How Rayleigh scattering works" section
  [x] 3. Draft "Why the sky is blue" section
"""


async def judge_loop(client: FoundryChatClient, judge_client: FoundryChatClient) -> None:
    """Pattern 2: a second chat client judges whether the request was answered."""
    print("\n=== 3. ChatClient judge (loop until the request is answered) ===")

    # 1. Provide a ``judge_client``. The middleware asks it (via a ``JudgeVerdict`` structured
    #    output) whether the original request has been fully addressed and continues while the
    #    answer is "no". The judge's ``reasoning`` is fed back to the agent as the next iteration's
    #    input, so the agent knows what is missing. Judge loops default to a small ``max_iterations``
    #    cap because each pass costs an extra model call.
    #
    #    ``criteria`` is a list of requirements the response must satisfy. The loop (a) injects them
    #    as an extra instruction for the agent before it runs and (b) renders them into the judge's
    #    instructions (the default judge prompt includes a ``{{criteria}}`` placeholder). Supply your
    #    own ``instructions`` string with ``{{criteria}}`` to control the wording, or omit ``criteria``
    #    entirely and pass a plain ``instructions`` string.
    loop = AgentLoopMiddleware.with_judge(
        judge_client,
        criteria=[
            "Mentions the moon",
            "Includes at least one good joke",
            "Is written as a single piece of fluent prose",
        ],
        max_iterations=4,
    )

    agent = Agent(
        client=client,
        name="answerer",
        instructions="You are a helpful assistant. Answer the user's question thoroughly.",
        middleware=[loop],
    )

    # 2. Run with streaming; the judge's feedback appears as a ``user`` update between iterations
    #    until the judge is satisfied (or the iteration cap is reached). Each contiguous ``user``
    #    block marks the boundary into the next iteration, so we count loop iterations by those
    #    boundaries (robust to function calling, where one iteration may issue several model calls).
    iterations = 1
    in_user_block = False
    assistant_open = False
    async for update in agent.run("Explain why the sky is blue and sunsets are red.", stream=True):
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


"""
Sample output for ``judge_loop`` (abridged; exact text varies by model):

=== 3. ChatClient judge (loop until the request is answered) ===
assistant: The sky is blue because shorter (blue) wavelengths scatter more (Rayleigh scattering).
user: An evaluator reviewed your previous response and judged that it does not yet fully
address the original request.

Evaluator feedback: The response does not mention the moon.

Revise and continue so the original request is fully addressed.
assistant: The sky is blue because shorter (blue) wavelengths scatter more. At sunset, light travels
through more atmosphere, scattering away blue and leaving red/orange hues. The moon follows the
sky's colors because the same scattering applies to the light reaching it.

Completed in 2 iteration(s).
"""


async def main() -> None:
    # A single credential and client are reused; the judge uses its own client instance.
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(credential=credential)
        judge_client = FoundryChatClient(credential=credential)

        await refinement_loop(client)
        await todo_loop(client)
        await judge_loop(client, judge_client)


if __name__ == "__main__":
    asyncio.run(main())
