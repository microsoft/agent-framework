# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

from agent_framework import Agent, AgentLoopMiddleware, ChatContext, ChatResponse, chat_middleware
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_typesafe import TypeSafeChatClient

load_dotenv()

"""
Use TypeSafeChatClient directly as the AgentLoopMiddleware judge.

``AgentLoopMiddleware.with_judge`` requests the Pydantic ``JudgeVerdict`` model.
The TypeSafe connector recognizes that contract out of the box, maps
``JudgeVerdict.answered`` to one Jev Noul question, and returns the verdict the
middleware expects.

Jev does not generate the verdict's optional free-form reasoning. The connector
uses a deterministic ``P(answered)`` string as feedback when another iteration
is needed.

Environment variables:
    TYPESAFE_API_KEY        — TypeSafe API key for the Jev judge.
    FOUNDRY_PROJECT_ENDPOINT — Microsoft Foundry project endpoint for the answerer.
    FOUNDRY_MODEL            — Foundry model deployment for the answerer.

Authentication:
    Run ``az login`` before running this sample.
"""

JUDGE_CRITERIA = [
    "Explains why the sky is blue",
    "Explains why sunsets are red",
    "Uses clear language suitable for a general audience",
]

_JUDGE_FRAMING_MESSAGES = {
    "Evaluate the agent's work. The user's original request follows:",
    "The agent's latest response was:",
    "Has the original request been fully addressed?",
}


@chat_middleware
async def log_judge_exchange(
    context: ChatContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Log the input evaluated by Jev and its structured judge verdict."""
    request_messages = [
        message
        for message in context.messages
        if message.role == "user" and message.text not in _JUDGE_FRAMING_MESSAGES
    ]
    response_messages = [message for message in context.messages if message.role == "assistant"]

    print("\nJudge evaluation:")
    print("  Criteria:")
    for criterion in JUDGE_CRITERIA:
        print(f"    - {criterion}")
    print("  Original request:")
    for message in request_messages:
        print(f"    {message.text or message.contents}")
    print("  Latest response:")
    for message in response_messages:
        print(f"    {message.text or message.contents}")

    await call_next()

    if isinstance(context.result, ChatResponse):
        print(f"Judge response: {context.result.value}")


async def main() -> None:
    """Loop a real Foundry answerer until the Jev judge accepts its response."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["FOUNDRY_MODEL"]

    async with (
        AzureCliCredential() as credential,
        TypeSafeChatClient(middleware=[log_judge_exchange]) as judge_client,
    ):
        # 1. The primary agent is a normal generative chat client. Jev only
        #    evaluates whether its latest answer meets the request and criteria.
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=endpoint,
                model=model,
                credential=credential,
            ),
            name="answerer",
            instructions=(
                "Answer clearly and revise your answer when evaluator feedback says "
                "the original request is not fully addressed."
            ),
            middleware=[
                AgentLoopMiddleware.with_judge(
                    # 2. TypeSafeChatClient is used here as a judge.
                    judge_client,
                    criteria=JUDGE_CRITERIA,
                    max_iterations=3,
                )
            ],
        )

        response = await agent.run("Explain why the sky is blue.")

    # 3. Non-streaming loop results include all iterations; the last assistant
    #    message is the accepted final answer.
    print(f"Final answer: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (exact answer and iteration count vary by the Foundry model):

Judge evaluation:
  Criteria:
    - Explains why the sky is blue
    - Explains why sunsets are red
    - Uses clear language suitable for a general audience
  Original request:
    Explain why the sky is blue.
  Latest response:
    The sky appears blue because ...
Judge response: answered=False reasoning='Jev P(answered)=0.421'

Judge evaluation:
  Criteria:
    - Explains why the sky is blue
    - Explains why sunsets are red
    - Uses clear language suitable for a general audience
  Original request:
    Explain why the sky is blue.
  Latest response:
    The sky appears blue because ...
Judge response: answered=True reasoning='Jev P(answered)=0.873'

Final answer: The sky appears blue because air molecules scatter shorter blue
wavelengths more strongly than longer wavelengths. At sunset, sunlight travels
through more atmosphere, so much of the blue light is scattered away and the
remaining red and orange light dominates.

TypeSafeChatClient supplies JudgeVerdict directly to AgentLoopMiddleware. If Jev
returns P(answered) <= 0.5, the middleware runs the Foundry agent again with
deterministic probability feedback.
"""
