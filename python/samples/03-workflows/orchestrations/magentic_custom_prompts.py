# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import cast

from agent_framework import Agent, AgentResponseUpdate, Message, WorkflowEvent
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import MagenticBuilder
from agent_framework_orchestrations import MagenticOrchestrator
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
Sample: Magentic Orchestration with Custom Manager Prompts

The `StandardMagenticManager` drives planning, replanning, progress tracking, and the final
answer with a set of built-in prompts. Every one of them can be replaced through
`MagenticBuilder`, which is useful when the orchestration has to follow a house style, a
domain vocabulary, or a fixed report format.

Overridable prompts and the placeholders available to each one:

| Builder argument                   | Placeholders                       | Used for                          |
| ---------------------------------- | ---------------------------------- | --------------------------------- |
| `task_ledger_facts_prompt`         | `{task}`                           | Initial fact sheet                |
| `task_ledger_plan_prompt`          | `{team}`                           | Initial plan                      |
| `task_ledger_full_prompt`          | `{task}`, `{team}`, `{facts}`, `{plan}` | Combined ledger shown to the team |
| `task_ledger_facts_update_prompt`  | `{task}`, `{old_facts}`            | Fact sheet refresh on replan      |
| `task_ledger_plan_update_prompt`   | `{team}`                           | New plan on replan                |
| `progress_ledger_prompt`           | `{task}`, `{team}`, `{names}`      | Per-round progress decision       |
| `final_answer_prompt`              | `{task}`                           | Final synthesized answer          |

A prompt is formatted with `str.format`, so any literal brace in a custom prompt must be
doubled (`{{`, `}}`). An override may omit any available placeholder, but any placeholder it
uses must have a name listed above. `progress_ledger_prompt` is the one override to treat with
care: its response is parsed as JSON, so a replacement must keep the same schema as the
built-in prompt. This sample leaves it at the default and overrides the six prompts that shape
the ledger and the final report. Note that the replan prompts have to be overridden alongside
the initial ones: a stall makes the manager rebuild the fact sheet and the plan, and leaving
the replan prompts at their defaults would silently drop the custom format mid-run.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Microsoft Foundry Agent Service (V2) project endpoint.
- FOUNDRY_MODEL must be set to your Azure OpenAI model deployment name.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
"""

load_dotenv()

FACTS_PROMPT = """You are the planning lead of an incident review board.

Request under review:

{task}

Produce a fact sheet using exactly these headings, and nothing else:

    1. CONFIRMED SIGNALS
    2. SIGNALS TO COLLECT
    3. SIGNALS TO DERIVE
    4. WORKING HYPOTHESES

Every entry must be a single line starting with "- ". Do not propose next steps yet.
"""

PLAN_PROMPT = """The review board is staffed as follows:

{team}

Write the investigation plan as numbered steps. Each step must be one line in the form:

    <n>. [<team member name>] <what they do> -> <what artifact it produces>

Use at most five steps and only involve a team member when their expertise is required.
"""

FACTS_UPDATE_PROMPT = """The investigation has stalled on this request:

{task}

Rewrite the fact sheet below with everything learned since it was written, keeping the same
four headings and the same one-line "- " entries. Move confirmed items out of the hypothesis
section and add at least one new working hypothesis with its reasoning.

Previous fact sheet:

{old_facts}
"""

PLAN_UPDATE_PROMPT = """State in one sentence why the previous plan stalled, then write a new
investigation plan for this board:

{team}

Keep the numbered one-line step format:

    <n>. [<team member name>] <what they do> -> <what artifact it produces>

Use at most five steps and make each one avoid the failure you just named.
"""

FULL_LEDGER_PROMPT = """INCIDENT REVIEW BRIEF
=====================

Request:
{task}

Board:
{team}

Fact sheet:
{facts}

Investigation plan:
{plan}
"""

FINAL_ANSWER_PROMPT = """The investigation of the following request is complete:

{task}

Write the closing report for the incident review board with these sections:

    SUMMARY - two sentences, no jargon.
    FINDINGS - bullet list, each with the evidence it rests on.
    RECOMMENDATION - a single actionable sentence.

Address the reader directly and do not mention the investigation process itself.
"""


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    log_analyst = Agent(
        name="LogAnalyst",
        description="Reads service logs and metrics to reconstruct what happened during an incident",
        instructions=(
            "You are a log analyst. Reconstruct incident timelines from the evidence you are given "
            "and state plainly when evidence is missing."
        ),
        client=client,
    )

    reliability_engineer = Agent(
        name="ReliabilityEngineer",
        description="Explains failure modes and proposes mitigations for distributed systems",
        instructions="You are a reliability engineer. Explain likely failure modes and propose mitigations.",
        client=client,
    )

    manager_agent = Agent(
        name="MagenticManager",
        description="Orchestrator that runs the incident review board",
        instructions="You coordinate a team to complete complex tasks efficiently.",
        client=client,
    )

    workflow = MagenticBuilder(
        participants=[log_analyst, reliability_engineer],
        intermediate_output_from=[log_analyst, reliability_engineer],
        manager_agent=manager_agent,
        task_ledger_facts_prompt=FACTS_PROMPT,
        task_ledger_plan_prompt=PLAN_PROMPT,
        task_ledger_full_prompt=FULL_LEDGER_PROMPT,
        task_ledger_facts_update_prompt=FACTS_UPDATE_PROMPT,
        task_ledger_plan_update_prompt=PLAN_UPDATE_PROMPT,
        final_answer_prompt=FINAL_ANSWER_PROMPT,
        max_round_count=8,
        max_stall_count=2,
    ).build()

    task = (
        "A checkout service returned HTTP 503 for 12 minutes after a deployment. Error rates spiked "
        "only on the two pods that were rescheduled onto a new node pool, and the database connection "
        "pool reported saturation for the same window. Determine the most likely root cause and how to "
        "prevent a recurrence."
    )

    print(f"\nTask: {task}\n")

    last_message_id: str | None = None
    output_event: WorkflowEvent | None = None
    async for event in workflow.run(task, stream=True):
        if event.type in ("intermediate", "output"):
            if event.executor_id == MagenticOrchestrator.MANAGER_NAME:
                output_event = event
            else:
                update = cast(AgentResponseUpdate, event.data)
                if update.message_id != last_message_id:
                    if last_message_id is not None:
                        print("\n")
                    print(f"- {event.executor_id}:", end=" ", flush=True)
                    last_message_id = update.message_id
                print(update, end="", flush=True)

        elif event.type == "magentic_orchestrator" and isinstance(event.data.content, Message):
            # The task ledger rendered here follows FULL_LEDGER_PROMPT rather than the built-in layout.
            print(f"\n[{event.data.event_type.name}]\n{event.data.content.text}")

    if not output_event:
        raise RuntimeError("Workflow did not produce a final output event.")

    print("\n\nFinal report (shaped by FINAL_ANSWER_PROMPT):")
    print(cast(AgentResponseUpdate, output_event.data).text)


if __name__ == "__main__":
    asyncio.run(main())
