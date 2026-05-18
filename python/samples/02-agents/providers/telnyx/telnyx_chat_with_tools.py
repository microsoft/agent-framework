# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "telnyx-agent-toolkit>=0.1.0",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/02-agents/providers/telnyx/telnyx_chat_with_tools.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Telnyx Chat Completion with Telecom Tools Example

This sample demonstrates using Telnyx as an OpenAI-compatible inference
provider together with Telnyx telecom tools (SMS, number lookup) via
the telnyx-agent-toolkit package.

The agent can send SMS messages and look up phone number information
using Telnyx's telecom APIs, combining LLM capabilities with real-world
telecom actions.

Environment Variables:
    TELNYX_API_KEY   — Your Telnyx API key (from https://portal.telnyx.com/)
    TELNYX_MODEL     — Model name to use (default: "Kimi-K2.5")
    TELNYX_FROM_NUMBER — Phone number for sending SMS (E.164 format, e.g. "+15551234567")
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
async def lookup_number(
    phone_number: Annotated[str, "Phone number in E.164 format (e.g., +15551234567)"],
) -> str:
    """Look up carrier and line type information for a phone number.

    Uses the Telnyx Number Lookup API to retrieve carrier details,
    line type (mobile, landline, VoIP), and country information.
    """
    import telnyx

    telnyx.api_key = os.getenv("TELNYX_API_KEY")
    try:
        lookup = telnyx.NumberLookup.retrieve(phone_number)
        return str(lookup)
    except Exception as e:
        return f"Lookup failed: {e}"


@tool(approval_mode="never_require")
async def send_sms(
    to_number: Annotated[str, "Destination phone number in E.164 format (e.g., +15551234567)"],
    message: Annotated[str, "SMS message text to send"],
) -> str:
    """Send an SMS message to a phone number.

    Uses the Telnyx Messaging API to send an SMS from the configured
    TELNYX_FROM_NUMBER to the specified destination.
    """
    import telnyx

    telnyx.api_key = os.getenv("TELNYX_API_KEY")
    from_number = os.getenv("TELNYX_FROM_NUMBER")

    if not from_number:
        return "Error: TELNYX_FROM_NUMBER environment variable is not set."

    try:
        sms = telnyx.Message.create(
            from_=from_number,
            to=to_number,
            text=message,
        )
        return f"SMS sent successfully. Message ID: {sms.id}"
    except Exception as e:
        return f"Failed to send SMS: {e}"


async def main() -> None:
    print("=== Telnyx Chat Completion with Telecom Tools Example ===")

    # 1. Configure the OpenAI client to use Telnyx as the backend.
    client = OpenAIChatClient(
        api_key=os.getenv("TELNYX_API_KEY"),
        base_url="https://api.telnyx.com/v2/ai/openai",
        model=os.getenv("TELNYX_MODEL", "Kimi-K2.5"),
    )

    # 2. Create an agent with telecom tools.
    agent = Agent(
        client=client,
        name="TelnyxTelecomAgent",
        instructions=(
            "You are a telecom assistant powered by Telnyx. "
            "You can look up phone number information and send SMS messages. "
            "Always confirm with the user before sending an SMS. "
            "When looking up a number, present the carrier and line type clearly."
        ),
        tools=[lookup_number, send_sms],
    )

    # 3. Example: Look up a phone number.
    query = "Can you look up the number +15551234567 and tell me what carrier it belongs to?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

=== Telnyx Chat Completion with Telecom Tools Example ===
User: Can you look up the number +15551234567 and tell me what carrier it belongs to?
Agent: I looked up the number +15551234567 for you. Here are the details:

- **Carrier**: T-Mobile USA
- **Line Type**: Mobile
- **Country**: United States

Is there anything else you'd like to know about this number, or would you like me to send an SMS to it?
"""
