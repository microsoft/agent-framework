# Copyright (c) Microsoft. All rights reserved.

"""Local client for the **complete** server (``app.py`` in this folder).

Demonstrates the two most distinctive flows the complete sample adds on top
of the advanced sample:

1. **Identity-linked Telegram resume.** Pass ``--previous-response-id
   telegram:<chat_id>`` to resume a Telegram chat's history through the
   Responses endpoint — this only works once the user has linked their
   Telegram chat to their Entra account via the
   ``EntraIdentityLinkChannel`` (visit ``/auth/start?channel=telegram&id=...``
   in the browser first).
2. **Multicast via ``response_target``.** Pass ``--telegram-chat-id`` to
   have the host fan out the agent reply to a Telegram chat in addition
   to returning it on the local wire. Drop ``--include-originating`` to
   send only to Telegram and have the local response reduced to a small
   acknowledgement.

Start the server first (in another shell)::

    cd local_identity_link && uv run python app.py

Then::

    python call_server.py "What is the weather in Tokyo?"
    python call_server.py --previous-response-id telegram:8741188429 "What did we discuss?"
    python call_server.py --telegram-chat-id 8741188429 "Heads up, sending to your phone too."
"""

from __future__ import annotations

import argparse

from openai import OpenAI

BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--safety-identifier", default="local-dev")
    parser.add_argument("--previous-response-id", default=None)
    parser.add_argument("--telegram-chat-id", default=None)
    parser.add_argument("--include-originating", action="store_true", default=True)
    parser.add_argument("prompt", nargs="*")
    args = parser.parse_args()

    prompt = " ".join(args.prompt) or "What is the weather in Seattle?"

    extra_body: dict[str, object] = {}
    if args.telegram_chat_id is not None:
        targets: list[str] = []
        if args.include_originating:
            targets.append("originating")
        targets.append(f"telegram:{args.telegram_chat_id}")
        extra_body["response_target"] = targets

    client = OpenAI(base_url=BASE_URL, api_key="not-needed")
    response = client.responses.create(
        model="agent",
        input=prompt,
        safety_identifier=args.safety_identifier,
        previous_response_id=args.previous_response_id,
        extra_body=extra_body or None,
    )
    print(f"User: {prompt}")
    print(f"Agent: {response.output_text}")


if __name__ == "__main__":
    main()
