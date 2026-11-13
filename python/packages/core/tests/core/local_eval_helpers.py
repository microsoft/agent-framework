# Copyright (c) Microsoft. All rights reserved.

"""Helpers for the local evaluation tests."""

from agent_framework import Content, Message
from agent_framework._types import LOOP_INJECTED_MESSAGE_PROPERTY


def two_turn_conversation() -> list[Message]:
    """Return a two-turn conversation whose first turn contains a tool call."""
    return [
        Message("user", ["Weather in NYC?"]),
        Message("assistant", [Content.from_function_call("c1", "get_weather", arguments={"location": "NYC"})]),
        Message("assistant", ["Sunny."]),
        Message("user", ["And tomorrow?"]),
        Message("assistant", ["No idea."]),
    ]


def loop_aggregated_conversation() -> list[Message]:
    """Return a conversation shaped like a loop-aggregated agent run.

    The agent loop injects a ``user``-role nudge between iterations of a single run.  Such a
    message is not a real user turn, so the tool call made in the first iteration still belongs to
    the response side of the split.
    """
    nudge = Message(
        "user",
        ["Continue working on the task."],
        additional_properties={LOOP_INJECTED_MESSAGE_PROPERTY: True},
    )
    return [
        Message("user", ["Weather in NYC?"]),
        Message("assistant", [Content.from_function_call("c1", "get_weather", arguments={"location": "NYC"})]),
        nudge,
        Message("assistant", ["Sunny."]),
    ]
