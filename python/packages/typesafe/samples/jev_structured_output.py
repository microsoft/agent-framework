# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio

from agent_framework import Agent, Message
from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse

from agent_framework_typesafe import TypeSafeChatClient, TypeSafeChatOptions

load_dotenv()

"""
TypeSafe AI Jev structured-output chat client example.

This connector uses Agent Framework's ``response_format`` option differently
from regular chat clients:

- ``response_format`` is a TypeSafe ``Questions`` mapping, not a Pydantic output model.
- ``response.value`` is the typed ``SystemOneResponse`` returned by TypeSafe.
- ``response.text`` is the serialized JSON response when no tool was executed.

The three TypeSafe response primitives are:

- ``Noul``: a yes/no probability in ``answer.noul``. It has no separate confidence.
- ``Choice``: one selected label, its probability distribution, and ``confidence``.
- ``Score``: a probability-weighted position across ordered rubric levels, plus
  its legend, probability distribution, and ``confidence``.

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
    # 1. Define the TypeSafe Questions mapping passed through response_format.
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

    # The question IDs become the keys in SystemOneResponse.answers and its typed views:
    # response.nouls, response.choices, and response.scores.
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
        # Prefer response.value when code needs typed answers and probabilities.
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

``response.value`` also contains:
- ``answers``: all answers keyed by the configured question IDs.
- ``choices`` / ``nouls`` / ``scores``: typed views grouped by primitive.
- ``model`` and ``usage``: the TypeSafe model and token counts.
"""
