# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for DurableSharedState and SharedState entity."""

from unittest.mock import Mock

import pytest
from azure.durable_functions import EntityId

from agent_framework_azurefunctions._shared_state import (
    SHARED_STATE_ENTITY_NAME,
    DurableSharedState,
    SharedStateData,
    create_shared_state_entity_function,
)


class TestSharedStateData:
    """Test suite for SharedStateData dataclass."""

    def test_default_initialization(self) -> None:
        """Test default initialization creates empty state."""
        data = SharedStateData()

        assert data.state == {}

    def test_initialization_with_state(self) -> None:
        """Test initialization with provided state."""
        data = SharedStateData(state={"key": "value"})

        assert data.state == {"key": "value"}

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        data = SharedStateData(state={"a": 1, "b": 2})

        result = data.to_dict()

        assert result == {"state": {"a": 1, "b": 2}}

    def test_from_dict_with_none(self) -> None:
        """Test deserialization from None."""
        result = SharedStateData.from_dict(None)

        assert result.state == {}

    def test_from_dict_with_empty_dict(self) -> None:
        """Test deserialization from empty dict."""
        result = SharedStateData.from_dict({})

        assert result.state == {}

    def test_from_dict_with_state(self) -> None:
        """Test deserialization from dict with state."""
        result = SharedStateData.from_dict({"state": {"x": 10, "y": 20}})

        assert result.state == {"x": 10, "y": 20}


class TestDurableSharedState:
    """Test suite for DurableSharedState orchestration wrapper."""

    @pytest.fixture
    def mock_context(self) -> Mock:
        """Create a mock DurableOrchestrationContext."""
        context = Mock()
        context.call_entity = Mock(return_value="mocked_result")
        return context

    @pytest.fixture
    def shared_state(self, mock_context: Mock) -> DurableSharedState:
        """Create a DurableSharedState instance for testing."""
        return DurableSharedState(mock_context, "test-session-123")

    def test_initialization(self, mock_context: Mock) -> None:
        """Test DurableSharedState initialization."""
        state = DurableSharedState(mock_context, "my-session")

        assert state._context == mock_context
        assert state._session_id == "my-session"
        assert state._entity_id.name == SHARED_STATE_ENTITY_NAME
        assert state._entity_id.key == "my-session"

    def test_entity_id_property(self, shared_state: DurableSharedState) -> None:
        """Test entity_id property returns correct EntityId."""
        entity_id = shared_state.entity_id

        assert isinstance(entity_id, EntityId)
        assert entity_id.name == SHARED_STATE_ENTITY_NAME
        assert entity_id.key == "test-session-123"

    def test_get_generator_yields_entity_call(self, shared_state: DurableSharedState, mock_context: Mock) -> None:
        """Test get() yields a call_entity operation."""
        gen = shared_state.get("my_key", default="default_val")

        # The generator should yield the entity call
        next(gen)

        # Verify the call was made with correct parameters
        mock_context.call_entity.assert_called_once_with(
            shared_state._entity_id, "get", {"key": "my_key", "default": "default_val"}
        )

    def test_set_generator_yields_entity_call(self, shared_state: DurableSharedState, mock_context: Mock) -> None:
        """Test set() yields a call_entity operation."""
        gen = shared_state.set("my_key", {"data": "value"})

        # Consume the generator
        next(gen)

        mock_context.call_entity.assert_called_once_with(
            shared_state._entity_id, "set", {"key": "my_key", "value": {"data": "value"}}
        )

    def test_has_generator_yields_entity_call(self, shared_state: DurableSharedState, mock_context: Mock) -> None:
        """Test has() yields a call_entity operation."""
        gen = shared_state.has("check_key")

        next(gen)

        mock_context.call_entity.assert_called_once_with(shared_state._entity_id, "has", {"key": "check_key"})

    def test_delete_generator_yields_entity_call(self, shared_state: DurableSharedState, mock_context: Mock) -> None:
        """Test delete() yields a call_entity operation."""
        gen = shared_state.delete("remove_key")

        next(gen)

        mock_context.call_entity.assert_called_once_with(shared_state._entity_id, "delete", {"key": "remove_key"})

    def test_get_all_generator_yields_entity_call(self, shared_state: DurableSharedState, mock_context: Mock) -> None:
        """Test get_all() yields a call_entity operation."""
        gen = shared_state.get_all()

        next(gen)

        mock_context.call_entity.assert_called_once_with(shared_state._entity_id, "get_all", None)

    def test_update_generator_yields_entity_call(self, shared_state: DurableSharedState, mock_context: Mock) -> None:
        """Test update() yields a call_entity operation."""
        updates = {"key1": "val1", "key2": "val2"}
        gen = shared_state.update(updates)

        next(gen)

        mock_context.call_entity.assert_called_once_with(shared_state._entity_id, "update", {"updates": updates})

    def test_clear_generator_yields_entity_call(self, shared_state: DurableSharedState, mock_context: Mock) -> None:
        """Test clear() yields a call_entity operation."""
        gen = shared_state.clear()

        next(gen)

        mock_context.call_entity.assert_called_once_with(shared_state._entity_id, "clear", None)


