# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Agent,
    AgentLoopMiddleware,
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
Agent Loop Middleware: todo list + report-style judge, composed as two middleware

This sample demonstrates a more complex ``AgentLoopMiddleware`` setup that composes TWO separate loop
middleware on a single agent — rather than hand-writing one predicate that does both checks. The
agent's ``middleware`` list is the composition point:

    middleware=[judge_loop, todo_loop]

Agent middleware run outermost-first, so ``judge_loop`` wraps ``todo_loop``:

1. ``todo_loop`` (inner) — built from the ``todos_remaining`` helper over a ``TodoProvider``. It
   re-runs the agent while any todo item is still open, so the agent plans the report and then drafts
   it one todo at a time. Its final todo assembles and emits the complete report, so when the inner
   loop stops its final response is the full report.
2. ``judge_loop`` (outer) — built from ``AgentLoopMiddleware.with_judge``. Each time the inner todo
   loop finishes, a separate "editor" chat client reviews the assembled report (via a ``JudgeVerdict``
   structured output) against a list of report ``criteria``. While the editor is not satisfied, the
   outer loop re-runs the inner todo loop (the todos are already complete, so it runs the agent once)
   with the editor's reasoning fed back, and the agent revises the full report.

``with_judge(criteria=...)`` renders the criteria into both the editor's judge instructions and an
extra instruction injected for the agent, so the agent writes toward the same bar the editor grades
against. A custom report-style ``instructions`` string frames the judge as an editor reviewing a
report.

The loop is run with streaming, so the injected messages between iterations show up as ``user``
updates; the stream is printed as ``<role>: <content>`` lines. Each contiguous ``user`` block (from
either loop) marks a boundary into another agent run, so the printed count is the total number of
agent runs across both loops.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""

# Requirements the finished report must satisfy. Passed as ``criteria`` to ``with_judge``, which
# renders them into both the editor's judge instructions and an extra instruction for the agent.
REPORT_REQUIREMENTS = [
    "Opens with a one-paragraph executive summary.",
    "Has a clearly titled section for each part of the brief.",
    "Ends with a short 'Key takeaways' bulleted list.",
    "Is written in clear, professional prose.",
]

# Report-style judge instructions. The ``{{criteria}}`` placeholder is replaced by ``with_judge``
# with the rendered REPORT_REQUIREMENTS block.
EDITOR_INSTRUCTIONS = (
    "You are a senior editor reviewing a research report. You are given the user's original brief and "
    "the report the agent produced. Decide whether the report is publication-ready. Set 'answered' to "
    "true only if the report is ready, otherwise set it to false and use 'reasoning' to state "
    "concisely what is missing.{{criteria}}"
)


async def report_loop(client: FoundryChatClient, editor_client: FoundryChatClient) -> None:
    """Compose a todo loop (inner) and a report-style judge loop (outer) on one agent."""
    print("\n=== Todo list + report-style judge (two composed middleware) ===")

    # 1. A TodoProvider gives the agent tools to plan and track the report as todo items. A single
    #    session (created below) keeps this todo state alive across loop iterations.
    todo_provider = TodoProvider()

    # 2. Inner loop: re-run the agent while the TodoProvider still has open items. ``todos_remaining``
    #    builds the ``should_continue`` predicate; ``max_iterations`` caps planning + one-todo-per-turn
    #    drafting + the final assembly turn.
    todo_loop = AgentLoopMiddleware(
        todos_remaining(),
        max_iterations=8,
    )

    # 3. Outer loop: each time the inner todo loop finishes, ``editor_client`` judges the assembled
    #    report against REPORT_REQUIREMENTS and the loop re-runs the inner loop while it is not yet
    #    publication-ready. ``with_judge`` injects the criteria for the agent too, and feeds the
    #    editor's reasoning back as the next iteration's input. The judge cap bounds the revision rounds.
    judge_loop = AgentLoopMiddleware.with_judge(
        editor_client,
        instructions=EDITOR_INSTRUCTIONS,
        criteria=REPORT_REQUIREMENTS,
        max_iterations=4,
    )

    # 4. Compose the two middleware on the agent. Order matters: ``judge_loop`` is outermost (it wraps
    #    and re-runs the whole ``todo_loop``), ``todo_loop`` is innermost (it drives the per-todo
    #    drafting). The agent is told to finish with a dedicated assembly todo so that, when the inner
    #    loop stops, its final response is the complete report the editor then grades.
    agent = Agent(
        client=client,
        name="report-writer",
        instructions=(
            "You are a research writer producing a short report. "
            "On your FIRST turn, break the report into todo items using your todo tools: one item per "
            "report section, plus a final 'Assemble and output the complete report' item — then stop, "
            "do not start writing yet. On EACH SUBSEQUENT turn while todos remain, complete exactly "
            "ONE remaining todo item, draft its content, and mark it done using your tools — never "
            "more than one item per turn. When you reach the final assembly item, output the FULL "
            "report in a single message and mark it done. If an editor later returns feedback, revise "
            "and output the full report again."
        ),
        context_providers=[todo_provider],
        middleware=[judge_loop, todo_loop],
    )

    # 5. Run once with streaming. Reuse a single session so todo state persists across iterations.
    #    Each contiguous ``user`` block marks a boundary into another agent run; both loops inject
    #    such blocks (todo nudges and editor feedback), so the count is the total number of agent runs.
    session = AgentSession()
    prompt = "Write a brief report on the benefits and risks of remote work for software teams."
    runs = 1
    in_user_block = False
    assistant_open = False
    async for update in agent.run(prompt, session=session, stream=True):
        if update.role == "user":
            if not in_user_block:
                runs += 1
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
    print(f"\n\nCompleted in {runs} agent run(s).")

    # 6. Inspect the todos the agent created, loaded from the same store the inner loop uses.
    items = await todo_provider.store.load_items(session, source_id=todo_provider.source_id)
    print("\nTodos after the run:")
    for item in items:
        mark = "x" if item.is_complete else " "
        print(f"  [{mark}] {item.id}. {item.title}")


"""
Sample output for ``report_loop`` (abridged; exact text varies by model):

=== Todo list + report-style judge (two composed middleware) ===
assistant: Here is my plan. I'll create todos for each section and a final assembly item.
user: Continue working on the task. If it is complete, say so.
...
assistant: # Remote Work for Software Teams

**Executive summary:** Remote work offers flexibility and access to wider talent...

## Benefits
...

## Risks
...

## Key takeaways
- Flexibility improves retention.
- Async communication needs discipline.
user: An evaluator reviewed your previous response and judged that it does not yet fully
address the original request.

Evaluator feedback: Add a one-paragraph executive summary before the first section.

Revise and continue so the original request is fully addressed.
assistant: # Remote Work for Software Teams

**Executive summary:** ... (revised, now opens with a summary)
...

Completed in 7 agent run(s).

Todos after the run:
  [x] 1. Benefits section
  [x] 2. Risks section
  [x] 3. Key takeaways
  [x] 4. Assemble and output the complete report
"""


async def main() -> None:
    # A single credential is reused; the editor judge uses its own client instance.
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(credential=credential)
        editor_client = FoundryChatClient(credential=credential)

        await report_loop(client, editor_client)


if __name__ == "__main__":
    asyncio.run(main())
