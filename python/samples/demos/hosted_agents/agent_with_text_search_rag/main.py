# Copyright (c) Microsoft. All rights reserved.

import json
import sys
from collections.abc import MutableSequence
from dataclasses import dataclass
from typing import Any

from agent_framework import ChatMessage, Context, ContextProvider, Role
from agent_framework.azure import AzureOpenAIChatClient
from azure.ai.agentserver.agentframework import from_agent_framework  # pyright: ignore[reportUnknownVariableType]
from azure.identity import DefaultAzureCredential

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


@dataclass
class TextSearchResult:
    source_name: str
    source_link: str
    text: str


class TextSearchContextProvider(ContextProvider):
    """A simple context provider that simulates text search results based on keywords in the user's message."""

    def _get_most_recent_message(self, messages: ChatMessage | MutableSequence[ChatMessage]) -> ChatMessage:
        """Helper method to extract the most recent message from the input."""
        if isinstance(messages, ChatMessage):
            return messages
        if messages:
            return messages[-1]
        raise ValueError("No messages provided")

    @override
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        message = self._get_most_recent_message(messages)
        query = message.text.lower()

        results: list[TextSearchResult] = []
        if "return" in query and "refund" in query:
            results.append(
                TextSearchResult(
                    source_name="Contoso Outdoors Return Policy",
                    source_link="https://contoso.com/policies/returns",
                    text=(
                        "Customers may return any item within 30 days of delivery. "
                        "Items should be unused and include original packaging. "
                        "Refunds are issued to the original payment method within 5 business days of inspection."
                    ),
                )
            )

        if "shipping" in query:
            results.append(
                TextSearchResult(
                    source_name="Contoso Outdoors Shipping Guide",
                    source_link="https://contoso.com/help/shipping",
                    text=(
                        "Standard shipping is free on orders over $50 and typically arrives in 3-5 business days "
                        "within the continental United States. Expedited options are available at checkout."
                    ),
                )
            )

        if "tent" in query or "fabric" in query:
            results.append(
                TextSearchResult(
                    source_name="TrailRunner Tent Care Instructions",
                    source_link="https://contoso.com/manuals/trailrunner-tent",
                    text=(
                        "Clean the tent fabric with lukewarm water and a non-detergent soap. "
                        "Allow it to air dry completely before storage and avoid prolonged UV "
                        "exposure to extend the lifespan of the waterproof coating."
                    ),
                )
            )

        if not results:
            return Context()

        return Context(
            messages=[
                ChatMessage(
                    role=Role.USER, text="\n\n".join(json.dumps(result.__dict__, indent=2) for result in results)
                )
            ]
        )


def main():
    # Create an Agent using the Azure OpenAI Chat Client
    agent = AzureOpenAIChatClient(credential=DefaultAzureCredential()).create_agent(
        name="SupportSpecialist",
        instructions=(
            "You are a helpful support specialist for Contoso Outdoors. "
            "Answer questions using the provided context and cite the source document when available."
        ),
        context_providers=TextSearchContextProvider(),
    )

    # Run the agent as a hosted agent
    from_agent_framework(agent).run()


if __name__ == "__main__":
    main()
