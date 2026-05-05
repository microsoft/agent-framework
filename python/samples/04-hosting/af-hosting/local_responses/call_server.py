# Copyright (c) Microsoft. All rights reserved.

"""Local client for the local_responses sample.

Posts to ``/responses`` using the standard ``openai`` SDK.

Pass ``--previous-response-id <id>`` to continue a conversation by its
``response.id`` (returned in the prior response).

Start the server first (in another shell)::

    uv run python app.py

Then::

    uv run python call_server.py "What is the weather in Tokyo?"
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
        print(f"Resuming response: {previous_response_id}")
    prompt = " ".join(args) or "What is the weather in Tokyo?"
    client = OpenAI(base_url=BASE_URL, api_key="not-needed")
    response = client.responses.create(
        model="agent",
        input=prompt,
        previous_response_id=previous_response_id,
    )
    print(f"User: {prompt}")
    print(f"Agent: {response.output_text}")


if __name__ == "__main__":
    main()
