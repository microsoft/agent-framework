# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Message,
    annotate_message_groups,
    apply_compaction,
    included_messages,
)

"""This sample demonstrates authoring a custom compaction strategy.

The custom strategy keeps system messages and the most recent user turn while
excluding older non-system groups.
"""

EXCLUDED_KEY = "_excluded"
GROUP_ANNOTATION_KEY = "_group"


class KeepLastUserTurnStrategy:
    async def __call__(self, messages: list[Message]) -> bool:
        group_ids = annotate_message_groups(messages)
        group_kinds: dict[str, str] = {}
        for message in messages:
            group_annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
            group_id = group_annotation.get("id") if isinstance(group_annotation, dict) else None
            kind = group_annotation.get("kind") if isinstance(group_annotation, dict) else None
            if (
                isinstance(group_id, str)
                and isinstance(kind, str)
                and group_id not in group_kinds
            ):
                group_kinds[group_id] = kind
        user_group_ids = [
            group_id for group_id in group_ids if group_kinds.get(group_id) == "user"
        ]
        if not user_group_ids:
            return False
        keep_user_group_id = user_group_ids[-1]

        changed = False
        for message in messages:
            group_annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
            group_id = group_annotation.get("id") if isinstance(group_annotation, dict) else None
            if message.role == "system":
                continue
            if group_id == keep_user_group_id:
                continue
            if message.additional_properties.get(EXCLUDED_KEY) is not True:
                changed = True
            message.additional_properties[EXCLUDED_KEY] = True
        return changed


def _messages() -> list[Message]:
    return [
        Message(role="system", text="You are concise."),
        Message(role="user", text="first request"),
        Message(role="assistant", text="first response"),
        Message(role="user", text="second request"),
        Message(role="assistant", text="second response"),
    ]


async def main() -> None:
    # 1. Build a short conversation.
    messages = _messages()
    print(f"Number of messages before compaction: {len(messages)}")
    # 2. Apply custom strategy.
    await apply_compaction(messages, strategy=KeepLastUserTurnStrategy())
    # 3. Print projected messages.
    projected = included_messages(messages)
    print(f"Number of messages after compaction: {len(projected)}")
    for msg in projected:
        print(f"[{msg.role}] {msg.text}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Number of messages before compaction: 5
Number of messages after compaction: 2
[system] You are concise.
[user] second request
"""
