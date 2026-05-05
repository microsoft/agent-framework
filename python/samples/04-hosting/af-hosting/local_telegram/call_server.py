# Copyright (c) Microsoft. All rights reserved.

"""Local client for the advanced agent — POSTs to the ``/responses`` endpoint
exposed by ``server/advanced_app.py`` using the standard ``openai`` SDK.

The advanced server's ``responses_hook`` keys per-user history off the
OpenAI ``safety_identifier`` field, so we pass ``safety_identifier=`` here.

Pass ``--previous-response-id <id>`` to resume an existing AgentSession by
its isolation key. Because the server uses ``previous_response_id`` directly
as the ``AgentSession`` id, you can resume any session written by any
channel — for example a Telegram chat at
``--previous-response-id telegram:8741188429``.

Start the server first (in another shell)::

    cd server && uv run python advanced_app.py

Then::

    python call_server.py "What is the weather in Tokyo?"
    python call_server.py --previous-response-id telegram:8741188429 "What did we discuss?"
"""

from __future__ import annotations

import sys

from openai import OpenAI

BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    args = sys.argv[1:]
    previous_response_id: str | None = None
    if len(args) >= 2 and args[0] == "--previous-response-id":
        previous_response_id = args[1]
        args = args[2:]
        print(f"Resuming AgentSession: {previous_response_id}")
    prompt = " ".join(args) or "What is the weather in Seattle?"
    client = OpenAI(base_url=BASE_URL, api_key="not-needed")
    response = client.responses.create(
        model="agent",
        input=prompt,
        safety_identifier="local-dev",
        previous_response_id=previous_response_id,
    )
    print(f"User: {prompt}")
    print(f"Agent: {response.output_text}")


if __name__ == "__main__":
    main()
