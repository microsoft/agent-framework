# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "python-dotenv",
#     "typesafe-sdk>=0.7.0",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/02-agents/providers/typesafe/jev_structured_output.py

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Mapping, Sequence
from typing import Any, ClassVar

from agent_framework import (
    Agent,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Message,
    ResponseStream,
    UsageDetails,
)
from dotenv import load_dotenv
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Question, Score, SystemOneResponse

load_dotenv()

"""
TypeSafe AI Jev structured-output chat client example.

Jev is a System One decision model, not a generative chat model. This sample adapts
Agent Framework messages into Jev state and requires every request to provide:

- ``questions`` containing TypeSafe Noul, Choice, or Score questions.
- ``response_format`` set to ``typesafe_sdk.SystemOneResponse``.

Streaming, tools, non-text content, and free-form generation options are rejected.

Environment variables:
    TYPESAFE_API_KEY  — TypeSafe API key.
"""


class JevChatOptions(ChatOptions[SystemOneResponse], total=False):
    """Chat options supported by the Jev adapter."""

    questions: Mapping[str, Question]


class JevChatClient(BaseChatClient[JevChatOptions]):
    """Adapt TypeSafe AI Jev's structured decision API to Agent Framework."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "typesafe.ai"
    _SUPPORTED_OPTIONS: ClassVar[frozenset[str]] = frozenset({
        "instructions",
        "model",
        "questions",
        "response_format",
        "tool_choice",
    })

    def __init__(
        self,
        *,
        sdk_client: AsyncTypeSafeClient,
        model: str = "jev-latest",
    ) -> None:
        """Initialize the adapter with an externally managed TypeSafe client.

        Args:
            sdk_client: An asynchronous TypeSafe SDK client.
            model: Default Jev model used when a request does not override it.
        """
        super().__init__()
        self._sdk_client = sdk_client
        self._model = model

    def service_url(self) -> str:
        """Return the TypeSafe System One service endpoint."""
        return "https://api.typesafe.ai/v1/systemone"

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Evaluate text messages with Jev and return its structured response."""
        if stream:
            raise ValueError("Jev does not support streaming responses.")
        if kwargs:
            raise ValueError(f"Jev does not support client-specific arguments: {', '.join(sorted(kwargs))}.")

        async def _get_response() -> ChatResponse:
            normalized_options = await self._validate_options(options)
            unsupported_options = sorted(
                key
                for key, value in normalized_options.items()
                if key not in self._SUPPORTED_OPTIONS and value is not None
            )
            if unsupported_options:
                raise ValueError(
                    "Jev does not support these chat options: "
                    f"{', '.join(unsupported_options)}. Use questions to define the structured judgments."
                )
            if normalized_options.get("tool_choice") not in (None, "auto", "none"):
                raise ValueError("Jev does not support required tool choice.")

            response_format = normalized_options.get("response_format")
            if not isinstance(response_format, type) or not issubclass(response_format, SystemOneResponse):
                raise ValueError(
                    "Jev requires options['response_format'] to be typesafe_sdk.SystemOneResponse or a subclass."
                )

            questions = normalized_options.get("questions")
            if not isinstance(questions, Mapping) or not questions:
                raise ValueError("Jev requires a non-empty options['questions'] mapping.")

            state = _build_jev_state(
                messages,
                instructions=normalized_options.get("instructions"),
            )
            response = await self._sdk_client.system_one(
                state=state,
                questions=questions,
                model=normalized_options.get("model", self._model),
                response_model=response_format,
            )

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            usage_details = UsageDetails(
                **({"input_token_count": input_tokens} if input_tokens is not None else {}),
                **({"output_token_count": output_tokens} if output_tokens is not None else {}),
                **(
                    {"total_token_count": input_tokens + output_tokens}
                    if input_tokens is not None and output_tokens is not None
                    else {}
                ),
            )

            return ChatResponse(
                messages=[Message(role="assistant", contents=[response.model_dump_json()])],
                response_id=response.request_id,
                model=response.model,
                finish_reason="stop",
                usage_details=usage_details or None,
                value=response,
                response_format=response_format,
                raw_representation=response,
            )

        return _get_response()


