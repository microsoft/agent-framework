# Copyright (c) Microsoft. All rights reserved.

"""Local client for the local_responses_harness sample.

Posts to ``/responses`` using the standard ``openai`` SDK.

Start the server first (in another shell)::

    uv run python app.py

Then::

    uv run python call_server.py

The script sends two follow-up turns, each continuing from the previous turn's
``response.id`` as ``previous_response_id``. The third turn asks about
information from the *first* turn only, so it also exercises session continuity
across a rotating response id chain, not just a single hop. Session state is
managed by the harness agent behind the hosted route.
"""

from __future__ import annotations

from openai import OpenAI

BASE_URL = "http://127.0.0.1:8000"
PROMPT = "What is the weather in Tokyo?"
FOLLOW_UP_PROMPT = "And what about Amsterdam?"
THIRD_PROMPT = "Which of the two cities we just discussed is warmer?"


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

    third = client.responses.create(
        input=THIRD_PROMPT,
        previous_response_id=follow_up.id,
    )
    print()
    print(f"User: {THIRD_PROMPT}")
    print(f"Agent: {third.output_text}")
    print(f"Response ID: {third.id}")


if __name__ == "__main__":
    main()
