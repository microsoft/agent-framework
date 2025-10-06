# Copyright (c) Microsoft. All rights reserved.

"""Utility functions for DevUI."""

import inspect
import json
import logging
from dataclasses import fields, is_dataclass
from typing import Any, get_args, get_origin

logger = logging.getLogger(__name__)

# ============================================================================
# Type System Utilities
# ============================================================================


def is_serialization_mixin(cls: type) -> bool:
    """Check if class is a SerializationMixin subclass.

    Args:
        cls: Class to check

    Returns:
        True if class is a SerializationMixin subclass
    """
    try:
        from agent_framework._serialization import SerializationMixin

        return isinstance(cls, type) and issubclass(cls, SerializationMixin)
    except ImportError:
        return False


def _type_to_schema(type_hint: Any, field_name: str) -> dict[str, Any]:
    """Convert a type hint to JSON schema.

    Args:
        type_hint: Type hint to convert
        field_name: Name of the field (for documentation)

    Returns:
        JSON schema dict
    """
    type_str = str(type_hint)

    # Handle None/Optional
    if type_hint is type(None):
        return {"type": "null"}

    # Handle basic types
    if type_hint is str or "str" in type_str:
        return {"type": "string"}
    if type_hint is int or "int" in type_str:
        return {"type": "integer"}
    if type_hint is float or "float" in type_str:
        return {"type": "number"}
    if type_hint is bool or "bool" in type_str:
        return {"type": "boolean"}

    # Handle Literal types (for enum-like values)
    if "Literal" in type_str:
        origin = get_origin(type_hint)
        if origin is not None:
            args = get_args(type_hint)
            if args:
                return {"type": "string", "enum": list(args)}

    # Handle Union/Optional
    if "Union" in type_str or "Optional" in type_str:
        origin = get_origin(type_hint)
        if origin is not None:
            args = get_args(type_hint)
            # Filter out None type
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                return _type_to_schema(non_none_args[0], field_name)
            # Multiple types - pick first non-None
            if non_none_args:
                return _type_to_schema(non_none_args[0], field_name)

    # Handle collections
    if "list" in type_str or "List" in type_str or "Sequence" in type_str:
        origin = get_origin(type_hint)
        if origin is not None:
            args = get_args(type_hint)
            if args:
                items_schema = _type_to_schema(args[0], field_name)
                return {"type": "array", "items": items_schema}
        return {"type": "array"}

    if "dict" in type_str or "Dict" in type_str or "Mapping" in type_str:
        return {"type": "object"}

    # Default fallback
    return {"type": "string", "description": f"Type: {type_hint}"}


def generate_schema_from_serialization_mixin(cls: type[Any]) -> dict[str, Any]:
    """Generate JSON schema from SerializationMixin class.

    Introspects the __init__ signature to extract parameter types and defaults.

    Args:
        cls: SerializationMixin subclass

    Returns:
        JSON schema dict
    """
    sig = inspect.signature(cls)

    # Get type hints
    try:
        from typing import get_type_hints

        type_hints = get_type_hints(cls)
    except Exception:
        type_hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "kwargs"):
            continue

        # Get type annotation
        param_type = type_hints.get(param_name, str)

        # Generate schema for this parameter
        param_schema = _type_to_schema(param_type, param_name)
        properties[param_name] = param_schema

        # Check if required (no default value, not VAR_KEYWORD)
        if param.default == inspect.Parameter.empty and param.kind != inspect.Parameter.VAR_KEYWORD:
            required.append(param_name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}

    if required:
        schema["required"] = required

    return schema


def generate_schema_from_dataclass(cls: type[Any]) -> dict[str, Any]:
    """Generate JSON schema from dataclass.

    Args:
        cls: Dataclass type

    Returns:
        JSON schema dict
    """
    if not is_dataclass(cls):
        return {"type": "object"}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for field in fields(cls):
        # Generate schema for field type
        field_schema = _type_to_schema(field.type, field.name)
        properties[field.name] = field_schema

        # Check if required (no default value)
        if field.default == field.default_factory:  # No default
            required.append(field.name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}

    if required:
        schema["required"] = required

    return schema


def generate_input_schema(input_type: type) -> dict[str, Any]:
    """Generate JSON schema for workflow input type.

    Supports multiple input types in priority order:
    1. Built-in types (str, dict, int, etc.)
    2. Pydantic models (via model_json_schema)
    3. SerializationMixin classes (via __init__ introspection)
    4. Dataclasses (via fields introspection)
    5. Fallback to string

    Args:
        input_type: Input type to generate schema for

    Returns:
        JSON schema dict
    """
    # 1. Built-in types
    if input_type is str:
        return {"type": "string"}
    if input_type is dict:
        return {"type": "object"}
    if input_type is int:
        return {"type": "integer"}
    if input_type is float:
        return {"type": "number"}
    if input_type is bool:
        return {"type": "boolean"}

    # 2. Pydantic models (legacy support)
    if hasattr(input_type, "model_json_schema"):
        return input_type.model_json_schema()  # type: ignore

    # 3. SerializationMixin classes (ChatMessage, etc.)
    if is_serialization_mixin(input_type):
        return generate_schema_from_serialization_mixin(input_type)

    # 4. Dataclasses
    if is_dataclass(input_type):
        return generate_schema_from_dataclass(input_type)

    # 5. Fallback to string
    type_name = getattr(input_type, "__name__", str(input_type))
    return {"type": "string", "description": f"Input type: {type_name}"}


# ============================================================================
# Input Parsing Utilities
# ============================================================================