def _build_jev_state(messages: Sequence[Message], *, instructions: str | None) -> dict[str, Any]:
    """Convert text-only Agent Framework messages into structured Jev state."""
    state_messages: list[dict[str, str]] = []

    for index, message in enumerate(messages):
        unsupported_content_types = sorted({content.type for content in message.contents if content.type != "text"})
        if unsupported_content_types:
            raise ValueError(
                f"Jev only supports text message content; message {index} contains: "
                f"{', '.join(unsupported_content_types)}."
            )

        if message.text:
            state_messages.append({
                "role": str(message.role),
                "content": message.text,
            })

    if not state_messages:
        raise ValueError("Jev requires at least one non-empty text message.")

    state: dict[str, Any] = {"messages": state_messages}
    if instructions:
        state["instructions"] = instructions
    return state


def _get_api_key() -> str:
    """Resolve the TypeSafe API key."""
    api_key = os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        raise RuntimeError("Set TYPESAFE_API_KEY before running this sample.")
    return api_key


def _print_evaluation(label: str, response: SystemOneResponse) -> None:
    """Print the typed answers returned by Jev."""
    print(f"\n{label}")
    print(f"Department: {response.choices['department'].choice}")
    print(f"Department confidence: {response.choices['department'].confidence:.3f}")
    print(f"Frustration score: {response.scores['frustration'].score:.3f}")
    print(f"Urgency probability: {response.nouls['is_urgent'].noul:.3f}")


async def main() -> None:
    """Run Jev through both the chat client and Agent Framework Agent APIs."""
    # 1. Define the typed judgments Jev should make for every support request.
    questions: dict[str, Question] = {
        "department": Choice(
            instructions="Which team should handle the support request?",
            criteria={
                "billing": "Payments, subscriptions, invoices, or refunds",
                "technical": "Bugs, outages, integrations, or account access",
                "sales": "Pricing, upgrades, or new account questions",
            },
        ),
        "frustration": Score(
            instructions="How frustrated does the customer appear?",
            criteria=[
                "Calm and factual",
                "Frustrated but civil",
                "Very angry or threatening to leave",
            ],
        ),
        "is_urgent": Noul(
            instructions="Does the request require urgent attention?",
            criteria={
                "true": "The customer describes ongoing harm, lost revenue, or an immediate deadline",
                "false": "The request can wait for the normal support queue",
            },
        ),
    }

    direct_ticket = "I was charged twice for the same subscription. Please refund the duplicate charge."
    agent_ticket = "Our checkout integration has failed for three days and we are losing sales. Please help ASAP."

    # 2. Create the SDK client and adapt it to the Agent Framework chat client contract.
    async with AsyncTypeSafeClient(api_key=_get_api_key(), model="jev-latest") as sdk_client:
        client = JevChatClient(sdk_client=sdk_client)
        options: JevChatOptions = {
            "questions": questions,
            "response_format": SystemOneResponse,
        }

        # 3. Call the structured-output chat client directly.
        direct_response = await client.get_response(
            [Message(role="user", contents=[direct_ticket])],
            options=options,
        )
        if not isinstance(direct_response.value, SystemOneResponse):
            raise RuntimeError("Jev did not return the required structured response.")
        _print_evaluation("Direct JevChatClient result:", direct_response.value)

        # 4. Use the same client through an Agent Framework Agent.
        agent = Agent(
            client=client,
            name="JevTicketEvaluator",
            instructions="Evaluate the support request using the configured TypeSafe questions.",
        )
        agent_response = await agent.run(agent_ticket, options=options)
        if not isinstance(agent_response.value, SystemOneResponse):
            raise RuntimeError("The agent did not return the required structured response.")
        _print_evaluation("Agent result:", agent_response.value)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (probabilities and scores vary):

Direct JevChatClient result:
Department: billing
Department confidence: 0.900
Frustration score: 1.100
Urgency probability: 0.650

Agent result:
Department: technical
Department confidence: 0.950
Frustration score: 1.700
Urgency probability: 0.990
"""
