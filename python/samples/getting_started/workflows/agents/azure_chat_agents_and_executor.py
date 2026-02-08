# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Final

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponseUpdate,
    ChatMessage,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: AzureOpenAI Chat Agents and an Executor in a Workflow with Streaming

Pipeline layout:
research_agent -> enrich_with_references (@executor) -> final_editor_agent

The first agent drafts a short answer. A lightweight @executor function simulates
an external data fetch and injects a follow-up user message containing extra context.
The final agent incorporates the new note and produces the polished output.

Demonstrates:
- Using the @executor decorator to create a function-style Workflow node.
- Consuming an AgentExecutorResponse and forwarding an AgentExecutorRequest for the next agent.

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
    """Inject a follow-up user instruction that adds an external note for the next agent.

    Args:
        draft: The response from the research_agent containing the initial draft. This is
               a `AgentExecutorResponse` because agents in workflows send their full response
               wrapped in this type to connected executors.
        ctx: The workflow context to send the next request.
    """
    conversation = list(draft.full_conversation or draft.agent_response.messages)
    original_prompt = next((message.text for message in conversation if message.role == "user"), "")
    external_note = _lookup_external_note(original_prompt) or (
        "No additional references were found. Please refine the previous assistant response for clarity."
    )

    follow_up = (
        "External knowledge snippet:\n"
        f"{external_note}\n\n"
        "Please update the prior assistant answer so it weaves this note into the guidance."
    )
    conversation.append(ChatMessage("user", [follow_up]))

    # Output a new AgentExecutorRequest for the next agent in the workflow.
    # Agents in workflows handle this type and will generate a response based on the request.
    await ctx.send_message(AgentExecutorRequest(messages=conversation))


async def main() -> None:
    """Run the workflow and stream combined updates from both agents."""
    # Create the agents
    research_agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="research_agent",
        instructions=(
            "Produce a short, bullet-style briefing with two actionable ideas. Label the section as 'Initial Draft'."
        ),
    )

    final_editor_agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="final_editor_agent",
        instructions=(
            "Use all conversation context (including external notes) to produce the final answer. "
            "Merge the draft and extra note into a concise recommendation under 150 words."
        ),
    )

    workflow = (
        WorkflowBuilder(start_executor=research_agent)
        .add_edge(research_agent, enrich_with_references)
        .add_edge(enrich_with_references, final_editor_agent)
        .build()
    )

    events = workflow.run(
        "Create quick workspace wellness tips for a remote analyst working across two monitors.", stream=True
    )

    # Track the last author to format streaming output.
    last_author: str | None = None

    async for event in events:
        # The outputs of the workflow are whatever the agents produce. So the events are expected to
        # contain `AgentResponseUpdate` from the agents in the workflow.
        if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
            update = event.data
            author = update.author_name
            if author != last_author:
                if last_author is not None:
                    print("\n")  # Newline between different authors
                print(f"{author}: {update.text}", end="", flush=True)
                last_author = author
            else:
                print(update.text, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
