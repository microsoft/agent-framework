# Copyright (c) Microsoft. All rights reserved.

class TestPrependInstructionsEmpty:
    def test_empty_string_instructions_add_no_message(self) -> None:
        """An unset "" instruction must not inject a contentless system message."""
        from agent_framework import Message, prepend_instructions_to_messages

        messages = [Message(role="user", contents=["hi"])]
        out = prepend_instructions_to_messages(messages, "")
        assert [(m.role, [getattr(c, "text", c) for c in m.contents]) for m in out] == [("user", ["hi"])]

    def test_whitespace_only_instructions_add_no_message(self) -> None:
        from agent_framework import prepend_instructions_to_messages

        assert prepend_instructions_to_messages([], ["", "   "]) == []

    def test_real_instructions_still_prepend_verbatim(self) -> None:
        from agent_framework import prepend_instructions_to_messages

        out = prepend_instructions_to_messages([], ["  real  "])
        assert [(m.role, [getattr(c, "text", c) for c in m.contents]) for m in out] == [("system", ["  real  "])]
