# Copyright (c) Microsoft. All rights reserved.

import json
import re
from collections.abc import Mapping, MutableMapping
from typing import Any, ClassVar, Protocol, TypeVar, runtime_checkable

from ._logging import get_logger

logger = get_logger()

TClass = TypeVar("TClass", bound="SerializationMixin")
TProtocol = TypeVar("TProtocol", bound="SerializationProtocol")

# Regex pattern for converting CamelCase to snake_case
_CAMEL_TO_SNAKE_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")


@runtime_checkable
class SerializationProtocol(Protocol):
    """Protocol for objects that support serialization and deserialization.

    This protocol defines the interface that classes must implement to be compatible
    with the agent framework's serialization system. Any class implementing both
    ``to_dict()`` and ``from_dict()`` methods will automatically satisfy this protocol
    and can be used seamlessly with other serializable components.

    The protocol enables type safety and duck typing for serializable objects,
    ensuring consistent behavior across the framework.

    Examples:
        The framework's ``ChatMessage`` class demonstrates the protocol in action:

        .. code-block:: python

            from agent_framework import ChatMessage
            from agent_framework._serialization import SerializationProtocol


            # ChatMessage implements SerializationProtocol via SerializationMixin
            user_msg = ChatMessage(role="user", text="What's the weather like today?")

            # Serialize to dictionary - automatic type identification and nested serialization
            msg_dict = user_msg.to_dict()
            # Result: {
            #     "type": "chat_message",
            #     "role": {"type": "role", "value": "user"},
            #     "contents": [{"type": "text_content", "text": "What's the weather like today?"}],
            #     "message_id": "...",
            #     "additional_properties": {}
            # }

            # Deserialize back to ChatMessage instance - automatic type reconstruction
            restored_msg = ChatMessage.from_dict(msg_dict)
            print(restored_msg.text)  # "What's the weather like today?"
            print(restored_msg.role.value)  # "user"

            # Verify protocol compliance (useful for type checking and validation)
            assert isinstance(user_msg, SerializationProtocol)
            assert isinstance(restored_msg, SerializationProtocol)

        The protocol is also implemented by simpler classes like ``UsageDetails``:

        .. code-block:: python

            from agent_framework import UsageDetails

            # Create usage tracking instance
            usage = UsageDetails(input_token_count=150, output_token_count=75, total_token_count=225)

            # Seamless serialization with type preservation
            usage_dict = usage.to_dict()
            restored_usage = UsageDetails.from_dict(usage_dict)

            # Both satisfy the SerializationProtocol
            assert isinstance(usage, SerializationProtocol)
            assert restored_usage.total_token_count == 225

        The protocol ensures consistent serialization behavior across all framework components,
        enabling reliable data persistence, API communication, and object reconstruction
        throughout the agent framework ecosystem.
    """

    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        """Convert the instance to a dictionary.

        Keyword Args:
            kwargs: Additional keyword arguments for serialization.

        Returns:
            Dictionary representation of the instance.
        """
        ...

    @classmethod
    def from_dict(cls: type[TProtocol], value: MutableMapping[str, Any], /, **kwargs: Any) -> TProtocol:
        """Create an instance from a dictionary.

        Args:
            value: Dictionary containing the instance data (positional-only).

        Keyword Args:
            kwargs: Additional keyword arguments for deserialization.

        Returns:
            New instance of the class.
        """
        ...


def is_serializable(value: Any) -> bool:
    """Check if a value is JSON serializable.

    This function tests whether a value can be directly serialized to JSON
    without custom encoding. It checks for basic Python types that have
    direct JSON equivalents.

    Args:
        value: The value to check for JSON serializability.

    Returns:
        True if the value is one of the basic JSON-serializable types
        (str, int, float, bool, None, list, dict), False otherwise.

    Note:
        This function only checks for direct JSON compatibility. Complex objects
        that implement ``SerializationProtocol`` require conversion via ``to_dict()``
        before JSON serialization.
    """
    return isinstance(value, (str, int, float, bool, type(None), list, dict))


