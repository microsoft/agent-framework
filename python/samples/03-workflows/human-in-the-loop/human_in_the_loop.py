# Copyright (c) Microsoft. All rights reserved.

"""
Human-in-the-Loop Workflow Sample

An agent guesses a number, then a human guides it with "higher", "lower", or
"correct". Demonstrates pausing a workflow for human input and resuming.

What you'll learn:
- Using request_info / response_handler for human interaction
- Alternating turns between an agent and a human
- Driving the loop with run(responses=..., stream=True)

Related samples:
- ../checkpoints/ — Save and resume workflow state
- ../agents-in-workflows/ — Using agents as workflow steps

Docs: https://learn.microsoft.com/agent-framework/workflows/overview
"""

import asyncio
from collections.abc import AsyncIterable
from dataclasses import dataclass

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponseUpdate,
    ChatMessage,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
    response_handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel


# <step_definitions>
@dataclass
class HumanFeedbackRequest:
    """Request sent to the human for feedback on the agent's guess."""

    prompt: str


class GuessOutput(BaseModel):
    """Structured output from the agent."""

    guess: int


class TurnManager(Executor):
    """Coordinates turns between the agent and the human."""

    def __init__(self, id: str | None = None):
        super().__init__(id=id or "turn_manager")

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """Start the game by asking the agent for an initial guess."""
        user = ChatMessage("user", text="Start by making your first guess.")
        await ctx.send_message(AgentExecutorRequest(messages=[user], should_respond=True))

    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext,
    ) -> None:
        """Handle the agent's guess and request human guidance."""
        text = result.agent_response.text
        last_guess = GuessOutput.model_validate_json(text).guess

        prompt = (
            f"The agent guessed: {last_guess}. "
            "Type one of: higher (your number is higher than this guess), "
            "lower (your number is lower than this guess), correct, or exit."
        )
        await ctx.request_info(
            request_data=HumanFeedbackRequest(prompt=prompt),
            response_type=str,
        )

    @response_handler
    async def on_human_feedback(
        self,
        original_request: HumanFeedbackRequest,
        feedback: str,
        ctx: WorkflowContext[AgentExecutorRequest, str],
    ) -> None:
        """Continue the game or finish based on human feedback."""
        reply = feedback.strip().lower()

        if reply == "correct":
            await ctx.yield_output("Guessed correctly!")
            return

        last_guess = original_request.prompt.split(": ")[1].split(".")[0]
        feedback_text = (
            f"Feedback: {reply}. Your last guess was {last_guess}. "
            f"Use this feedback to adjust and make your next guess (1-10)."
        )
        user_msg = ChatMessage("user", text=feedback_text)
        await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))
# </step_definitions>


async def process_event_stream(stream: AsyncIterable[WorkflowEvent]) -> dict[str, str] | None:
    """Process events from the workflow stream to capture human feedback requests."""
    last_response_id: str | None = None
    requests: list[tuple[str, HumanFeedbackRequest]] = []

    async for event in stream:
        if event.type == "request_info" and isinstance(event.data, HumanFeedbackRequest):
            requests.append((event.request_id, event.data))
        elif event.type == "output":
            if isinstance(event.data, AgentResponseUpdate):
                update = event.data
                response_id = update.response_id
                if response_id != last_response_id:
                    if last_response_id is not None:
                        print()
                    print(f"{update.author_name}: {update.text}", end="", flush=True)
                    last_response_id = response_id
                else:
                    print(update.text, end="", flush=True)
            else:
                print(f"\n{event.executor_id}: {event.data}")

    if requests:
        responses: dict[str, str] = {}
        for request_id, request in requests:
            print(f"\nHITL: {request.prompt}")
            answer = input("Enter higher/lower/correct/exit: ").lower()  # noqa: ASYNC250
            if answer == "exit":
                print("Exiting...")
                return None
            responses[request_id] = answer
        return responses

    return None


# <running>
async def main() -> None:
    """Run the human-in-the-loop guessing game workflow."""
    guessing_agent = AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        name="GuessingAgent",
        instructions=(
            "You guess a number between 1 and 10. "
            "If the user says 'higher' or 'lower', adjust your next guess. "
            'You MUST return ONLY a JSON object exactly matching this schema: {"guess": <integer 1..10>}. '
            "No explanations or additional text."
        ),
        default_options={"response_format": GuessOutput},
    )
    turn_manager = TurnManager(id="turn_manager")

    # Build a loop: TurnManager <-> AgentExecutor
    workflow = (
        WorkflowBuilder(start_executor=turn_manager)
        .add_edge(turn_manager, guessing_agent)
        .add_edge(guessing_agent, turn_manager)
    ).build()

    stream = workflow.run("start", stream=True)
    pending_responses = await process_event_stream(stream)
    while pending_responses is not None:
        stream = workflow.run(stream=True, responses=pending_responses)
        pending_responses = await process_event_stream(stream)
# </running>


if __name__ == "__main__":
    asyncio.run(main())
