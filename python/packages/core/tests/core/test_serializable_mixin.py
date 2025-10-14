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
