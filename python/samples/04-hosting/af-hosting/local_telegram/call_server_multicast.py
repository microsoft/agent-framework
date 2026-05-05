# Copyright (c) Microsoft. All rights reserved.

"""Local client demonstrating server-side ``ResponseTarget`` fan-out.

Posts one request to ``/responses`` with
``extra_body={"response_target": ["originating", "telegram:<chat_id>"]}``.
The server invokes the agent once and the host's
``ChannelContext.deliver_response`` resolves the target list against the
configured channels, calling :class:`host.ChannelPush` ``push`` on each
non-originating destination — here, the operator's Telegram chat. The
``"originating"`` pseudo-name keeps the agent reply on this script's wire
too, so the local terminal sees the reply alongside Telegram.

Drop ``--include-originating`` to deliver only to Telegram (the local
response becomes a small acknowledgement string referencing the push
targets).

The ``--previous-response-id`` flag (the AgentSession id) is independent
of ``--telegram-chat-id`` (the push destination). They were conflated in
an earlier iteration; in general one Entra user may have several Telegram
chat ids, and the session id is usually their Entra/responses isolation
key, not the chat id. Pass them both to resume a specific session and
fan-out to a specific chat::

    python call_server_multicast.py \\
        --previous-response-id telegram:8741188429 \\
        --telegram-chat-id 8741188429 \\
        "What did we discuss?"

Start the server first (in another shell)::

    cd server && uv run python advanced_app.py
"""

from __future__ import annotations

import argparse

from openai import OpenAI

BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--telegram-chat-id",
        required=True,
        help="Native Telegram chat id to push the agent reply to.",
    )
    parser.add_argument(
        "--previous-response-id",
        default=None,
        help=(
            "Existing AgentSession id (e.g. 'telegram:8741188429' or "
            "'responses:local-dev'). Defaults to no resume — the server "
            "creates a fresh session keyed by safety_identifier."
        ),
    )
    parser.add_argument(
        "--no-originating",
        action="store_true",
        help="Skip 'originating' in response_target; only Telegram receives the reply.",
    )
    parser.add_argument("prompt", nargs="*", help="Prompt to send to the agent.")
    args = parser.parse_args()

    prompt = " ".join(args.prompt) or "What is the weather in Seattle?"

    response_target: list[str] = []
    if not args.no_originating:
        response_target.append("originating")
    response_target.append(f"telegram:{args.telegram_chat_id}")

    if args.previous_response_id:
        print(f"Resuming AgentSession: {args.previous_response_id}")
    print(f"response_target:       {response_target}")

    client = OpenAI(base_url=BASE_URL, api_key="not-needed")
    response = client.responses.create(
        model="agent",
        input=prompt,
        safety_identifier="local-dev",
        previous_response_id=args.previous_response_id,
        extra_body={"response_target": response_target},
    )
    print(f"User: {prompt}")
    print(f"Agent: {response.output_text}")


if __name__ == "__main__":
    main()
