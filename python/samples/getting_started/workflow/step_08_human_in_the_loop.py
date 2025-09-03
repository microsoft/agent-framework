# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import AIAgent, ChatMessage, ChatRole
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from azure.identity import AzureCliCredential
from pydantic import BaseModel

"""
Human-in-the-loop (HITL) Guessing Game

What it does:
- An agent guesses numbers; a human provides feedback via `RequestInfoExecutor`.
- Uses structured output (Pydantic `GuessOutput`) instead of regex parsing.
- Alternates turns until the human replies "correct". No checkpointing or resume.

Prerequisites:
- Azure AI/ Azure OpenAI for `AzureChatClient` agent.
- Authentication via `azure-identity` — uses `AzureCliCredential()` (run `az login`).
"""


# Request type sent to the RequestInfoExecutor for human feedback
@dataclass
class HumanFeedbackRequest(RequestInfoMessage):
    prompt: str = ""
    guess: int | None = None


class GuessOutput(BaseModel):
    guess: int


class TurnManager(AgentExecutor):
    """Manages the turn-taking between the agent and a human."""

    def __init__(self, agent: AIAgent, id: str | None = None):
        super().__init__(agent, id=id)

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """Kick off the game by asking the agent for an initial guess."""
        user = ChatMessage(ChatRole.USER, text="Start by making your first guess.")
        await ctx.send_message(AgentExecutorRequest(messages=[user], should_respond=True))

    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext[HumanFeedbackRequest],
    ) -> None:
        """Handle the agent's guess and request human feedback."""
        # Parse structured model output
        text = result.agent_run_response.text or ""
        last_guess = GuessOutput.model_validate_json(text).guess if text else None

        # Ask the human for guidance (carry the guess in the request)
        prompt = f"The agent guessed: {last_guess if last_guess is not None else text}. Type one of: higher, lower, correct, exit"  # noqa: E501
        await ctx.send_message(HumanFeedbackRequest(prompt=prompt, guess=last_guess))

    @handler
    async def on_human_feedback(
        self,
        feedback: RequestResponse[HumanFeedbackRequest, str],
        ctx: WorkflowContext[AgentExecutorRequest | WorkflowCompletedEvent],
    ) -> None:
        """Continue the game or finish, based on human feedback."""
        reply = (feedback.data or "").strip().lower()
        # Prefer the correlated request's guess (no need to read state)
        last_guess = getattr(feedback.original_request, "guess", None)

        if reply == "correct":
            await ctx.add_event(WorkflowCompletedEvent(f"Guessed correctly: {last_guess}"))
            return

        # Provide feedback to the agent to try again
        user_msg = ChatMessage(
            ChatRole.USER,
            text=(f'Feedback: {reply}. Return ONLY a JSON object matching the schema {{"guess": <int 1..10>}}.'),
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))


async def main() -> None:
    # Create the chat agent and wrap it in an AgentExecutor
    chat_client = AzureChatClient(credential=AzureCliCredential())
    agent = chat_client.create_agent(
        instructions=(
            "You guess a number between 1 and 10. "
            "If the user says 'higher' or 'lower', adjust your next guess. "
            'You MUST return ONLY a JSON object exactly matching this schema: {"guess": <integer 1..10>}. '
            "No explanations or additional text."
        ),
        response_format=GuessOutput,
    )

    # Build a single-level workflow: TurnManager <-> RequestInfoExecutor
    turn_manager = TurnManager(agent=agent, id="turn_manager")
    hitl = RequestInfoExecutor(id="request_info")
    top_builder = (
        WorkflowBuilder()
        .set_start_executor(turn_manager)
        .add_edge(turn_manager, turn_manager)  # TurnManager executes its own agent step
        .add_edge(turn_manager, hitl)  # Ask human for guidance
        .add_edge(hitl, turn_manager)  # Feed human guidance back to the agent turn manager
    )

    # Build the workflow (no checkpointing)
    workflow = top_builder.build()

    # Human-in-the-loop run: alternate between running and feeding responses as needed
    pending_responses: dict[str, str] | None = None
    completed: WorkflowCompletedEvent | None = None

    while not completed:
        stream = (
            workflow.send_responses_streaming(pending_responses)
            if pending_responses
            else workflow.run_streaming("start")
        )
        events = [event async for event in stream]
        pending_responses = None

        requests: list[tuple[str, str]] = []  # (request_id, prompt)
        for event in events:
            if isinstance(event, WorkflowCompletedEvent):
                completed = event
            elif isinstance(event, RequestInfoEvent) and isinstance(event.data, HumanFeedbackRequest):
                # RequestInfoEvent for our HumanFeedbackRequest
                requests.append((event.request_id, event.data.prompt))
            # Other events are ignored for brevity

        # If we have any human requests, prompt the user and prepare responses
        if requests and not completed:
            responses: dict[str, str] = {}
            for req_id, prompt in requests:
                # Simple console prompt for the sample
                print(f"HITL> {prompt}")
                answer = input("Enter higher/lower/correct/exit: ").lower()
                if answer == "exit":
                    print("Exiting...")
                    return
                responses[req_id] = answer
            pending_responses = responses

    # Show final result
    print(completed)

    """
    Sample Output:

    HITL> The agent guessed: 5. Type one of: higher, lower, correct, exit
    Enter higher/lower/correct/exit: higher
    HITL> The agent guessed: 8. Type one of: higher, lower, correct, exit
    Enter higher/lower/correct/exit: higher
    HITL> The agent guessed: 10. Type one of: higher, lower, correct, exit
    Enter higher/lower/correct/exit: lower
    HITL> The agent guessed: 9. Type one of: higher, lower, correct, exit
    Enter higher/lower/correct/exit: correct
    WorkflowCompletedEvent(data=Guessed correctly: 9)
    """


if __name__ == "__main__":
    asyncio.run(main())
