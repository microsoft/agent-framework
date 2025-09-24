# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import (
    AgentExecutor,  # Executor that runs the agent
    AgentExecutorRequest,  # Message bundle sent to an AgentExecutor
    AgentExecutorResponse,  # Result returned by an AgentExecutor
    ChatMessage,  # Chat message structure
    Executor,  # Base class for workflow executors
    RequestInfoEvent,  # Event emitted when human input is requested
    RequestInfoExecutor,  # Special executor that collects human input out of band
    RequestInfoMessage,  # Base class for request payloads sent to RequestInfoExecutor
    RequestResponse,  # Correlates a human response with the original request
    Role,  # Enum of chat roles (user, assistant, system)
    WorkflowBuilder,  # Fluent builder for assembling the graph
    WorkflowContext,  # Per run context and event bus
    WorkflowOutputEvent,  # Event emitted when workflow yields output
    WorkflowRunState,  # Enum of workflow run states
    WorkflowStatusEvent,  # Event emitted on run state changes
    handler,  # Decorator to expose an Executor method as a step
)
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel

"""
Sample: Human in the loop guessing game

An agent guesses a number, then a human guides it with higher, lower, or
correct via RequestInfoExecutor. The loop continues until the human confirms
correct, at which point the workflow completes when idle with no pending work.

Purpose:
Show how to integrate a human step in the middle of an LLM workflow using RequestInfoExecutor and correlated
RequestResponse objects.

Demonstrate:
- Alternating turns between an AgentExecutor and a human, driven by events.
- Using Pydantic response_format to enforce structured JSON output from the agent instead of regex parsing.
- Driving the loop in application code with run_stream and send_responses_streaming.

Prerequisites:
- Azure OpenAI configured for AzureChatClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, executors, edges, events, and streaming runs.
"""

# What RequestInfoExecutor does:
# RequestInfoExecutor is a workflow-native bridge that pauses the graph at a request for information,
# emits a RequestInfoEvent with a typed payload, and then resumes the graph only after your application
# supplies a matching RequestResponse keyed by the emitted request_id. It does not gather input by itself.
# Your application is responsible for collecting the human reply from any UI or CLI and then calling
# send_responses_streaming with a dict mapping request_id to the human's answer. The executor exists to
# standardize pause-and-resume human gating, to carry typed request payloads, and to preserve correlation.


# Request type sent to the RequestInfoExecutor for human feedback.
# Including the agent's last guess allows the UI or CLI to display context and helps
# the turn manager avoid extra state reads.
# Why subclass RequestInfoMessage:
# Subclassing RequestInfoMessage defines the exact schema of the request that the human will see.
# This gives you strong typing, forward-compatible validation, and clear correlation semantics.
# It also lets you attach contextual fields (such as the previous guess) so the UI can render a rich prompt
# without fetching extra state from elsewhere.
@dataclass
class HumanFeedbackRequest(RequestInfoMessage):
    prompt: str = ""
    guess: int | None = None


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
        ctx: WorkflowContext[HumanFeedbackRequest],
    ) -> None:
        """Handle the agent's guess and request human guidance.

        Steps:
        1) Parse the agent's JSON into GuessOutput for robustness.
        2) Send a HumanFeedbackRequest to the RequestInfoExecutor with a clear instruction:
           - higher means the human's secret number is higher than the agent's guess.
           - lower means the human's secret number is lower than the agent's guess.
           - correct confirms the guess is exactly right.
           - exit quits the demo.
        """
        # Parse structured model output (defensive default if the agent did not reply).
        text = result.agent_run_response.text or ""
        last_guess = GuessOutput.model_validate_json(text).guess if text else None

        # Craft a precise human prompt that defines higher and lower relative to the agent's guess.
        prompt = (
            f"The agent guessed: {last_guess if last_guess is not None else text}. "
            "Type one of: higher (your number is higher than this guess), "
            "lower (your number is lower than this guess), correct, or exit."
        )
        await ctx.send_message(HumanFeedbackRequest(prompt=prompt, guess=last_guess))

    @handler
    async def on_human_feedback(
        self,
        feedback: RequestResponse[HumanFeedbackRequest, str],
        ctx: WorkflowContext[AgentExecutorRequest, str],
    ) -> None:
        """Continue the game or finish based on human feedback.

        The RequestResponse contains both the human's string reply and the correlated HumanFeedbackRequest,
        which carries the prior guess for convenience.
        """
        reply = (feedback.data or "").strip().lower()
        # Prefer the correlated request's guess to avoid extra shared state reads.
        last_guess = getattr(feedback.original_request, "guess", None)

        if reply == "correct":
            await ctx.yield_output(f"Guessed correctly: {last_guess}")
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

    # Build a simple loop: TurnManager <-> AgentExecutor <-> RequestInfoExecutor.
    # TurnManager coordinates, AgentExecutor runs the model, RequestInfoExecutor gathers human replies.
    turn_manager = TurnManager(id="turn_manager")
    agent_exec = AgentExecutor(agent=agent, id="agent")

    # Naming note:
    # This variable is currently named hitl for historical reasons. The name can feel ambiguous or magical.
    # Consider renaming to request_info_executor in your own code for clarity, since it directly represents
    # the RequestInfoExecutor node that gathers human replies out of band.
    hitl = RequestInfoExecutor(id="request_info")

    top_builder = (
        WorkflowBuilder()
        .set_start_executor(turn_manager)
        .add_edge(turn_manager, agent_exec)  # Ask agent to make/adjust a guess
        .add_edge(agent_exec, turn_manager)  # Agent's response comes back to coordinator
        .add_edge(turn_manager, hitl)  # Ask human for guidance
        .add_edge(hitl, turn_manager)  # Feed human guidance back to coordinator
    )

    # Build the workflow (no checkpointing in this minimal sample).
    workflow = top_builder.build()

    # Human in the loop run: alternate between invoking the workflow and supplying collected responses.
    pending_responses: dict[str, str] | None = None
    completed = False
    workflow_output: str | None = None

    # User guidance printing:
    # If you want to instruct users up front, print a short banner before the loop.
    # Example:
    # print(
    #     "Interactive mode. When prompted, type one of: higher, lower, correct, or exit. "
    #     "The agent will keep guessing until you reply correct.",
    #     flush=True,
    # )

    while not completed:
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
                completed = True  # In this sample, we finish after one output.

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
        if requests and not completed:
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
