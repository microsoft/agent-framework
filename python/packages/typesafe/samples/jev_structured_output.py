# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio

from agent_framework import Agent, Message
from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse

from agent_framework_typesafe import TypeSafeChatClient, TypeSafeChatOptions

"""
TypeSafe AI Jev structured-output chat client example.

Jev is a System One decision model, not a generative chat model. Every request
provides typed questions, and every response contains structured answers.

Environment variables:
    TYPESAFE_API_KEY — TypeSafe API key.
"""


def print_evaluation(label: str, response: SystemOneResponse) -> None:
    """Print the typed answers returned by Jev."""
    print(f"\n{label}")
    print(f"Department: {response.choices['department'].choice}")
    print(f"Department confidence: {response.choices['department'].confidence:.3f}")
    print(f"Frustration score: {response.scores['frustration'].score:.3f}")
    print(f"Urgency probability: {response.nouls['is_urgent'].noul:.3f}")


async def main() -> None:
    """Run Jev through both the chat client and Agent Framework Agent APIs."""
    # 1. Define the typed judgments Jev should make for every support request.
    questions: Questions = {
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
    options: TypeSafeChatOptions = {"response_format": questions}

    direct_ticket = "I was charged twice for the same subscription. Please refund the duplicate charge."
    agent_ticket = "Our checkout integration has failed for three days and we are losing sales. Please help ASAP."

    # 2. Create the package client. It owns and closes the TypeSafe SDK client.
    async with TypeSafeChatClient() as client:
        # 3. Call the structured-output chat client directly.
        direct_response = await client.get_response(
            [Message(role="user", contents=[direct_ticket])],
            options=options,
        )
        if not isinstance(direct_response.value, SystemOneResponse):
            raise RuntimeError("TypeSafe did not return the required structured response.")
        print_evaluation("Direct TypeSafeChatClient result:", direct_response.value)

        # 4. Use the same client through an Agent Framework Agent.
        agent = Agent(
            client=client,
            name="JevTicketEvaluator",
            instructions="Evaluate the support request using the configured TypeSafe questions.",
        )
        agent_response = await agent.run(agent_ticket, options=options)
        if not isinstance(agent_response.value, SystemOneResponse):
            raise RuntimeError("The agent did not return the required structured response.")
        print_evaluation("Agent result:", agent_response.value)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (probabilities and scores vary):

Direct TypeSafeChatClient result:
Department: billing
Department confidence: 1.000
Frustration score: 0.070
Urgency probability: 0.220

Agent result:
Department: technical
Department confidence: 0.970
Frustration score: 1.000
Urgency probability: 0.980
"""
