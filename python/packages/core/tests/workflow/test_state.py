# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the State class superstep caching behavior."""

import pytest

from agent_framework._workflows._state import State


class TestStateBasicOperations:
    """Tests for basic State get/set/has/delete operations."""

    def test_set_and_get(self) -> None:
        state = State()
        state.set("key", "value")
        assert state.get("key") == "value"

    def test_get_with_default(self) -> None:
        state = State()
        assert state.get("missing") is None
        assert state.get("missing", "default") == "default"

    def test_has_returns_true_for_existing_key(self) -> None:
        state = State()
        state.set("key", "value")
        assert state.has("key") is True

    def test_has_returns_false_for_missing_key(self) -> None:
        state = State()
        assert state.has("missing") is False

    def test_delete_existing_key(self) -> None:
        state = State()
        state.set("key", "value")
        state.commit()
        state.delete("key")
        state.commit()
        assert state.has("key") is False
        assert state.get("key") is None

    def test_delete_missing_key_raises(self) -> None:
        state = State()
        with pytest.raises(KeyError, match="Key 'missing' not found"):
            state.delete("missing")

    def test_clear(self) -> None:
        state = State()
        state.set("key1", "value1")
        state.commit()
        state.set("key2", "value2")
        state.clear()
        assert state.get("key1") is None
        assert state.get("key2") is None


class TestSuperstepCaching:
    """Tests for superstep caching semantics - pending vs committed state."""

    def test_set_writes_to_pending_not_committed(self) -> None:
        state = State()
        state.set("key", "value")

        # Value is in pending
        assert "key" in state._pending  # pyright: ignore[reportPrivateUsage]
        # Value is NOT in committed
        assert "key" not in state._committed  # pyright: ignore[reportPrivateUsage]
        # But get() still returns it
        assert state.get("key") == "value"

    def test_commit_moves_pending_to_committed(self) -> None:
        state = State()
        state.set("key", "value")

        # Before commit: in pending, not committed
        assert "key" in state._pending  # pyright: ignore[reportPrivateUsage]
        assert "key" not in state._committed  # pyright: ignore[reportPrivateUsage]

        state.commit()

        # After commit: in committed, pending cleared
        assert "key" not in state._pending  # pyright: ignore[reportPrivateUsage]
        assert "key" in state._committed  # pyright: ignore[reportPrivateUsage]
        assert state.get("key") == "value"

    def test_discard_clears_pending_without_committing(self) -> None:
        state = State()
        state.set("existing", "original")
        state.commit()

        # Make a pending change
        state.set("existing", "modified")
        state.set("new_key", "new_value")

        # Discard pending changes
        state.discard()

        # Original value is preserved, new key never committed
        assert state.get("existing") == "original"
        assert state.get("new_key") is None

    def test_pending_overrides_committed_on_get(self) -> None:
        state = State()
        state.set("key", "committed_value")
        state.commit()

        state.set("key", "pending_value")

        # get() returns pending value, not committed
        assert state.get("key") == "pending_value"
        # But committed still has old value
        assert state._committed["key"] == "committed_value"  # pyright: ignore[reportPrivateUsage]

    def test_multiple_sets_before_commit(self) -> None:
        state = State()
        state.set("key", "value1")
        state.set("key", "value2")
        state.set("key", "value3")

        # Only final value is in pending
        assert state.get("key") == "value3"

        state.commit()
        assert state.get("key") == "value3"


