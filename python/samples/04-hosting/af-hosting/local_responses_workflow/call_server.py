# Copyright (c) Microsoft. All rights reserved.

"""Local client for the local_responses_workflow sample.

Posts to ``/responses`` using the standard ``openai`` SDK.

Start the server first (in another shell)::

    uv run python app.py

Then::

    uv run python call_server.py '{"topic": "electric SUV", "style": "playful", "audience": "young families"}'
"""

from __future__ import annotations

import sys

from openai import OpenAI

BASE_URL = "http://127.0.0.1:8000"
DEFAULT_BRIEF = '{"topic": "electric SUV", "style": "playful", "audience": "young families"}'
FOLLOW_UP = "Make it a little more premium, but still family friendly."


def main() -> None:
    """Send a two-turn workflow conversation to the local server."""
    client = OpenAI(base_url=BASE_URL, api_key="not-needed")
    brief = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BRIEF

    response = client.responses.create(input=brief)
    print(f"User: {brief}")
    print(f"Workflow: {response.output_text}")
    print(f"Response ID: {response.id}")

    follow_up = client.responses.create(
        input=FOLLOW_UP,
        previous_response_id=response.id,
    )
    print()
    print(f"User: {FOLLOW_UP}")
    print(f"Workflow: {follow_up.output_text}")
    print(f"Response ID: {follow_up.id}")


if __name__ == "__main__":
    main()
