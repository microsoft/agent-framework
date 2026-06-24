# Copyright (c) Microsoft. All rights reserved.

"""Local Responses-endpoint client for the local_multi_channel sample.

POSTs to the ``/responses`` endpoint using the OpenAI SDK.

The ``responses_hook`` on the server keys per-user history off the OpenAI
``safety_identifier`` field. Pass ``--previous-response-id`` to resume an
existing AgentSession by its isolation key — this works across channels, so
you can resume a Telegram chat by passing its isolation key::

    uv run python call_server.py --previous-response-id telegram:8741188429 "What did we discuss?"

Start the server first (in another shell)::

    uv run python app.py

Then::

    uv run python call_server.py "What is the weather in Tokyo?"
    uv run python call_server.py --previous-response-id telegram:8741188429 "What did we discuss?"
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
