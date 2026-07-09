# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, AgentLoopMiddleware
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent Loop Middleware: ChatClient judge

This sample demonstrates ``AgentLoopMiddleware.with_judge(...)``: a second chat client decides (via a
``JudgeVerdict`` structured output) whether the original request was answered, and the loop continues
while the answer is "no". The judge's ``reasoning`` is fed back to the agent as the next iteration's
input, so the agent knows what is missing. The loop also passes a list of ``criteria``, which are
injected as an extra instruction for the agent and rendered into the judge's instructions.

The loop is run with streaming, so the judge's feedback between iterations shows up as a ``user``
update; the stream is printed as ``<role>: <content>`` lines.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""


async def judge_loop(client: FoundryChatClient, judge_client: FoundryChatClient) -> None:
    """A second chat client judges whether the request was answered."""
    print("\n=== ChatClient judge (loop until the request is answered) ===")

    # 1. Provide a ``judge_client``. The middleware asks it (via a ``JudgeVerdict`` structured
    #    output) whether the original request has been fully addressed and continues while the
    #    answer is "no". The judge's ``reasoning`` is fed back to the agent as the next iteration's
    #    input, so the agent knows what is missing. Judge loops default to a small ``max_iterations``
    #    cap because each pass costs an extra model call.
    #
    #    ``criteria`` is a list of requirements the response must satisfy. The loop (a) injects them
    #    as an extra instruction for the agent before it runs and (b) renders them into the judge's
    #    instructions (the default judge prompt includes a ``{{criteria}}`` placeholder). Supply your
    #    own ``instructions`` string with ``{{criteria}}`` to control the wording, or omit ``criteria``
    #    entirely and pass a plain ``instructions`` string.
    loop = AgentLoopMiddleware.with_judge(
        judge_client,
        criteria=[
            "Mentions the moon",
            "Includes at least one good joke",
            "Is written as a single piece of fluent prose",
        ],
        max_iterations=4,
    )

    agent = Agent(
        client=client,
        name="answerer",
        instructions="You are a helpful assistant. Answer the user's question thoroughly.",
        middleware=[loop],
    )

    # 2. Run with streaming; the judge's feedback appears as a ``user`` update between iterations
    #    until the judge is satisfied (or the iteration cap is reached). Each contiguous ``user``
    #    block marks the boundary into the next iteration, so we count loop iterations by those
    #    boundaries (robust to function calling, where one iteration may issue several model calls).
    iterations = 1
    in_user_block = False
    assistant_open = False
    async for update in agent.run("Explain why the sky is blue and sunsets are red.", stream=True):
        if update.role == "user":
            if not in_user_block:
                iterations += 1
                in_user_block = True
            assistant_open = False
            print(f"\nuser: {update.text}", flush=True)
            continue
        in_user_block = False
        if update.text:
            if not assistant_open:
                print("\nassistant: ", end="", flush=True)
                assistant_open = True
            print(update.text, end="", flush=True)
    print(f"\n\nCompleted in {iterations} iteration(s).")


async def main() -> None:
    # A single credential is reused; the judge uses its own client instance.
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(credential=credential)
        judge_client = FoundryChatClient(credential=credential)
        await judge_loop(client, judge_client)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (abridged; exact text varies by model):

=== ChatClient judge (loop until the request is answered) ===
assistant: The sky is blue because shorter (blue) wavelengths scatter more (Rayleigh scattering).
user: An evaluator reviewed your previous response and judged that it does not yet fully
address the original request.

Evaluator feedback: The response does not mention the moon.

Revise and continue so the original request is fully addressed.
assistant: The sky is blue because shorter (blue) wavelengths scatter more. At sunset, light travels
through more atmosphere, scattering away blue and leaving red/orange hues. The moon follows the
sky's colors because the same scattering applies to the light reaching it.

Completed in 2 iteration(s).
"""
