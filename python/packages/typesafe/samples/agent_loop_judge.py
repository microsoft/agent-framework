# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os

from agent_framework import Agent, AgentLoopMiddleware
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


async def main() -> None:
    """Loop a real Foundry answerer until the Jev judge accepts its response."""
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["FOUNDRY_MODEL"]

    async with AzureCliCredential() as credential, TypeSafeChatClient() as judge_client:
        # 1. TypeSafeChatClient is passed directly—no judge-specific wrapper.
        loop = AgentLoopMiddleware.with_judge(
            judge_client,
            criteria=[
                "Explains why the sky is blue",
                "Explains why sunsets are red",
                "Uses clear language suitable for a general audience",
            ],
            max_iterations=3,
        )

        # 2. The primary agent remains a normal generative chat client. Jev only
        #    evaluates whether its latest answer meets the request and criteria.
        answer_client = FoundryChatClient(
            project_endpoint=endpoint,
            model=model,
            credential=credential,
        )
        agent = Agent(
            client=answer_client,
            name="answerer",
            instructions=(
                "Answer clearly and revise your answer when evaluator feedback says "
                "the original request is not fully addressed."
            ),
            middleware=[loop],
        )

        response = await agent.run("Explain why the sky is blue and sunsets are red.")

    # 3. Non-streaming loop results include all iterations; the last assistant
    #    message is the accepted final answer.
    print(f"Final answer: {response.messages[-1].text}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (exact answer and iteration count vary by the Foundry model):

Final answer: The sky appears blue because air molecules scatter shorter blue
wavelengths more strongly than longer wavelengths. At sunset, sunlight travels
through more atmosphere, so much of the blue light is scattered away and the
remaining red and orange light dominates.

TypeSafeChatClient supplies JudgeVerdict directly to AgentLoopMiddleware. If Jev
returns P(answered) <= 0.5, the middleware runs the Foundry agent again with
deterministic probability feedback.
"""
