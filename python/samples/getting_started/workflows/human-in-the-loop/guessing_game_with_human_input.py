# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import (
    AgentExecutorRequest,  # Message bundle sent to an AgentExecutor
    AgentExecutorResponse,  # Result returned by an AgentExecutor
    ChatMessage,  # Chat message structure
    Executor,  # Base class for workflow executors
    RequestInfoEvent,  # Event emitted when human input is requested
    Role,  # Enum of chat roles (user, assistant, system)
    WorkflowBuilder,  # Fluent builder for assembling the graph
    WorkflowContext,  # Per run context and event bus
    WorkflowOutputEvent,  # Event emitted when workflow yields output
    WorkflowRunState,  # Enum of workflow run states
    WorkflowStatusEvent,  # Event emitted on run state changes
    handler,
    response_handler,  # Decorator to expose an Executor method as a step
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel

"""
Sample: Human in the loop guessing game

An agent guesses a number, then a human guides it with higher, lower, or
correct. The loop continues until the human confirms correct, at which point
the workflow completes when idle with no pending work.

Purpose:
Show how to integrate a human step in the middle of an LLM workflow by using
`request_info` and `send_responses_streaming`.

Demonstrate:
- Alternating turns between an AgentExecutor and a human, driven by events.
- Using Pydantic response_format to enforce structured JSON output from the agent instead of regex parsing.
- Driving the loop in application code with run_stream and responses parameter.

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, executors, edges, events, and streaming runs.
"""

# How human-in-the-loop is achieved via `request_info` and `send_responses_streaming`:
# - An executor (TurnManager) calls `ctx.request_info` with a payload (HumanFeedbackRequest).
# - The workflow run pauses and emits a RequestInfoEvent with the payload and the request_id.
# - The application captures the event, prompts the user, and collects replies.
# - The application calls `send_responses_streaming` with a map of request_ids to replies.
# - The workflow resumes, and the response is delivered to the executor method decorated with @response_handler.
# - The executor can then continue the workflow, e.g., by sending a new message to the agent.


@dataclass
class HumanFeedbackRequest:
    """Request sent to the human for feedback on the agent's guess."""

    prompt: str


class GuessOutput(BaseModel):
    """Structured output from the agent. Enforced via response_format for reliable parsing."""

    guess: int


class TurnManager(Executor):
    """Coordinates turns between the agent and the human.

    Responsibilities:
    - Kick off the first agent turn.
    - After each agent reply, request human feedback with a HumanFeedbackRequest.
    - After each human reply, either finish the game or prompt the agent again with feedback.
    """

    def __init__(self, id: str | None = None):
        super().__init__(id=id or "turn_manager")

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """Start the game by asking the agent for an initial guess.

        Contract:
        - Input is a simple starter token (ignored here).
        - Output is an AgentExecutorRequest that triggers the agent to produce a guess.
        """
        user = ChatMessage(Role.USER, text="Start by making your first guess.")
        await ctx.send_message(AgentExecutorRequest(messages=[user], should_respond=True))

    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext,
    ) -> None:
        """Handle the agent's guess and request human guidance.

        Steps:
        1) Parse the agent's JSON into GuessOutput for robustness.
        2) Request info with a HumanFeedbackRequest as the payload.
        """
        # Parse structured model output
        text = result.agent_run_response.text
        last_guess = GuessOutput.model_validate_json(text).guess

        # Craft a precise human prompt that defines higher and lower relative to the agent's guess.
        prompt = (
            f"The agent guessed: {last_guess}. "
            "Type one of: higher (your number is higher than this guess), "
            "lower (your number is lower than this guess), correct, or exit."
        )
        # Send a request with a prompt as the payload and expect a string reply.
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
        print(f"Feedback for prompt '{original_request.prompt}' received: {feedback}")

        reply = feedback.strip().lower()

        if reply == "correct":
            await ctx.yield_output("Guessed correctly!")
            return

        # Provide feedback to the agent to try again.
        # We keep the agent's output strictly JSON to ensure stable parsing on the next turn.
        user_msg = ChatMessage(
            Role.USER,
            text=(f'Feedback: {reply}. Return ONLY a JSON object matching the schema {{"guess": <int 1..10>}}.'),
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))


