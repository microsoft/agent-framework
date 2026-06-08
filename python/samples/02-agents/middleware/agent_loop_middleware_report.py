# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Agent,
    AgentLoopMiddleware,
    AgentResponse,
    AgentSession,
    JudgeVerdict,
    Message,
    TodoProvider,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent Loop Middleware: todo list + report-style judge

This sample demonstrates a more complex ``AgentLoopMiddleware`` setup that combines TWO criteria in a
single ``should_continue`` predicate, evaluated in order:

1. Todo list (checked first) — a ``TodoProvider`` gives the agent tools to plan the report as todo
   items. While any todo is still open, the loop keeps going so the agent drafts the report section
   by section. Only once every todo is complete does the predicate fall through to the second check.
2. Report-style judge (checked second) — once the draft is finished, a separate "editor" chat client
   reviews the assembled report against a list of report requirements (executive summary, titled
   sections, a key-takeaways list, professional prose) and returns a ``JudgeVerdict``. While the
   editor is not satisfied, the loop continues and the agent revises the full report; the editor's
   reasoning is fed back to the agent as the next iteration's input.

The same ``REPORT_REQUIREMENTS`` list is rendered into both the agent's instructions (so it aims for
them) and the editor's instructions (so it grades against them), mirroring how
``AgentLoopMiddleware.with_judge(criteria=...)`` works — but here it is wired up by hand so the todo
check and the judge check can be composed in one predicate.

The loop is run with streaming, so the injected messages between iterations show up as ``user``
updates; the stream is printed as ``<role>: <content>`` lines. Loop iterations are counted by the
contiguous ``user`` blocks the middleware injects between runs (robust to the function calling the
todo tools rely on, where one iteration may issue several model calls).

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""

# Requirements the finished report must satisfy. Rendered into both the agent's instructions (so it
# writes toward them) and the editor's judge instructions (so it grades against them).
REPORT_REQUIREMENTS = [
    "Opens with a one-paragraph executive summary.",
    "Has a clearly titled section for each part of the brief.",
    "Ends with a short 'Key takeaways' bulleted list.",
    "Is written in clear, professional prose.",
]


def _bullets(items: list[str]) -> str:
    """Render a list of strings as a bulleted block."""
    return "\n".join(f"- {item}" for item in items)


