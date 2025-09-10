# Copyright (c) Microsoft. All rights reserved.

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pydantic import BaseModel

from agent_framework import AgentRunResponse, ChatClient, ChatMessage, ChatRole

from agent_framework.workflow import (
    Executor,
    handler,
    WorkflowContext,
)
from ._const import DEFAULT_REVIEW_SYSTEM_PROMPT, ReviewResult
from ._types import CriticAgentExecutorResponse


class CriticAgentExecutorRequest(BaseModel):
    """A request to a review executor.

    Attributes:
        conversation_id: The ID of the conversation being reviewed.
        last_response_id: The ID of the last response to include in the review.
        # messages: A list of chat messages to be processed by the agent.
    """

    conversation_id: str | None = None
    last_response_id: str | None = None


class CriticAgentExecutor(Executor, ABC):
    """built-in executor for reviewing agent messages."""

    def __init__(
        self,
        *,
        max_retries: int,
    ):
        super().__init__()
        self._revision = 0
        self._max_retries = max_retries

    @abstractmethod
    async def _on_run(self, messages: list[ChatMessage]) -> CriticAgentExecutorResponse:
        pass

    @handler
    async def run(self, request: CriticAgentExecutorRequest, ctx: WorkflowContext[CriticAgentExecutorResponse]) -> None:

        # (TODO) fetch run chat history from agent v2 API, by conversation_id or last_response_id
        # Mock chat history
        messages_chat_history = [
            ChatMessage(
                role=ChatRole.USER,
                text="What is the capital of France?",
            ),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                text="The capital of France is Paris."
            ),
        ]

        response = await self._on_run(messages_chat_history)

        # Send the review response.
        await ctx.send_message(response)


class CriticAgentMetricExecutor(Executor):
    # TODO: finish shi
    pass


class CriticAgentPromptExecutor(CriticAgentExecutor):
    def __init__(
        self,
        *,
        max_retries: int,
        chat_client: ChatClient,
        reviewer_prompt: str = None,
    ):
        super().__init__(max_retries=max_retries)
        self._max_retries = max_retries
        self._chat_client = chat_client
        self._reviewer_prompt = reviewer_prompt

    async def _on_run(self, messages_chat_history: list[ChatMessage]) -> CriticAgentExecutorResponse:
        self._revision += 1
        if self._revision >= self._max_retries:
            return CriticAgentExecutorResponse(
                approved=ReviewResult.TIMEOUT,
                feedback="Maximum number of retries reached without approval.",
                suggestions=None,
            )

        # Define the system prompt.
        messages = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                text=DEFAULT_REVIEW_SYSTEM_PROMPT,
            )
        ]

        messages.extend(messages_chat_history)

        # Add add one more instruction for the assistant to follow.
        messages.append(
            ChatMessage(role=ChatRole.USER, text="Please provide a review of the agent's responses to the user.")
        )

        print("🔍 Reviewer: Sending review request to LLM...")
        # Get the response from the chat client.
        response = await self._chat_client.get_response(messages=messages, response_format=CriticAgentExecutorResponse)

        # Parse the response.
        parsed = CriticAgentExecutorResponse.model_validate_json(response.messages[-1].text)

        print(f"🔍 Reviewer: Review complete - Approved: {parsed.approved}")
        print(f"🔍 Reviewer: Feedback: {parsed.feedback}")
        return parsed
