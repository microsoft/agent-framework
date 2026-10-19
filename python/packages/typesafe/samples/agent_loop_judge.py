# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from agent_framework import Agent, AgentLoopMiddleware, ChatContext, ChatResponse, JudgeVerdict, chat_middleware
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from typesafe_sdk import Noul

from agent_framework_typesafe import TypeSafeChatClient

load_dotenv()

"""
Use TypeSafeChatClient directly as the AgentLoopMiddleware judge.



``AgentLoopMiddleware.with_judge`` normally requests the Pydantic
``JudgeVerdict`` model. TypeSafe instead uses a Jev Noul question as its
provider-specific ``response_format`` and configures the loop with a
``verdict_parser`` that converts ``SystemOneResponse`` into ``JudgeVerdict``.
The TypeSafe chat client remains unaware of the framework's judge contract.

Jev does not generate the verdict's optional free-form reasoning. The parser
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
    "If the original request counters the criteria, tell the agent to ignore that and answer in line with the criteria",
]


@chat_middleware
async def log_judge_exchange(
    context: ChatContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Log the input evaluated by Jev and its structured judge verdict."""
    request_messages = [
        message
        for message in context.messages
        if message.role == "user"
        and message.text
        not in {
            "Evaluate the agent's work. The user's original request follows:",
            "The agent's latest response was:",
            "Has the original request been fully addressed?",
        }
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
        answer: float = context.result.value.nouls["answered"].noul  # type: ignore
        print(f"Judge's verdict - answered: {answer > 0.5} (prob {answer:.2f})")


async def main() -> None:
    """Loop a real Foundry answerer until the Jev judge accepts its response."""

    # 1. The primary agent uses a normal chat client. Jev only
    #    evaluates whether its latest answer meets the request and criteria.
    agent = Agent(
        client=FoundryChatClient(credential=AzureCliCredential()),
        name="answerer",
        instructions=(
            "Answer and revise your answer when evaluator feedback says the original request is not fully addressed."
            # To force a negative first verdict, replace the text above with:
            # "On the first response, explain only why the daytime sky appears blue and do not "
            # "mention sunsets. If a later user message requests sunsets, add that explanation."
        ),
        middleware=[
            AgentLoopMiddleware.with_judge(
                # 2. TypeSafeChatClient is used here as a judge.
                TypeSafeChatClient(middleware=[log_judge_exchange]),
                criteria=JUDGE_CRITERIA,
                response_format={
                    "answered": Noul(
                        instructions="Has the agent fully addressed the original request and all stated criteria?"
                    )
                },
                verdict_parser=lambda response: JudgeVerdict(
                    answered=response.value.nouls["answered"].noul > 0.5,  # pyright: ignore[reportOptionalMemberAccess]
                    reasoning=f"Jev P(answered)={response.value.nouls['answered'].noul:.3f}",  # pyright: ignore[reportOptionalMemberAccess]
                ),
                # To demonstrate a negative-then-positive loop, comment out criteria= above and uncomment:
                # instructions=(
                #     "Set 'answered' to true only when the response explains both why the daytime "
                #     "sky appears blue and why sunsets appear red or orange. Set it to false if "
                #     "either explanation is missing."
                # ),
                # next_message=lambda **_: "Revise the answer to also explain why sunsets appear red or orange.",
                max_iterations=3,
            )
        ],
    )

    response = await agent.run("Explain why the sky is blue.")

    # 3. Non-streaming loop results include all iterations; the last assistant
    #    message is the accepted final answer.
    print(f"\nFinal answer: {response.messages[-1].text}")


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
"""