def parse_input_for_type(input_data: Any, target_type: type) -> Any:
    """Parse input data to match the target type.

    Handles conversion from raw input (string, dict) to the expected type:
    - Built-in types: direct conversion
    - Pydantic models: use model_validate or model_validate_json
    - SerializationMixin: use from_dict or construct from string
    - Dataclasses: construct from dict

    Args:
        input_data: Raw input data (string, dict, or already correct type)
        target_type: Expected type for the input

    Returns:
        Parsed input matching target_type, or original input if parsing fails
    """
    # If already correct type, return as-is
    if isinstance(input_data, target_type):
        return input_data

    # Handle string input
    if isinstance(input_data, str):
        return _parse_string_input(input_data, target_type)

    # Handle dict input
    if isinstance(input_data, dict):
        return _parse_dict_input(input_data, target_type)

    # Fallback: return original
    return input_data


def _parse_string_input(input_str: str, target_type: type) -> Any:
    """Parse string input to target type.

    Args:
        input_str: Input string
        target_type: Target type

    Returns:
        Parsed input or original string
    """
    # Built-in types
    if target_type is str:
        return input_str
    if target_type is int:
        try:
            return int(input_str)
        except ValueError:
            return input_str
    elif target_type is float:
        try:
            return float(input_str)
        except ValueError:
            return input_str
    elif target_type is bool:
        return input_str.lower() in ("true", "1", "yes")

    # Pydantic models
    if hasattr(target_type, "model_validate_json"):
        try:
            # Try parsing as JSON first
            if input_str.strip().startswith("{"):
                return target_type.model_validate_json(input_str)  # type: ignore

            # Try common field names with the string value
            common_fields = ["text", "message", "content", "input", "data"]
            for field in common_fields:
                try:
                    return target_type(**{field: input_str})  # type: ignore
                except Exception as e:
                    logger.debug(f"Failed to parse string input with field '{field}': {e}")
                    continue
        except Exception as e:
            logger.debug(f"Failed to parse string as Pydantic model: {e}")

    # SerializationMixin (like ChatMessage)
    if is_serialization_mixin(target_type):
        try:
            # Try parsing as JSON dict first
            if input_str.strip().startswith("{"):
                data = json.loads(input_str)
                if hasattr(target_type, "from_dict"):
                    return target_type.from_dict(data)  # type: ignore
                return target_type(**data)  # type: ignore

            # For ChatMessage specifically: create from text
            # Try common field patterns
            common_fields = ["text", "message", "content"]
            sig = inspect.signature(target_type)
            params = list(sig.parameters.keys())

            # If it has 'text' param, use it
            if "text" in params:
                try:
                    return target_type(role="user", text=input_str)  # type: ignore
                except Exception as e:
                    logger.debug(f"Failed to create SerializationMixin with text field: {e}")

            # Try other common fields
            for field in common_fields:
                if field in params:
                    try:
                        return target_type(**{field: input_str})  # type: ignore
                    except Exception as e:
                        logger.debug(f"Failed to create SerializationMixin with field '{field}': {e}")
                        continue
        except Exception as e:
            logger.debug(f"Failed to parse string as SerializationMixin: {e}")

    # Dataclasses
    if is_dataclass(target_type):
        try:
            # Try parsing as JSON
            if input_str.strip().startswith("{"):
                data = json.loads(input_str)
                return target_type(**data)  # type: ignore

            # Try common field names
            common_fields = ["text", "message", "content", "input", "data"]
            for field in common_fields:
                try:
                    return target_type(**{field: input_str})  # type: ignore
                except Exception as e:
                    logger.debug(f"Failed to create dataclass with field '{field}': {e}")
                    continue
        except Exception as e:
            logger.debug(f"Failed to parse string as dataclass: {e}")

    # Fallback: return original string
    return input_str


def _parse_dict_input(input_dict: dict[str, Any], target_type: type) -> Any:
    """Parse dict input to target type.

    Args:
        input_dict: Input dictionary
        target_type: Target type

    Returns:
        Parsed input or original dict
    """
    # Handle primitive types - extract from common field names
    if target_type in (str, int, float, bool):
        try:
            # If it's already the right type, return as-is
            if isinstance(input_dict, target_type):
                return input_dict

            # Try "input" field first (common for workflow inputs)
            if "input" in input_dict:
                return target_type(input_dict["input"])  # type: ignore

            # If single-key dict, extract the value
            if len(input_dict) == 1:
                value = next(iter(input_dict.values()))
                return target_type(value)  # type: ignore

            # Otherwise, return as-is
            return input_dict
        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to convert dict to {target_type}: {e}")
            return input_dict

    # If target is dict, return as-is
    if target_type is dict:
        return input_dict

    # Pydantic models
    if hasattr(target_type, "model_validate"):
        try:
            return target_type.model_validate(input_dict)  # type: ignore
        except Exception as e:
            logger.debug(f"Failed to validate dict as Pydantic model: {e}")

    # SerializationMixin
    if is_serialization_mixin(target_type):
        try:
            if hasattr(target_type, "from_dict"):
                return target_type.from_dict(input_dict)  # type: ignore
            return target_type(**input_dict)  # type: ignore
        except Exception as e:
            logger.debug(f"Failed to parse dict as SerializationMixin: {e}")

    # Dataclasses
    if is_dataclass(target_type):
        try:
            return target_type(**input_dict)  # type: ignore
        except Exception as e:
            logger.debug(f"Failed to parse dict as dataclass: {e}")

    # Fallback: return original dict
    return input_dict