async def report_loop(client: FoundryChatClient, editor_client: FoundryChatClient) -> None:
    """Compose a todo check (first) with a report-style judge (second) in one ``should_continue``."""
    print("\n=== Todo list + report-style judge ===")

    # 1. A TodoProvider gives the agent tools to plan and track the report as todo items. A single
    #    session is reused below so this todo state persists across loop iterations.
    todo_provider = TodoProvider()

    # 2. The editor's report-style instructions. The shared REPORT_REQUIREMENTS are rendered in so the
    #    editor grades the assembled report against the same bar the agent is told to hit.
    editor_instructions = (
        "You are a senior editor reviewing a research report. You are given the original brief and "
        "the report the agent produced. Decide whether the report is publication-ready. Set "
        "'answered' to true only if the report satisfies ALL of the following requirements, "
        "otherwise set it to false and use 'reasoning' to state concisely what is missing:\n"
        f"{_bullets(REPORT_REQUIREMENTS)}"
    )

    async def judge_report(original_messages: list[Message], last_result: AgentResponse) -> JudgeVerdict:
        """Ask the editor client (via a JudgeVerdict structured output) to grade the assembled report."""
        judge_messages = [
            Message(role="system", contents=[editor_instructions]),
            Message(role="user", contents=["Review the report. The original brief follows:"]),
            *original_messages,
            Message(role="user", contents=["The agent's latest report was:"]),
            *last_result.messages,
            Message(role="user", contents=["Is the report publication-ready?"]),
        ]
        response = await editor_client.get_response(judge_messages, options={"response_format": JudgeVerdict})
        verdict = response.value
        if isinstance(verdict, JudgeVerdict):
            return verdict
        # Fallback for clients that do not honor structured output: keep iterating.
        return JudgeVerdict(answered=False, reasoning="")

    # 3. The composite predicate. Todos are checked FIRST; only when they are all complete does it
    #    fall through to the editor judge. Both branches return a ``(continue, feedback)`` tuple; the
    #    feedback is surfaced to ``next_message`` so the agent knows what to do next.
    async def should_continue(
        *, session: AgentSession, original_messages: list[Message], last_result: AgentResponse, **kwargs: object
    ) -> tuple[bool, str | None]:
        items = await todo_provider.store.load_items(session, source_id=todo_provider.source_id)
        open_items = [item for item in items if not item.is_complete]
        if open_items:
            titles = ", ".join(item.title for item in open_items)
            return True, f"{len(open_items)} todo item(s) still open: {titles}"
        verdict = await judge_report(original_messages, last_result)
        return (not verdict.answered), (verdict.reasoning or None)

    # 4. ``next_message`` turns the feedback from either branch into the next iteration's input.
    def next_message(*, feedback: str | None = None, **kwargs: object) -> str:
        if feedback:
            return (
                "Continue the report. Outstanding work or editor feedback:\n"
                f"{feedback}\n\n"
                "If todo items remain, complete the next one. If the draft is complete, assemble and "
                "output the FULL report again, revised to address the feedback."
            )
        return "Continue working on the report."

    # 5. ``additional_instructions`` injects the same requirements for the agent. It is added as a
    #    system message ahead of the input, so it is present on every iteration. ``max_iterations``
    #    caps the loop: enough for planning, one todo per turn, plus a few editor revision rounds.
    loop = AgentLoopMiddleware(
        should_continue,
        max_iterations=10,
        next_message=next_message,
        additional_instructions=(
            "Your finished report must satisfy all of the following:\n" + _bullets(REPORT_REQUIREMENTS)
        ),
    )

    agent = Agent(
        client=client,
        name="report-writer",
        instructions=(
            "You are a research writer producing a short report. "
            "On your FIRST turn, break the report into todo items using your todo tools (one item per "
            "report section, plus an executive summary and a key-takeaways list) and then stop — do "
            "not start writing yet. On EACH SUBSEQUENT turn while todos remain, complete exactly ONE "
            "remaining todo item, draft its content, and mark it done using your tools — never more "
            "than one item per turn. Once EVERY todo is complete, assemble and output the FULL report "
            "in a single message. If an editor returns feedback, revise and output the full report "
            "again."
        ),
        context_providers=[todo_provider],
        middleware=[loop],
    )

    # 6. Run once with streaming. Reuse a single session so todo state persists across iterations.
    #    Each contiguous ``user`` block marks the boundary into the next iteration, so loop iterations
    #    are counted by those boundaries (the todo tools issue several model calls per iteration, but
    #    tool calls/results are ``tool``/``assistant`` updates, never ``user``).
    session = AgentSession()
    prompt = "Write a brief report on the benefits and risks of remote work for software teams."
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

    # 7. Inspect the todos the agent created, loaded from the same store the predicate uses.
    items = await todo_provider.store.load_items(session, source_id=todo_provider.source_id)
    print("\nTodos after the run:")
    for item in items:
        mark = "x" if item.is_complete else " "
        print(f"  [{mark}] {item.id}. {item.title}")


"""
Sample output for ``report_loop`` (abridged; exact text varies by model):

=== Todo list + report-style judge ===
assistant: Here is my plan. I'll create todos for the summary, sections, and takeaways.
user: Continue the report. Outstanding work or editor feedback:
4 todo item(s) still open: Executive summary, Benefits section, Risks section, Key takeaways
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

Completed in 6 iteration(s).

Todos after the run:
  [x] 1. Executive summary
  [x] 2. Benefits section
  [x] 3. Risks section
  [x] 4. Key takeaways
"""


async def main() -> None:
    # A single credential is reused; the editor judge uses its own client instance.
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(credential=credential)
        editor_client = FoundryChatClient(credential=credential)

        await report_loop(client, editor_client)


if __name__ == "__main__":
    asyncio.run(main())
