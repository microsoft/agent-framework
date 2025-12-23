# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Final

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
    AgentRunUpdateEvent,
    ChatMessage,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    executor,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Two agents connected by a function executor bridge

Pipeline layout:
research_agent -> enrich_with_references (@executor) -> final_editor_agent

The first agent drafts a short answer. A lightweight @executor function simulates
an external data fetch and injects a follow-up user message containing extra context.
The final agent incorporates the new note and produces the polished output.

Demonstrates:
- Using the @executor decorator to create a function-style Workflow node.
- Consuming an AgentExecutorResponse and forwarding an AgentExecutorRequest for the next agent.
- Streaming AgentRunUpdateEvent events across agent + function + agent chain.

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables.
- Authentication via azure-identity. Run `az login` before executing.
"""

# Simulated external content keyed by a simple topic hint.
EXTERNAL_REFERENCES: Final[dict[str, str]] = {
    "workspace": (
        "From Workspace Weekly: Adjustable monitor arms and sit-stand desks can reduce "
        "neck strain by up to 30%. Consider adding a reminder to move every 45 minutes."
    ),
    "travel": (
        "Checklist excerpt: Always confirm baggage limits for budget airlines. "
        "Keep a photocopy of your passport stored separately from the original."
    ),
    "wellness": (
        "Recent survey: Employees who take two 5-minute breaks per hour report 18% higher focus "
        "scores. Encourage scheduling micro-breaks alongside hydration reminders."
    ),
}


def _lookup_external_note(prompt: str) -> str | None:
    """Return the first matching external note based on a keyword search."""
    lowered = prompt.lower()
    for keyword, note in EXTERNAL_REFERENCES.items():
        if keyword in lowered:
            return note
    return None


@executor(id="enrich_with_references")
async def enrich_with_references(
    draft: AgentExecutorResponse,
    ctx: WorkflowContext[AgentExecutorRequest],
) -> None:
    """Inject a follow-up user instruction that adds an external note for the next agent."""
    conversation = list(draft.full_conversation or draft.agent_run_response.messages)
    original_prompt = next((message.text for message in conversation if message.role == Role.USER), "")
    external_note = _lookup_external_note(original_prompt) or (
        "No additional references were found. Please refine the previous assistant response for clarity."
    )

    follow_up = (
        "External knowledge snippet:\n"
        f"{external_note}\n\n"
        "Please update the prior assistant answer so it weaves this note into the guidance."
    )
    conversation.append(ChatMessage(role=Role.USER, text=follow_up))

    await ctx.send_message(AgentExecutorRequest(messages=conversation))


def create_research_agent():
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name="research_agent",
        instructions=(
            "Produce a short, bullet-style briefing with two actionable ideas. Label the section as 'Initial Draft'."
        ),
    )


def create_final_editor_agent():
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        name="final_editor_agent",
        instructions=(
            "Use all conversation context (including external notes) to produce the final answer. "
            "Merge the draft and extra note into a concise recommendation under 150 words."
        ),
    )


async def main() -> None:
    """Run the workflow and stream combined updates from both agents."""
    workflow = (
        WorkflowBuilder()
        .register_agent(create_research_agent, name="research_agent")
        .register_agent(create_final_editor_agent, name="final_editor_agent")
        .register_executor(lambda: enrich_with_references, name="enrich_with_references")
        .set_start_executor("research_agent")
        .add_edge("research_agent", "enrich_with_references")
        .add_edge("enrich_with_references", "final_editor_agent")
        .build()
    )

    events = workflow.run_stream(
        "Create quick workspace wellness tips for a remote analyst working across two monitors."
    )

    last_executor: str | None = None
    async for event in events:
        if isinstance(event, AgentRunUpdateEvent):
            if event.executor_id != last_executor:
                if last_executor is not None:
                    print()
                print(f"{event.executor_id}:", end=" ", flush=True)
                last_executor = event.executor_id
            print(event.data, end="", flush=True)
        elif isinstance(event, WorkflowOutputEvent):
            print("\n\n===== Final Output =====")
            response = event.data
            if isinstance(response, AgentRunResponse):
                print(response.text or "(empty response)")
            else:
                print(response if response is not None else "No response generated.")


if __name__ == "__main__":
    asyncio.run(main())