class TestDeleteWithSuperstepCaching:
    """Tests for delete behavior with superstep caching."""

    def test_delete_pending_only_key(self) -> None:
        state = State()
        state.set("key", "value")
        # Key only in pending, not committed
        assert "key" in state._pending  # pyright: ignore[reportPrivateUsage]
        assert "key" not in state._committed  # pyright: ignore[reportPrivateUsage]

        state.delete("key")

        # Should be removed from pending
        assert "key" not in state._pending  # pyright: ignore[reportPrivateUsage]
        assert state.get("key") is None
        assert state.has("key") is False

    def test_delete_committed_key_marks_for_deletion(self) -> None:
        state = State()
        state.set("key", "value")
        state.commit()

        state.delete("key")

        # Key should be marked for deletion in pending (sentinel)
        assert "key" in state._pending  # pyright: ignore[reportPrivateUsage]
        # get() should return default (not the sentinel!)
        assert state.get("key") is None
        assert state.get("key", "default") == "default"
        # has() should return False
        assert state.has("key") is False
        # But committed still has it until commit()
        assert "key" in state._committed  # pyright: ignore[reportPrivateUsage]

    def test_delete_committed_key_removed_on_commit(self) -> None:
        state = State()
        state.set("key", "value")
        state.commit()

        state.delete("key")
        state.commit()

        # Now it should be gone from committed too
        assert "key" not in state._committed  # pyright: ignore[reportPrivateUsage]
        assert "key" not in state._pending  # pyright: ignore[reportPrivateUsage]

    def test_delete_key_in_both_pending_and_committed(self) -> None:
        """Test delete when key exists in both pending (modified) and committed."""
        state = State()
        state.set("key", "original")
        state.commit()

        # Modify the key (now in both pending and committed)
        state.set("key", "modified")
        assert state._pending["key"] == "modified"  # pyright: ignore[reportPrivateUsage]
        assert state._committed["key"] == "original"  # pyright: ignore[reportPrivateUsage]

        # Delete should mark for deletion from committed
        state.delete("key")

        # Should be marked for deletion
        assert state.get("key") is None
        assert state.has("key") is False

        # After commit, key should be fully removed
        state.commit()
        assert "key" not in state._committed  # pyright: ignore[reportPrivateUsage]
        assert "key" not in state._pending  # pyright: ignore[reportPrivateUsage]

    def test_discard_after_delete_restores_committed_value(self) -> None:
        state = State()
        state.set("key", "value")
        state.commit()

        state.delete("key")
        # Key appears deleted
        assert state.has("key") is False

        state.discard()
        # After discard, committed value is restored
        assert state.has("key") is True
        assert state.get("key") == "value"


class TestFailureScenarios:
    """Tests simulating failure scenarios - pending changes should not leak to committed."""

    def test_failure_before_commit_preserves_committed_state(self) -> None:
        """Simulate executor failure - pending changes should not affect committed state."""
        state = State()
        state.set("key1", "original1")
        state.set("key2", "original2")
        state.commit()

        # Superstep starts - make some changes
        state.set("key1", "modified1")
        state.set("key3", "new_value")
        state.delete("key2")

        # Simulate failure - we call discard() instead of commit()
        state.discard()

        # All original values should be intact
        assert state.get("key1") == "original1"
        assert state.get("key2") == "original2"
        assert state.get("key3") is None

    def test_no_partial_commits(self) -> None:
        """Ensure commit is atomic - either all changes apply or none."""
        state = State()
        state.set("key1", "value1")
        state.set("key2", "value2")
        state.set("key3", "value3")

        # Before commit - nothing in committed
        assert len(state._committed) == 0  # pyright: ignore[reportPrivateUsage]

        state.commit()

        # After commit - all three values committed together
        assert state._committed == {"key1": "value1", "key2": "value2", "key3": "value3"}  # pyright: ignore[reportPrivateUsage]

    def test_repeated_supersteps_are_isolated(self) -> None:
        """Test that each superstep's changes are isolated until committed."""
        state = State()

        # Superstep 1
        state.set("counter", 1)
        state.commit()
        assert state.get("counter") == 1

        # Superstep 2
        state.set("counter", 2)
        state.set("temp", "should_be_discarded")
        state.discard()  # Simulate failure
        assert state.get("counter") == 1  # Reverted to superstep 1 value
        assert state.get("temp") is None

        # Superstep 3
        state.set("counter", 3)
        state.commit()
        assert state.get("counter") == 3


