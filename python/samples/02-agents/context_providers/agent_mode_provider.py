# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent, AgentModeProvider, get_agent_mode, set_agent_mode
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent Mode — Switch an agent's operating mode at runtime with AgentModeProvider

This sample shows how to use the ``AgentModeProvider``, a ``ContextProvider`` that tracks the
agent's current operating "mode" in the session state and exposes tools (``mode_get`` / ``mode_set``)
so the agent can query and switch modes as its work progresses. The mode is folded into the
instructions sent to the model on every turn, so different modes can drive different behavior.

The sample demonstrates two things:
  1. The built-in default modes ("plan" and "execute") that ship with the provider.
  2. How to customize the available modes via ``default_mode`` / ``mode_instructions``. Flip the
     ``USE_CUSTOM_MODES`` constant below to ``True`` to try a simple concise/detailed mode set.

It runs a simple interactive loop. In addition to chatting with the agent, you can switch the
agent's mode yourself using a slash command:
  /mode            — show the current mode
  /mode <name>     — switch to the named mode
  /help            — list the available commands and modes
  /exit            — quit

When you switch modes with /mode, the provider injects a notification on the next turn so the agent
clearly sees the change and adjusts its behavior accordingly.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Microsoft Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""

# Flip to True to run the sample with the custom modes defined below instead of the provider's
# built-in "plan" / "execute" defaults.
USE_CUSTOM_MODES = False


def print_help(available_modes: tuple[str, ...]) -> None:
    """Print the available slash commands and modes."""
    print("Commands:")
    print("  /mode            Show the current mode")
    print(f"  /mode <name>     Switch mode ({' | '.join(available_modes)})")
    print("  /help            Show this help")
    print("  /exit            Quit")


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # <create_mode_provider>
    if USE_CUSTOM_MODES:
        # Customize the set of modes by supplying ``mode_instructions``. Each mode maps a name to a
        # block of instructions describing how the agent should behave while operating in that mode.
        # ``default_mode`` selects the mode new sessions start in (defaults to the first mode when
        # omitted).
        mode_provider = AgentModeProvider(
            default_mode="concise",
            mode_instructions={
                "concise": (
                    "Answer in a single short sentence. Do not elaborate unless the user explicitly "
                    "asks for more detail."
                ),
                "detailed": (
                    "Answer thoroughly. Explain your reasoning, provide examples, and cover relevant edge cases."
                ),
            },
        )
    else:
        # Use the provider's built-in modes: "plan" (interactive planning) and "execute" (autonomous
        # execution). No options are required.
        mode_provider = AgentModeProvider()
    # </create_mode_provider>

    available_modes = mode_provider.available_modes

    # Create the agent and attach the mode provider as a context provider.
    agent = Agent(
        client=client,
        name="ModeAwareAssistant",
        instructions=(
            "You are a helpful assistant. Follow the process and behavior required by your current operating mode."
        ),
        context_providers=[mode_provider],
    )

    session = agent.create_session()

    def current_mode() -> str:
        """Read the active mode from the session, validated against the provider's configured modes."""
        return get_agent_mode(
            session,
            source_id=mode_provider.source_id,
            default_mode=mode_provider.default_mode,
            available_modes=available_modes,
        )

    print("Agent Mode sample. Type a message to chat, or use a slash command.")
    print(f"Available modes: {', '.join(available_modes)}")
    print(f"Current mode: {current_mode()}")
    print_help(available_modes)
    print()

    while True:
        user_input = input("> ").strip()

        # Treat empty input or /exit as a request to quit.
        if not user_input or user_input.lower() == "/exit":
            break

        if user_input.lower() == "/help":
            print_help(available_modes)
            continue

        # Handle the /mode slash command: "/mode" shows the current mode, "/mode <name>" switches.
        if user_input.lower() == "/mode" or user_input.lower().startswith("/mode "):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                print(f"Current mode: {current_mode()}")
                continue

            try:
                # ``set_agent_mode`` records the switch so the provider injects a notification on the
                # next turn. It raises ValueError when the requested mode is not configured.
                new_mode = set_agent_mode(
                    session,
                    parts[1],
                    source_id=mode_provider.source_id,
                    available_modes=available_modes,
                )
                print(f'Switched to "{new_mode}" mode.')
            except ValueError as ex:
                print(ex)

            continue

        # Anything else is a message for the agent. The mode provider injects the current mode (and
        # any pending mode-change notification) into the context for this turn.
        print(await agent.run(user_input, session=session))


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample interaction (abridged; exact text varies by model):

Agent Mode sample. Type a message to chat, or use a slash command.
Available modes: plan, execute
Current mode: plan
Commands:
  /mode            Show the current mode
  /mode <name>     Switch mode (plan | execute)
  /help            Show this help
  /exit            Quit

> Help me plan a blog post about the ocean.
Sure — before we start writing, let's outline the sections and audience. ...
> /mode execute
Switched to "execute" mode.
> Go ahead and write it.
Working through the plan autonomously now. Here's the first draft ...
> /exit
"""
