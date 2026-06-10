# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for workflow serialization helpers (`resolve_type`).

``resolve_type`` is annotated ``type | None`` and its result flows into
``reconstruct_to_type``, which calls ``issubclass``. A non-class attribute
(function, module member, etc.) would raise ``TypeError`` there, so the
resolver must only ever return actual classes.
"""

from collections import OrderedDict

from agent_framework_durabletask._workflows.serialization import resolve_type


class TestResolveType:
    """Test that resolve_type only returns real classes."""

    def test_resolves_a_real_class(self) -> None:
        assert resolve_type("collections:OrderedDict") is OrderedDict

    def test_returns_none_for_non_class_attribute(self) -> None:
        # json.dumps is a function; if resolve_type returned it, issubclass()
        # inside reconstruct_to_type() would raise TypeError at runtime.
        assert resolve_type("json:dumps") is None

    def test_returns_none_for_unknown_attribute(self) -> None:
        assert resolve_type("json:DoesNotExist") is None

    def test_returns_none_for_malformed_key(self) -> None:
        assert resolve_type("not-a-valid-key") is None