class TestExportImport:
    """Tests for state serialization (export/import)."""

    def test_export_returns_committed_only(self) -> None:
        state = State()
        state.set("committed_key", "committed_value")
        state.commit()
        state.set("pending_key", "pending_value")

        exported = state.export_state()

        # Only committed state is exported
        assert exported == {"committed_key": "committed_value"}
        assert "pending_key" not in exported

    def test_import_merges_into_committed(self) -> None:
        state = State()
        state.set("existing", "original")
        state.commit()

        state.import_state({"imported": "value", "existing": "overwritten"})

        assert state.get("imported") == "value"
        assert state.get("existing") == "overwritten"

    def test_import_does_not_affect_pending(self) -> None:
        state = State()
        state.set("pending_key", "pending_value")

        state.import_state({"imported": "value"})

        # Pending is still there
        assert state.get("pending_key") == "pending_value"
        assert "pending_key" in state._pending  # pyright: ignore[reportPrivateUsage]


class TestStateIsolation:
    """Tests for isolation between State instances across export/import.

    Regression tests for https://github.com/microsoft/agent-framework/issues/7683
    — checkpoint state must be isolated from live workflow state across
    restoration and storage boundaries, so a resumed workflow mutating its
    own state cannot corrupt the snapshot it was restored from.
    """

    def test_export_isolates_mutable_list_value(self) -> None:
        """Mutating a list value on the source State must not mutate the exported snapshot."""
        source = State()
        source.set("history", ["step-1"])
        source.commit()

        snapshot = source.export_state()

        # Read, mutate in place, write back on the live state.
        history = source.get("history")
        assert history is not None
        history.append("step-2")
        source.set("history", history)
        source.commit()

        # The snapshot taken before the mutation must be unchanged.
        assert snapshot == {"history": ["step-1"]}

    def test_export_isolates_mutable_dict_value(self) -> None:
        """Mutating a dict value on the source State must not mutate the exported snapshot."""
        source = State()
        source.set("counters", {"a": 1})
        source.commit()

        snapshot = source.export_state()

        counters = source.get("counters")
        assert counters is not None
        counters["b"] = 2
        source.set("counters", counters)
        source.commit()

        assert snapshot == {"counters": {"a": 1}}

    def test_import_does_not_alias_caller_state(self) -> None:
        """Mutating the caller's dict after import_state must not affect committed state."""
        state = State()
        incoming = {"history": ["step-1"]}
        state.import_state(incoming)

        # Caller mutates their dict in place after import.
        incoming["history"].append("step-2")
        incoming["extra"] = "leaked"

        # Committed state must be unaffected.
        assert state.get("history") == ["step-1"]
        assert state.has("extra") is False

    def test_roundtrip_restoration_isolates_checkpoint(self) -> None:
        """The full export → import round-trip must keep a checkpoint stable under in-place mutation.

        Mirrors the checkpoint build / restore path used by RunnerContext.build_checkpoint
        and Runner.restore_checkpoint, where the workflow does
            history = restored.get("history")
            history.append("...")
            restored.set("history", history)
        after being resumed.
        """
        source = State()
        source.set("history", ["step-1"])
        source.commit()
        checkpoint_state = source.export_state()

        restored = State()
        restored.import_state(checkpoint_state)

        history = restored.get("history")
        assert history is not None
        history.append("step-2")
        restored.set("history", history)
        restored.commit()

        # Checkpoint snapshot must remain at the original value.
        assert checkpoint_state == {"history": ["step-1"]}

    def test_export_returns_independent_dict(self) -> None:
        """Mutating the returned dict itself must not affect the source State."""
        source = State()
        source.set("a", 1)
        source.commit()

        snapshot = source.export_state()
        snapshot["b"] = 2
        snapshot.pop("a")

        assert source.get("a") == 1
        assert source.has("b") is False