class SerializationMixin:
    """Mixin class providing comprehensive serialization and deserialization capabilities.

    .. note::
        SerializationMixin is in active development. The API may change in future versions
        as we continue to improve and extend its functionality.

    This mixin enables classes to automatically handle complex serialization scenarios
    including nested objects, dependency injection, and type conversion. It provides
    robust support for converting objects to/from dictionaries and JSON strings while
    maintaining object relationships and handling external dependencies.

    **Key Features:**

    - Automatic serialization of nested SerializationProtocol objects
    - Support for lists and dictionaries containing serializable objects
    - Dependency injection system for non-serializable external dependencies
    - Flexible exclusion of fields from serialization
    - Type-safe deserialization with automatic type conversion

    **Constructor Pattern for Nested Objects:**

    Classes using this mixin should handle ``MutableMapping`` inputs in their ``__init__`` method
    for any parameters that expect ``SerializationMixin`` or ``SerializationProtocol`` instances.
    This enables automatic conversion of dictionaries to proper object instances during deserialization.

    **Dependency Injection System:**

    The mixin supports injecting external dependencies (like database connections, API clients,
    or configuration objects) that shouldn't be serialized but are needed at runtime.
    Fields marked in ``INJECTABLE`` are excluded during serialization and can be provided
    during deserialization via the ``dependencies`` parameter.

    Examples:
        **Nested object serialization with agent thread management:**

        .. code-block:: python

            from agent_framework import ChatMessage
            from agent_framework._threads import AgentThreadState, ChatMessageStoreState


            # ChatMessageStoreState handles nested ChatMessage serialization
            store_state = ChatMessageStoreState(
                messages=[
                    ChatMessage(role="user", text="Hello agent"),
                    ChatMessage(role="assistant", text="Hi! How can I help?"),
                ]
            )

            # Nested serialization: messages are automatically converted to dicts
            store_dict = store_state.to_dict()
            # Result: {
            #     "type": "chat_message_store_state",
            #     "messages": [
            #         {"type": "chat_message", "role": {...}, "contents": [...]},
            #         {"type": "chat_message", "role": {...}, "contents": [...]}
            #     ]
            # }

            # AgentThreadState contains nested ChatMessageStoreState
            thread_state = AgentThreadState(chat_message_store_state=store_state)

            # Deep serialization: nested SerializationMixin objects are handled automatically
            thread_dict = thread_state.to_dict()
            # The chat_message_store_state and its nested messages are all serialized

            # Reconstruction from nested dictionaries with automatic type conversion
            # The __init__ method handles MutableMapping -> object conversion:
            reconstructed = AgentThreadState.from_dict({
                "chat_message_store_state": {"messages": [{"role": "user", "text": "Hello again"}]}
            })
            # chat_message_store_state becomes ChatMessageStoreState instance automatically

        **Framework tools with exclusion patterns:**

        .. code-block:: python

            from agent_framework._tools import BaseTool


            class WeatherTool(BaseTool):
                \"\"\"Example tool that extends BaseTool with additional properties exclusion.\"\"\"

                # Inherits DEFAULT_EXCLUDE = {"additional_properties"} from BaseTool

                def __init__(self, name: str, api_key: str, **kwargs):
                    super().__init__(name=name, description="Get weather information", **kwargs)
                    self.api_key = api_key  # Will be serialized

                    # Additional properties are excluded from serialization
                    self.additional_properties = {"version": "1.0", "internal_config": {...}}


            weather_tool = WeatherTool(name="get_weather", api_key="secret-key")

            # Serialization excludes additional_properties but includes other fields
            tool_dict = weather_tool.to_dict()
            # Result: {
            #     "type": "weather_tool",
            #     "name": "get_weather",
            #     "description": "Get weather information",
            #     "api_key": "secret-key"
            #     # additional_properties excluded due to DEFAULT_EXCLUDE
            # }

        **Agent framework with injectable dependencies:**

        .. code-block:: python

            from agent_framework import BaseAgent


            class CustomAgent(BaseAgent):
                \"\"\"Custom agent extending BaseAgent with additional functionality.\"\"\"

                # Inherits DEFAULT_EXCLUDE = {"additional_properties"} from BaseAgent

                def __init__(self, **kwargs):
                    super().__init__(name="custom-agent", description="A custom agent", **kwargs)

                    # additional_properties stores runtime configuration but isn't serialized
                    self.additional_properties.update({
                        "runtime_context": {...},
                        "session_data": {...}
                    })


            agent = CustomAgent(
                context_providers=[...],
                middleware=[...]
            )

            # Serialization captures agent configuration but excludes runtime data
            agent_dict = agent.to_dict()
            # Result: {
            #     "type": "custom_agent",
            #     "id": "...",
            #     "name": "custom-agent",
            #     "description": "A custom agent",
            #     "context_provider": [...],
            #     "middleware": [...]
            #     # additional_properties excluded
            # }

            # Agent can be reconstructed with the same configuration
            restored_agent = CustomAgent.from_dict(agent_dict)

        This approach enables the agent framework to maintain clean separation between
        persistent configuration and transient runtime state, allowing agents and tools
        to be serialized for storage or transmission while preserving their functionality.
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = set()
    INJECTABLE: ClassVar[set[str]] = set()

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Convert the instance and any nested objects to a dictionary.

        This method performs deep serialization, automatically converting nested
        ``SerializationProtocol`` objects, lists, and dictionaries containing
        serializable objects. Non-serializable objects are skipped with debug logging.

        Fields marked in ``DEFAULT_EXCLUDE`` and ``INJECTABLE`` are automatically
        excluded from the output, as are any private attributes (starting with '_').

        Keyword Args:
            exclude: Additional field names to exclude from serialization beyond
                    the default exclusions (``DEFAULT_EXCLUDE`` and ``INJECTABLE``).
            exclude_none: Whether to exclude None values from the output. When True,
                         None values are omitted from the dictionary. Defaults to True.

        Returns:
            Dictionary representation of the instance including a 'type' field
            for type identification during deserialization (unless 'type' is excluded).
        """
        # Combine exclude sets
        combined_exclude = set(self.DEFAULT_EXCLUDE)
        if exclude:
            combined_exclude.update(exclude)
        combined_exclude.update(self.INJECTABLE)

        # Get all instance attributes
        result: dict[str, Any] = {} if "type" in combined_exclude else {"type": self._get_type_identifier()}
        for key, value in self.__dict__.items():
            if key not in combined_exclude and not key.startswith("_"):
                if exclude_none and value is None:
                    continue
                # Recursively serialize SerializationProtocol objects
                if isinstance(value, SerializationProtocol):
                    result[key] = value.to_dict(exclude=exclude, exclude_none=exclude_none)
                    continue
                # Handle lists containing SerializationProtocol objects
                if isinstance(value, list):
                    value_as_list: list[Any] = []
                    for item in value:
                        if isinstance(item, SerializationProtocol):
                            value_as_list.append(item.to_dict(exclude=exclude, exclude_none=exclude_none))
                            continue
                        if is_serializable(item):
                            value_as_list.append(item)
                            continue
                        logger.debug(
                            f"Skipping non-serializable item in list attribute '{key}' of type {type(item).__name__}"
                        )
                    result[key] = value_as_list
                    continue
                # Handle dicts containing SerializationProtocol values
                if isinstance(value, dict):
                    serialized_dict: dict[str, Any] = {}
                    for k, v in value.items():
                        if isinstance(v, SerializationProtocol):
                            serialized_dict[k] = v.to_dict(exclude=exclude, exclude_none=exclude_none)
                            continue
                        # Check if the value is JSON serializable
                        if is_serializable(v):
                            serialized_dict[k] = v
                            continue
                        logger.debug(
                            f"Skipping non-serializable value for key '{k}' in dict attribute '{key}' "
                            f"of type {type(v).__name__}"
                        )
                    result[key] = serialized_dict
                    continue
                # Directly include JSON serializable values
                if is_serializable(value):
                    result[key] = value
                    continue
                logger.debug(f"Skipping non-serializable attribute '{key}' of type {type(value).__name__}")

        return result

    def to_json(self, *, exclude: set[str] | None = None, exclude_none: bool = True, **kwargs: Any) -> str:
        """Convert the instance to a JSON string.

        This is a convenience method that calls ``to_dict()`` and then serializes
        the result using ``json.dumps()``. All the same serialization rules apply
        as in ``to_dict()``, including automatic exclusion of injectable dependencies
        and deep serialization of nested objects.

        Keyword Args:
            exclude: Additional field names to exclude from serialization.
            exclude_none: Whether to exclude None values from the output. Defaults to True.
            **kwargs: Additional keyword arguments passed through to ``json.dumps()``.
                     Common options include ``indent`` for pretty-printing and
                     ``ensure_ascii`` for Unicode handling.

        Returns:
            JSON string representation of the instance.
        """
        return json.dumps(self.to_dict(exclude=exclude, exclude_none=exclude_none), **kwargs)

    @classmethod
    def from_dict(
        cls: type[TClass], value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> TClass:
        """Create an instance from a dictionary with optional dependency injection.

        This method reconstructs an object from its dictionary representation, automatically
        handling type conversion and dependency injection. It supports three patterns of
        dependency injection to handle different scenarios where external dependencies
        need to be provided at deserialization time.

        Args:
            value: The dictionary containing the instance data (positional-only).
                   Must include a 'type' field matching the class type identifier.

        Keyword Args:
            dependencies: A nested dictionary mapping type identifiers to their injectable dependencies.
                The structure varies based on injection pattern:

                - **Simple injection**: ``{"<type>": {"<parameter>": value}}``
                - **Dict parameter injection**: ``{"<type>": {"<dict-parameter>": {"<key>": value}}}``
                - **Instance-specific injection**: ``{"<type>": {"<field>:<value>": {"<parameter>": value}}}``

        Returns:
            New instance of the class with injected dependencies.

        Raises:
            ValueError: If the 'type' field in the data doesn't match the class type identifier.

        Examples:
            **Simple Client Injection** - OpenAI client dependency injection:

            .. code-block:: python

                from agent_framework.openai import OpenAIChatClient
                from openai import AsyncOpenAI


                # OpenAI chat client requires an AsyncOpenAI client instance
                # The client is marked as INJECTABLE = {"client"} in OpenAIBase

                # Serialized data contains only the model configuration
                client_data = {
                    "type": "open_ai_chat_client",
                    "model_id": "gpt-4o-mini",
                    # client is excluded from serialization
                }

                # Provide the OpenAI client during deserialization
                openai_client = AsyncOpenAI(api_key="your-api-key")
                dependencies = {"open_ai_chat_client": {"client": openai_client}}

                # The chat client is reconstructed with the OpenAI client injected
                chat_client = OpenAIChatClient.from_dict(client_data, dependencies=dependencies)
                # Now ready to make API calls with the injected client

            **Function Injection for Tools** - AIFunction runtime dependency:

            .. code-block:: python

                from agent_framework import AIFunction
                from typing import Annotated


                # Define a function to be wrapped
                async def get_current_weather(location: Annotated[str, "The city name"]) -> str:
                    # In real implementation, this would call a weather API
                    return f"Current weather in {location}: 72°F and sunny"


                # AIFunction has INJECTABLE = {"func"}
                function_data = {
                    "type": "ai_function",
                    "name": "get_weather",
                    "description": "Get current weather for a location",
                    # func is excluded from serialization
                }

                # Inject the actual function implementation during deserialization
                dependencies = {"ai_function": {"func": get_current_weather}}

                # Reconstruct the AIFunction with the callable injected
                weather_func = AIFunction.from_dict(function_data, dependencies=dependencies)
                # The function is now callable and ready for agent use

            **Middleware Context Injection** - Agent execution context:

            .. code-block:: python

                from agent_framework._middleware import AgentRunContext
                from agent_framework import BaseAgent

                # AgentRunContext has INJECTABLE = {"agent", "result"}
                context_data = {
                    "type": "agent_run_context",
                    "messages": [{"role": "user", "text": "Hello"}],
                    "is_streaming": False,
                    "metadata": {"session_id": "abc123"},
                    # agent and result are excluded from serialization
                }

                # Inject agent and result during middleware processing
                my_agent = BaseAgent(name="test-agent")
                dependencies = {
                    "agent_run_context": {
                        "agent": my_agent,
                        "result": None,  # Will be populated during execution
                    }
                }

                # Reconstruct context with agent dependency for middleware chain
                context = AgentRunContext.from_dict(context_data, dependencies=dependencies)
                # Middleware can now access context.agent and process the execution

            This injection system allows the agent framework to maintain clean separation
            between serializable configuration and runtime dependencies like API clients,
            functions, and execution contexts that cannot or should not be persisted.
        """
        if dependencies is None:
            dependencies = {}

        # Get the type identifier
        type_id = cls._get_type_identifier(value)

        if (supplied_type := value.get("type")) and supplied_type != type_id:
            raise ValueError(f"Type mismatch: expected '{type_id}', got '{supplied_type}'")

        # Create a copy of the value dict to work with, filtering out the 'type' key
        kwargs = {k: v for k, v in value.items() if k != "type"}

        # Process dependencies using dict-based structure
        type_deps = dependencies.get(type_id, {})
        for dep_key, dep_value in type_deps.items():
            # Check if this is an instance-specific dependency (field:name format)
            if ":" in dep_key:
                field, name = dep_key.split(":", 1)
                # Only apply if the instance matches
                if kwargs.get(field) == name and isinstance(dep_value, dict):
                    # Apply instance-specific dependencies
                    for param_name, param_value in dep_value.items():
                        if param_name not in cls.INJECTABLE:
                            logger.debug(
                                f"Dependency '{param_name}' for type '{type_id}' is not in INJECTABLE set. "
                                f"Available injectable parameters: {cls.INJECTABLE}"
                            )
                        # Handle nested dict parameters
                        if (
                            isinstance(param_value, dict)
                            and param_name in kwargs
                            and isinstance(kwargs[param_name], dict)
                        ):
                            kwargs[param_name].update(param_value)
                        else:
                            kwargs[param_name] = param_value
            else:
                # Regular parameter dependency
                if dep_key not in cls.INJECTABLE:
                    logger.debug(
                        f"Dependency '{dep_key}' for type '{type_id}' is not in INJECTABLE set. "
                        f"Available injectable parameters: {cls.INJECTABLE}"
                    )
                # Handle dict parameters - merge if both are dicts
                if isinstance(dep_value, dict) and dep_key in kwargs and isinstance(kwargs[dep_key], dict):
                    kwargs[dep_key].update(dep_value)
                else:
                    kwargs[dep_key] = dep_value

        return cls(**kwargs)

    @classmethod
    def from_json(cls: type[TClass], value: str, /, *, dependencies: MutableMapping[str, Any] | None = None) -> TClass:
        """Create an instance from a JSON string.

        This is a convenience method that parses the JSON string using ``json.loads()``
        and then calls ``from_dict()`` to reconstruct the object. All dependency injection
        capabilities are available through the ``dependencies`` parameter.

        Args:
            value: The JSON string containing the instance data (positional-only).
                   Must be valid JSON that deserializes to a dictionary with a 'type' field.

        Keyword Args:
            dependencies: A nested dictionary mapping type identifiers to their injectable dependencies.
                         See :meth:`from_dict` for detailed structure and examples of the three
                         injection patterns (simple, dict parameter, and instance-specific).

        Returns:
            New instance of the class with any specified dependencies injected.

        Raises:
            json.JSONDecodeError: If the JSON string is malformed.
            ValueError: If the parsed data doesn't contain a valid 'type' field.
        """
        data = json.loads(value)
        return cls.from_dict(data, dependencies=dependencies)

    @classmethod
    def _get_type_identifier(cls, value: Mapping[str, Any] | None = None) -> str:
        """Get the type identifier for this class.

        The type identifier is used in serialized data to enable proper deserialization.
        It follows a priority order to determine the identifier:

        1. If ``value`` contains a 'type' field, return that value (for ``from_dict``)
        2. If the class has a ``type`` attribute, use that value (instance-level)
        3. If the class has a ``TYPE`` attribute, use that value (class-level constant)
        4. Otherwise, convert the class name to snake_case as fallback

        Args:
            value: Optional mapping containing serialized data that may have a 'type' field.

        Returns:
            Type identifier string used for serialization and dependency injection mapping.
        """
        # for from_dict
        if value and (type_ := value.get("type")) and isinstance(type_, str):
            return type_  # type:ignore[no-any-return]
        # for todict when defined per instance
        if (type_ := getattr(cls, "type", None)) and isinstance(type_, str):
            return type_  # type:ignore[no-any-return]
        # for both when defined on class.
        if (type_ := getattr(cls, "TYPE", None)) and isinstance(type_, str):
            return type_  # type:ignore[no-any-return]
        # Fallback and default
        # Convert class name to snake_case
        return _CAMEL_TO_SNAKE_PATTERN.sub("_", cls.__name__).lower()
