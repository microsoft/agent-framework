# Copyright (c) Microsoft. All rights reserved.

"""Local client for the local_responses sample.

Posts to ``/responses`` using the standard ``openai`` SDK.

Pass ``--previous-response-id <id>`` to continue a conversation by its
``response.id`` (returned in the prior response).

Start the server first (in another shell)::

    uv run python app.py

Then::

    uv run python call_server.py

The script sends a follow-up turn ("And what about Amsterdam?") using the
first response's ``response.id`` as ``previous_response_id``.
"""

from __future__ import annotations

from openai import OpenAI

BASE_URL = "http://127.0.0.1:8000"
PROMPT = "What is the weather in Tokyo?"
FOLLOW_UP_PROMPT = "And what about Amsterdam?"


def main() -> None:
    client = OpenAI(base_url=BASE_URL, api_key="not-needed")
    response = client.responses.create(
        input=PROMPT,
    )
    print(f"User: {PROMPT}")
    print(f"Agent: {response.output_text}")
    print(f"Response ID: {response.id}")

    follow_up = client.responses.create(
        input=FOLLOW_UP_PROMPT,
        previous_response_id=response.id,
    )
    print()
    print(f"User: {FOLLOW_UP_PROMPT}")
    print(f"Agent: {follow_up.output_text}")
    print(f"Response ID: {follow_up.id}")


if __name__ == "__main__":
    main()