class TestSharedStateEntityFunction:
    """Test suite for the SharedState entity function."""

    @pytest.fixture
    def entity_function(self):
        """Create the entity function."""
        return create_shared_state_entity_function()

    @pytest.fixture
    def mock_entity_context(self) -> Mock:
        """Create a mock entity context."""
        context = Mock()
        context.get_state = Mock(return_value={"state": {}})
        context.set_state = Mock()
        context.set_result = Mock()
        return context

    def test_get_operation_returns_value(self, entity_function, mock_entity_context: Mock) -> None:
        """Test get operation returns the stored value."""
        mock_entity_context.get_state.return_value = {"state": {"my_key": "my_value"}}
        mock_entity_context.operation_name = "get"
        mock_entity_context.get_input.return_value = {"key": "my_key", "default": None}

        entity_function(mock_entity_context)

        mock_entity_context.set_result.assert_called_once_with("my_value")

    def test_get_operation_returns_default_when_key_missing(self, entity_function, mock_entity_context: Mock) -> None:
        """Test get operation returns default when key doesn't exist."""
        mock_entity_context.get_state.return_value = {"state": {}}
        mock_entity_context.operation_name = "get"
        mock_entity_context.get_input.return_value = {"key": "missing_key", "default": "fallback"}

        entity_function(mock_entity_context)

        mock_entity_context.set_result.assert_called_once_with("fallback")

    def test_set_operation_stores_value(self, entity_function, mock_entity_context: Mock) -> None:
        """Test set operation stores a value."""
        mock_entity_context.get_state.return_value = {"state": {}}
        mock_entity_context.operation_name = "set"
        mock_entity_context.get_input.return_value = {"key": "new_key", "value": {"data": 123}}

        entity_function(mock_entity_context)

        mock_entity_context.set_state.assert_called_once()
        saved_state = mock_entity_context.set_state.call_args[0][0]
        assert saved_state["state"]["new_key"] == {"data": 123}

    def test_has_operation_returns_true_when_exists(self, entity_function, mock_entity_context: Mock) -> None:
        """Test has operation returns True when key exists."""
        mock_entity_context.get_state.return_value = {"state": {"existing_key": "value"}}
        mock_entity_context.operation_name = "has"
        mock_entity_context.get_input.return_value = {"key": "existing_key"}

        entity_function(mock_entity_context)

        mock_entity_context.set_result.assert_called_once_with(True)

    def test_has_operation_returns_false_when_missing(self, entity_function, mock_entity_context: Mock) -> None:
        """Test has operation returns False when key doesn't exist."""
        mock_entity_context.get_state.return_value = {"state": {}}
        mock_entity_context.operation_name = "has"
        mock_entity_context.get_input.return_value = {"key": "missing_key"}

        entity_function(mock_entity_context)

        mock_entity_context.set_result.assert_called_once_with(False)

    def test_delete_operation_removes_key(self, entity_function, mock_entity_context: Mock) -> None:
        """Test delete operation removes a key and returns True."""
        mock_entity_context.get_state.return_value = {"state": {"to_delete": "value"}}
        mock_entity_context.operation_name = "delete"
        mock_entity_context.get_input.return_value = {"key": "to_delete"}

        entity_function(mock_entity_context)

        mock_entity_context.set_result.assert_called_once_with(True)
        saved_state = mock_entity_context.set_state.call_args[0][0]
        assert "to_delete" not in saved_state["state"]

    def test_delete_operation_returns_false_when_missing(self, entity_function, mock_entity_context: Mock) -> None:
        """Test delete operation returns False when key doesn't exist."""
        mock_entity_context.get_state.return_value = {"state": {}}
        mock_entity_context.operation_name = "delete"
        mock_entity_context.get_input.return_value = {"key": "nonexistent"}

        entity_function(mock_entity_context)

        mock_entity_context.set_result.assert_called_once_with(False)
        mock_entity_context.set_state.assert_not_called()

    def test_get_all_operation_returns_all_state(self, entity_function, mock_entity_context: Mock) -> None:
        """Test get_all operation returns complete state."""
        state_data = {"key1": "val1", "key2": "val2"}
        mock_entity_context.get_state.return_value = {"state": state_data}
        mock_entity_context.operation_name = "get_all"
        mock_entity_context.get_input.return_value = None

        entity_function(mock_entity_context)

        mock_entity_context.set_result.assert_called_once()
        result = mock_entity_context.set_result.call_args[0][0]
        assert result == state_data

    def test_update_operation_merges_updates(self, entity_function, mock_entity_context: Mock) -> None:
        """Test update operation merges multiple key-value pairs."""
        mock_entity_context.get_state.return_value = {"state": {"existing": "old"}}
        mock_entity_context.operation_name = "update"
        mock_entity_context.get_input.return_value = {"updates": {"new1": "val1", "new2": "val2"}}

        entity_function(mock_entity_context)

        saved_state = mock_entity_context.set_state.call_args[0][0]
        assert saved_state["state"]["existing"] == "old"
        assert saved_state["state"]["new1"] == "val1"
        assert saved_state["state"]["new2"] == "val2"

    def test_clear_operation_removes_all_state(self, entity_function, mock_entity_context: Mock) -> None:
        """Test clear operation removes all state."""
        mock_entity_context.get_state.return_value = {"state": {"key1": "val1", "key2": "val2"}}
        mock_entity_context.operation_name = "clear"
        mock_entity_context.get_input.return_value = None

        entity_function(mock_entity_context)

        saved_state = mock_entity_context.set_state.call_args[0][0]
        assert saved_state["state"] == {}

    def test_unknown_operation_is_handled(self, entity_function, mock_entity_context: Mock) -> None:
        """Test unknown operation doesn't crash."""
        mock_entity_context.get_state.return_value = {"state": {}}
        mock_entity_context.operation_name = "unknown_op"
        mock_entity_context.get_input.return_value = {}

        # Should not raise
        entity_function(mock_entity_context)

        # No result should be set for unknown operations
        mock_entity_context.set_result.assert_not_called()
