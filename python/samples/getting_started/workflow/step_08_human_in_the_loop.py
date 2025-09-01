# Copyright (c) Microsoft. All rights reserved.

"""
Human-in-the-loop (HITL) guessing game with an AgentExecutor + checkpointing.

Flow:
- TurnManager starts the game by prompting an agent to guess a number (1-10).
- After each agent guess, TurnManager asks a human for feedback via RequestInfoExecutor
    ("higher", "lower", or "correct").
- The workflow pauses and emits a RequestInfoEvent; we show the latest checkpoint ID so you
    can resume the workflow later. You can also set CHECKPOINT_ID env var to start from a prior checkpoint.
"""

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_framework import ChatMessage, ChatRole
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    FileCheckpointStorage,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from agent_framework_workflow import AgentRunEvent
from azure.identity import AzureCliCredential


# Request type sent to the RequestInfoExecutor for human feedback
@dataclass
class HumanFeedbackRequest(RequestInfoMessage):
    prompt: str = ""


class TurnManager(AgentExecutor):
    """Manages the turn-taking between the agent and a human."""

    def __init__(self, agent: Any, id: str | None = None):
        super().__init__(agent, id=id)

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        """Kick off the game by asking the agent for an initial guess."""
        system = ChatMessage(
            ChatRole.SYSTEM,
            text=(
                "We're playing a number guessing game between 1 and 10.\n"
                "Always respond in the exact format: 'GUESS: <n>' with no explanations.\n"
                "After you receive human feedback 'higher' or 'lower', try again. If 'correct', stop."
            ),
        )
        user = ChatMessage(ChatRole.USER, text="Start by making your first guess.")

        await ctx.send_message(AgentExecutorRequest(messages=[system, user], should_respond=True))

    @handler
    async def on_agent_response(
        self,
        result: AgentExecutorResponse,
        ctx: WorkflowContext[HumanFeedbackRequest],
    ) -> None:
        """Handle the agent's guess and request human feedback."""
        text = result.agent_run_response.text or ""

        # Extract last guess (expects 'GUESS: <n>')
        m = re.search(r"GUESS:\s*(\d+)", text)
        last_guess = int(m.group(1)) if m else None
        await ctx.set_state({"last_guess": last_guess, "raw": text})

        # Ask the human for guidance
        prompt = f"The agent guessed: {last_guess if last_guess is not None else text}. Type one of: higher, lower, correct, exit"  # noqa: E501
        await ctx.send_message(HumanFeedbackRequest(prompt=prompt))

    @handler
    async def on_human_feedback(
        self,
        feedback: RequestResponse[HumanFeedbackRequest, str],
        ctx: WorkflowContext[AgentExecutorRequest | WorkflowCompletedEvent],
    ) -> None:
        """Continue the game or finish, based on human feedback."""
        reply = (feedback.data or "").strip().lower()
        state = await ctx.get_state() or {}
        last_guess = state.get("last_guess")

        if reply == "correct":
            await ctx.add_event(WorkflowCompletedEvent(f"Guessed correctly: {last_guess}"))
            return

        # Provide feedback to the agent to try again
        user_msg = ChatMessage(
            ChatRole.USER,
            text=(f"Feedback: {reply}. Try another guess. Remember to respond strictly as 'GUESS: <n>'."),
        )
        await ctx.send_message(AgentExecutorRequest(messages=[user_msg], should_respond=True))


async def main() -> None:
    # Configure checkpoint storage in the sample folder
    dir_path = Path(__file__).parent
    temp_dir = dir_path / "tmp" / "checkpoints"
    temp_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_storage = FileCheckpointStorage(storage_path=str(temp_dir))

    # Create the chat agent and wrap it in an AgentExecutor
    chat_client = AzureChatClient(credential=AzureCliCredential())
    agent = chat_client.create_agent(
        instructions=(
            "You guess a number between 1 and 10. Always reply only as 'GUESS: <n>'. "
            "If the user says 'higher' or 'lower', adjust your next guess. "
            "Make it fun and don't always guess the same number."
        )
    )

    # Build a single-level workflow: TurnManager <-> RequestInfoExecutor
    turn_manager = TurnManager(agent, id="turn_manager")
    hitl = RequestInfoExecutor(id="request_info")
    top_builder = (
        WorkflowBuilder()
        .set_start_executor(turn_manager)
        .add_edge(turn_manager, turn_manager)  # TurnManager executes its own agent step
        .add_edge(turn_manager, hitl)  # Ask human for guidance
        .add_edge(hitl, turn_manager)  # Feed human guidance back to the agent turn manager
    )

    # If CHECKPOINT_ID is set, resume from that checkpoint using the top-level workflow
    # without enabling checkpointing anew.
    env_checkpoint_id = os.environ.get("CHECKPOINT_ID")
    if env_checkpoint_id:
        workflow = top_builder.build()
        print(f"Resuming from checkpoint: {env_checkpoint_id}")
    else:
        workflow = top_builder.with_checkpointing(checkpoint_storage=checkpoint_storage).build()

    # Human-in-the-loop run: alternate between running and feeding responses as needed
    pending_responses: dict[str, str] | None = None
    completed: WorkflowCompletedEvent | None = None
    first_iteration = True

    async def get_latest_checkpoint_id() -> str | None:
        """Return latest checkpoint id for this workflow (if any)."""
        checkpoints = await checkpoint_storage.list_checkpoints(workflow_id=workflow.id)
        if not checkpoints:
            return None
        checkpoints.sort(key=lambda cp: cp.timestamp)
        return checkpoints[-1].checkpoint_id

    while not completed:
        if first_iteration and env_checkpoint_id:
            stream = workflow.run_streaming_from_checkpoint(env_checkpoint_id, checkpoint_storage=checkpoint_storage)
        else:
            stream = (
                workflow.send_responses_streaming(pending_responses)
                if pending_responses
                else workflow.run_streaming("start")
            )
        events = [event async for event in stream]
        pending_responses = None
        first_iteration = False

        requests: list[tuple[str, str]] = []  # (request_id, prompt)
        for event in events:
            if isinstance(event, WorkflowCompletedEvent):
                completed = event
            elif isinstance(event, RequestInfoEvent) and isinstance(event.data, HumanFeedbackRequest):
                # RequestInfoEvent for our HumanFeedbackRequest
                requests.append((event.request_id, event.data.prompt))
            elif isinstance(event, AgentRunEvent):
                # Print other events for visibility (optional)
                print(event)

        # If we have any human requests, prompt the user and prepare responses
        if requests and not completed:
            # Print the latest checkpoint so a user can safely exit and resume later.
            latest = await get_latest_checkpoint_id()
            if latest:
                print(f"Checkpoint available. Set CHECKPOINT_ID={latest} to resume later.")

            responses: dict[str, str] = {}
            for req_id, prompt in requests:
                # Simple console prompt for the sample
                print(f"HITL> {prompt}")
                answer = input("Enter higher/lower/correct/exit: ").lower()
                if answer == "exit":
                    latest_id = await get_latest_checkpoint_id()
                    print("Exiting...")
                    if latest_id:
                        print(f"You can resume by re-running with the environment variable CHECKPOINT_ID={latest_id}")
                    return
                responses[req_id] = answer
            pending_responses = responses

    # Show final result
    print(completed)


if __name__ == "__main__":
    asyncio.run(main())