async def main() -> None:
    # Create the chat agent and wrap it in an AgentExecutor.
    # response_format enforces that the model produces JSON compatible with GuessOutput.
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
    agent = chat_client.create_agent(
        name="GuessingAgent",
        instructions=(
            "You guess a number between 1 and 10. "
            "If the user says 'higher' or 'lower', adjust your next guess. "
            'You MUST return ONLY a JSON object exactly matching this schema: {"guess": <integer 1..10>}. '
            "No explanations or additional text."
        ),
        # Structured output enforced via Pydantic model.
        response_format=GuessOutput,
    )

    # TurnManager coordinates and gathers human replies while AgentExecutor runs the model.
    turn_manager = TurnManager(id="turn_manager")

    # Build a simple loop: TurnManager <-> AgentExecutor.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(turn_manager)
        .add_edge(turn_manager, agent)  # Ask agent to make/adjust a guess
        .add_edge(agent, turn_manager)  # Agent's response comes back to coordinator
    ).build()

    # Human in the loop run: alternate between invoking the workflow and supplying collected responses.
    pending_responses: dict[str, str] | None = None
    workflow_output: str | None = None

    # User guidance printing:
    # If you want to instruct users up front, print a short banner before the loop.
    # Example:
    # print(
    #     "Interactive mode. When prompted, type one of: higher, lower, correct, or exit. "
    #     "The agent will keep guessing until you reply correct.",
    #     flush=True,
    # )

    while workflow_output is None:
        # First iteration uses run_stream("start").
        # Subsequent iterations use send_responses_streaming with pending_responses from the console.
        stream = (
            workflow.send_responses_streaming(pending_responses) if pending_responses else workflow.run_stream("start")
        )
        # Collect events for this turn. Among these you may see WorkflowStatusEvent
        # with state IDLE_WITH_PENDING_REQUESTS when the workflow pauses for
        # human input, preceded by IN_PROGRESS_PENDING_REQUESTS as requests are
        # emitted.
        events = [event async for event in stream]
        pending_responses = None

        # Collect human requests, workflow outputs, and check for completion.
        requests: list[tuple[str, str]] = []  # (request_id, prompt)
        for event in events:
            if isinstance(event, RequestInfoEvent) and isinstance(event.data, HumanFeedbackRequest):
                # RequestInfoEvent for our HumanFeedbackRequest.
                requests.append((event.request_id, event.data.prompt))
            elif isinstance(event, WorkflowOutputEvent):
                # Capture workflow output as they're yielded
                workflow_output = str(event.data)

        # Detect run state transitions for a better developer experience.
        pending_status = any(
            isinstance(e, WorkflowStatusEvent) and e.state == WorkflowRunState.IN_PROGRESS_PENDING_REQUESTS
            for e in events
        )
        idle_with_requests = any(
            isinstance(e, WorkflowStatusEvent) and e.state == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
            for e in events
        )
        if pending_status:
            print("State: IN_PROGRESS_PENDING_REQUESTS (requests outstanding)")
        if idle_with_requests:
            print("State: IDLE_WITH_PENDING_REQUESTS (awaiting human input)")

        # If we have any human requests, prompt the user and prepare responses.
        if requests:
            responses: dict[str, str] = {}
            for req_id, prompt in requests:
                # Simple console prompt for the sample.
                print(f"HITL> {prompt}")
                # Instructional print already appears above. The input line below is the user entry point.
                # If desired, you can add more guidance here, but keep it concise.
                answer = input("Enter higher/lower/correct/exit: ").lower()  # noqa: ASYNC250
                if answer == "exit":
                    print("Exiting...")
                    return
                responses[req_id] = answer
            pending_responses = responses

    # Show final result from workflow output captured during streaming.
    print(f"Workflow output: {workflow_output}")
    """
    Sample Output:

    HITL> The agent guessed: 5. Type one of: higher (your number is higher than this guess), lower (your number is lower than this guess), correct, or exit.
    Enter higher/lower/correct/exit: higher
    HITL> The agent guessed: 8. Type one of: higher (your number is higher than this guess), lower (your number is lower than this guess), correct, or exit.
    Enter higher/lower/correct/exit: higher
    HITL> The agent guessed: 10. Type one of: higher (your number is higher than this guess), lower (your number is lower than this guess), correct, or exit.
    Enter higher/lower/correct/exit: lower
    HITL> The agent guessed: 9. Type one of: higher (your number is higher than this guess), lower (your number is lower than this guess), correct, or exit.
    Enter higher/lower/correct/exit: correct
    Workflow output: Guessed correctly: 9
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
