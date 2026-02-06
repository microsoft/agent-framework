# Copyright (c) Microsoft. All rights reserved.

"""Tests for SerializationMixin functionality."""

import logging
from typing import Any

from agent_framework._serialization import SerializationMixin


class TestSerializationMixin:
    """Test SerializationMixin serialization, deserialization, and dependency injection."""

    def test_basic_serialization(self):
        """Test basic to_dict and from_dict functionality."""

        class TestClass(SerializationMixin):
            def __init__(self, value: str, number: int):
                self.value = value
                self.number = number

        obj = TestClass(value="test", number=42)
        data = obj.to_dict()

        assert data["type"] == "test_class"
        assert data["value"] == "test"
        assert data["number"] == 42

        restored = TestClass.from_dict(data)
        assert restored.value == "test"
        assert restored.number == 42

    def test_injectable_dependency_no_warning(self, caplog):
        """Test that injectable dependencies don't trigger debug logging."""

        class TestClass(SerializationMixin):
            INJECTABLE = {"client"}

            def __init__(self, value: str, client: Any = None):
                self.value = value
                self.client = client

        mock_client = "mock_client_instance"

        with caplog.at_level(logging.DEBUG):
            obj = TestClass.from_dict(
                {"type": "test_class", "value": "test"},
                dependencies={"test_class": {"client": mock_client}},
            )

        assert obj.value == "test"
        assert obj.client == mock_client
        # No debug message should be logged for injectable dependency
        assert not any("is not in INJECTABLE set" in record.message for record in caplog.records)

    def test_non_injectable_dependency_logs_debug(self, caplog):
        """Test that non-injectable dependencies trigger debug logging."""

        class TestClass(SerializationMixin):
            INJECTABLE = {"client"}

            def __init__(self, value: str, other: Any = None):
                self.value = value
                self.other = other

        mock_other = "mock_other_instance"

        with caplog.at_level(logging.DEBUG):
            obj = TestClass.from_dict(
                {"type": "test_class", "value": "test"},
                dependencies={"test_class": {"other": mock_other}},
            )

        assert obj.value == "test"
        assert obj.other == mock_other
        # Debug message should be logged for non-injectable dependency
        debug_messages = [record.message for record in caplog.records if record.levelname == "DEBUG"]
        assert any("is not in INJECTABLE set" in msg for msg in debug_messages)
        assert any("other" in msg for msg in debug_messages)
        assert any("client" in msg for msg in debug_messages)  # Should mention available injectable

    def test_multiple_dependencies_mixed_injectable(self, caplog):
        """Test with both injectable and non-injectable dependencies."""

        class TestClass(SerializationMixin):
            INJECTABLE = {"client", "logger"}

            def __init__(
                self,
                value: str,
                client: Any = None,
                logger: Any = None,
                other: Any = None,
            ):
                self.value = value
                self.client = client
                self.logger = logger
                self.other = other

        mock_client = "mock_client"
        mock_logger = "mock_logger"
        mock_other = "mock_other"

        with caplog.at_level(logging.DEBUG):
            obj = TestClass.from_dict(
                {"type": "test_class", "value": "test"},
                dependencies={
                    "test_class": {
                        "client": mock_client,
                        "logger": mock_logger,
                        "other": mock_other,
                    }
                },
            )

        assert obj.value == "test"
        assert obj.client == mock_client
        assert obj.logger == mock_logger
        assert obj.other == mock_other

        # Only 'other' should trigger debug logging
        debug_messages = [record.message for record in caplog.records if record.levelname == "DEBUG"]
        assert any("other" in msg and "is not in INJECTABLE set" in msg for msg in debug_messages)
        # 'client' and 'logger' should not be mentioned as non-injectable dependencies
        assert not any("Dependency 'client'" in msg and "is not in INJECTABLE set" in msg for msg in debug_messages)
        assert not any("Dependency 'logger'" in msg and "is not in INJECTABLE set" in msg for msg in debug_messages)

    def test_no_injectable_set_defined(self, caplog):
        """Test behavior when INJECTABLE is not defined (empty set default)."""

        class TestClass(SerializationMixin):
            def __init__(self, value: str, client: Any = None):
                self.value = value
                self.client = client

        mock_client = "mock_client"

        with caplog.at_level(logging.DEBUG):
            obj = TestClass.from_dict(
                {"type": "test_class", "value": "test"},
                dependencies={"test_class": {"client": mock_client}},
            )

        assert obj.value == "test"
        assert obj.client == mock_client
        # Should log debug message since INJECTABLE is empty by default
        debug_messages = [record.message for record in caplog.records if record.levelname == "DEBUG"]
        assert any("client" in msg and "is not in INJECTABLE set" in msg for msg in debug_messages)

    def test_default_exclude_serialization(self):
        """Test that DEFAULT_EXCLUDE fields are not included in to_dict()."""

        class TestClass(SerializationMixin):
            DEFAULT_EXCLUDE = {"secret"}

            def __init__(self, value: str, secret: str):
                self.value = value
                self.secret = secret

        obj = TestClass(value="test", secret="hidden")
        data = obj.to_dict()

        assert "value" in data
        assert "secret" not in data
        assert data["value"] == "test"

    def test_roundtrip_with_injectable_dependency(self):
        """Test full roundtrip serialization/deserialization with injectable dependency."""

        class TestClass(SerializationMixin):
            INJECTABLE = {"client"}
            DEFAULT_EXCLUDE = {"client"}

            def __init__(self, value: str, number: int, client: Any = None):
                self.value = value
                self.number = number
                self.client = client

        mock_client = "mock_client"
        obj = TestClass(value="test", number=42, client=mock_client)

        # Serialize
        data = obj.to_dict()
        assert data["value"] == "test"
        assert data["number"] == 42
        assert "client" not in data  # Excluded from serialization

        # Deserialize with dependency injection
        restored = TestClass.from_dict(data, dependencies={"test_class": {"client": mock_client}})
        assert restored.value == "test"
        assert restored.number == 42
        assert restored.client == mock_client

    def test_exclude_none_in_to_dict(self):
        """Test that exclude_none parameter removes None values from to_dict()."""

        class TestClass(SerializationMixin):
            def __init__(self, value: str, optional: str | None = None):
                self.value = value
                self.optional = optional

        obj = TestClass(value="test", optional=None)
        data = obj.to_dict(exclude_none=True)

        assert data["value"] == "test"
        assert "optional" not in data

    def test_to_dict_with_nested_serialization_protocol(self):
        """Test to_dict handles nested SerializationProtocol objects."""

        class InnerClass(SerializationMixin):
            def __init__(self, inner_value: str):
                self.inner_value = inner_value

        class OuterClass(SerializationMixin):
            def __init__(self, outer_value: str, inner: Any = None):
                self.outer_value = outer_value
                self.inner = inner

        inner = InnerClass(inner_value="inner_test")
        outer = OuterClass(outer_value="outer_test", inner=inner)
        data = outer.to_dict()

        assert data["outer_value"] == "outer_test"
        assert data["inner"]["inner_value"] == "inner_test"

    def test_to_dict_with_list_of_serialization_protocol(self):
        """Test to_dict handles lists containing SerializationProtocol objects."""

        class ItemClass(SerializationMixin):
            def __init__(self, name: str):
                self.name = name

        class ContainerClass(SerializationMixin):
            def __init__(self, items: list):
                self.items = items

        items = [ItemClass(name="item1"), ItemClass(name="item2")]
        container = ContainerClass(items=items)
        data = container.to_dict()

        assert len(data["items"]) == 2
        assert data["items"][0]["name"] == "item1"
        assert data["items"][1]["name"] == "item2"

    def test_to_dict_skips_non_serializable_in_list(self, caplog):
        """Test to_dict skips non-serializable items in lists with debug logging."""

        class NonSerializable:
            pass

        class TestClass(SerializationMixin):
            def __init__(self, items: list):
                self.items = items

        obj = TestClass(items=["serializable", NonSerializable()])

        with caplog.at_level(logging.DEBUG):
            data = obj.to_dict()

        # Should only contain the serializable item
        assert len(data["items"]) == 1
        assert data["items"][0] == "serializable"

    def test_to_dict_with_dict_containing_serialization_protocol(self):
        """Test to_dict handles dicts containing SerializationProtocol values."""

        class ItemClass(SerializationMixin):
            def __init__(self, name: str):
                self.name = name

        class ContainerClass(SerializationMixin):
            def __init__(self, items_dict: dict):
                self.items_dict = items_dict

        items = {"a": ItemClass(name="item1"), "b": ItemClass(name="item2")}
        container = ContainerClass(items_dict=items)
        data = container.to_dict()

        assert data["items_dict"]["a"]["name"] == "item1"
        assert data["items_dict"]["b"]["name"] == "item2"

    def test_to_dict_with_datetime_in_dict(self):
        """Test to_dict converts datetime objects in dicts to strings."""
        from datetime import datetime

        class TestClass(SerializationMixin):
            def __init__(self, metadata: dict):
                self.metadata = metadata

        now = datetime(2025, 1, 27, 12, 0, 0)
        obj = TestClass(metadata={"created_at": now})
        data = obj.to_dict()

        assert isinstance(data["metadata"]["created_at"], str)

    def test_to_dict_skips_non_serializable_in_dict(self, caplog):
        """Test to_dict skips non-serializable values in dicts with debug logging."""

        class NonSerializable:
            pass

        class TestClass(SerializationMixin):
            def __init__(self, metadata: dict):
                self.metadata = metadata

        obj = TestClass(metadata={"valid": "value", "invalid": NonSerializable()})

        with caplog.at_level(logging.DEBUG):
            data = obj.to_dict()

        assert data["metadata"]["valid"] == "value"
        assert "invalid" not in data["metadata"]

    def test_to_dict_skips_non_serializable_attributes(self, caplog):
        """Test to_dict skips non-serializable top-level attributes."""

        class TestClass(SerializationMixin):
            def __init__(self, value: str, func: Any = None):
                self.value = value
                self.func = func

        obj = TestClass(value="test", func=lambda x: x)

        with caplog.at_level(logging.DEBUG):
            data = obj.to_dict()

        assert data["value"] == "test"
        assert "func" not in data

    def test_from_dict_without_type_in_data(self):
        """Test from_dict uses class TYPE when no type field in data."""

        class TestClass(SerializationMixin):
            TYPE = "my_custom_type"

            def __init__(self, value: str):
                self.value = value

        # Data without 'type' field - class TYPE should be used for type identifier
        data = {"value": "test"}

        obj = TestClass.from_dict(data)
        assert obj.value == "test"

        # Verify to_dict includes the type
        out = obj.to_dict()
        assert out["type"] == "my_custom_type"

    def test_from_json(self):
        """Test from_json deserializes JSON string."""

        class TestClass(SerializationMixin):
            def __init__(self, value: str):
                self.value = value

        json_str = '{"type": "test_class", "value": "test_value"}'
        obj = TestClass.from_json(json_str)

        assert obj.value == "test_value"

    def test_get_type_identifier_with_instance_type(self):
        """Test _get_type_identifier uses instance 'type' attribute."""

        class TestClass(SerializationMixin):
            def __init__(self, value: str):
                self.value = value
                self.type = "custom_type"

        obj = TestClass(value="test")
        data = obj.to_dict()

        assert data["type"] == "custom_type"

    def test_get_type_identifier_with_class_TYPE(self):
        """Test _get_type_identifier uses class TYPE constant."""

        class TestClass(SerializationMixin):
            TYPE = "class_level_type"

            def __init__(self, value: str):
                self.value = value

        obj = TestClass(value="test")
        data = obj.to_dict()

        assert data["type"] == "class_level_type"

    def test_instance_specific_dependency_injection(self):
        """Test instance-specific dependency injection with field:name format."""

        class TestClass(SerializationMixin):
            INJECTABLE = {"config"}

            def __init__(self, name: str, config: Any = None):
                self.name = name
                self.config = config

        dependencies = {
            "test_class": {
                "name:special_instance": {"config": "special_config"},
            }
        }

        # This should match the instance-specific dependency
        obj = TestClass.from_dict({"type": "test_class", "name": "special_instance"}, dependencies=dependencies)

        assert obj.name == "special_instance"
        assert obj.config == "special_config"

    def test_dependency_dict_merging(self):
        """Test that dict dependencies are merged with existing dict kwargs."""

        class TestClass(SerializationMixin):
            INJECTABLE = {"options"}

            def __init__(self, value: str, options: dict | None = None):
                self.value = value
                self.options = options or {}

        # Existing options in data
        data = {"type": "test_class", "value": "test", "options": {"existing": "value"}}
        # Additional options from dependencies
        dependencies = {"test_class": {"options": {"injected": "option"}}}

        obj = TestClass.from_dict(data, dependencies=dependencies)

        assert obj.options["existing"] == "value"
        assert obj.options["injected"] == "option"
