# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from agent_framework import (
    Agent,
    AgentLoopMiddleware,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    FunctionInvocationLayer,
    JudgeVerdict,
    Message,
)
from agent_framework.exceptions import ChatClientInvalidRequestException
from dotenv import load_dotenv
from typesafe_sdk import Noul, SystemOneResponse

from agent_framework_typesafe import RawTypeSafeChatClient

load_dotenv()

"""
Use Jev as the judge for AgentLoopMiddleware.with_judge.

The middleware asks its judge client for the Pydantic ``JudgeVerdict`` model.
Jev returns typed questions instead, so this adapter maps the verdict's
``answered`` field to one Noul question and constructs JudgeVerdict from the
probability.

Jev does not generate the verdict's free-form ``reasoning`` field. The adapter
uses a deterministic probability string as feedback for the next loop iteration.

Environment variables:
    TYPESAFE_API_KEY — TypeSafe API key.
"""


class JevJudgeClient(RawTypeSafeChatClient):
    """Map the AgentLoopMiddleware judge contract to one Jev Noul."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.answer_probabilities: list[float] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Any:
        """Return JudgeVerdict while using Jev for the answered decision."""
        if stream:
            raise ChatClientInvalidRequestException("The Jev judge does not support streaming.")
        if options.get("response_format") is not JudgeVerdict:
            raise ChatClientInvalidRequestException("The Jev judge expects JudgeVerdict response format.")

        async def evaluate() -> ChatResponse[Any]:
            raw_response = await super(JevJudgeClient, self)._inner_get_response(
                messages=messages,
                stream=False,
                options={
                    "response_format": {
                        "answered": Noul(
                            instructions=("Has the agent fully addressed the original request and all stated criteria?")
                        )
                    }
                },
            )
            if not isinstance(raw_response.value, SystemOneResponse):
                raise RuntimeError("Jev did not return the judge's SystemOneResponse.")

            probability = raw_response.value.nouls["answered"].noul
            self.answer_probabilities.append(probability)
            verdict = JudgeVerdict(
                answered=probability > 0.5,
                reasoning=f"Jev P(answered)={probability:.3f}",
            )
            return ChatResponse(
                messages=[Message(role="assistant", contents=[verdict.model_dump_json()])],
                model=raw_response.model,
                usage_details=raw_response.usage_details,
                value=verdict,
                response_format=JudgeVerdict,
                raw_representation=raw_response.raw_representation,
            )

        return evaluate()


class ScriptedAnswerClient(
    FunctionInvocationLayer[ChatOptions[None]],
    BaseChatClient[ChatOptions[None]],
):
    """Return an incomplete answer first and a complete answer second."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Any:
        """Return the next deterministic candidate answer."""
        if stream:
            raise ChatClientInvalidRequestException("The scripted sample client does not stream.")

        async def respond() -> ChatResponse:
            self.call_count += 1
            if self.call_count == 1:
                text = "The sky is blue because blue light scatters more."
            else:
                text = (
                    "The sky is blue because shorter wavelengths scatter more strongly. "
                    "Sunsets are red because the longer path through the atmosphere scatters "
                    "blue light away before the remaining red and orange light reaches us."
                )
            return ChatResponse(messages=[Message(role="assistant", contents=[text])])

        return respond()


async def main() -> None:
    """Loop a scripted answerer until Jev judges the answer complete."""
    primary_client = ScriptedAnswerClient()

    # 1. Jev receives the original request, latest answer, and rendered criteria as state.
    async with JevJudgeClient() as judge_client:
        loop = AgentLoopMiddleware.with_judge(
            judge_client,
            criteria=[
                "Explains why the sky is blue",
                "Explains why sunsets are red",
            ],
            max_iterations=3,
        )
        agent = Agent(client=primary_client, name="answerer", middleware=[loop])

        # 2. The first candidate is incomplete. Jev returns a low P(answered), the
        #    middleware feeds that verdict back, and the scripted client revises once.
        response = await agent.run("Explain why the sky is blue and sunsets are red.")

    print(f"Agent iterations: {primary_client.call_count}")
    print("Judge probabilities: " + ", ".join(f"{value:.3f}" for value in judge_client.answer_probabilities))
    print(f"Final answer: {response.messages[-1].text}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (probabilities vary):

Agent iterations: 2
Judge probabilities: 0.040, 0.990
Final answer: The sky is blue because shorter wavelengths scatter more strongly.
Sunsets are red because the longer path through the atmosphere scatters blue
light away before the remaining red and orange light reaches us.

The Jev judge can stop or continue the loop. Its feedback is the deterministic
probability string, not generated gap-analysis prose.
"""
