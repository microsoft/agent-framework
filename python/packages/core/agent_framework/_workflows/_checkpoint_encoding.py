# Copyright (c) Microsoft. All rights reserved.

import contextlib
import importlib
import logging
import sys
from dataclasses import fields, is_dataclass
from typing import Any, cast

# Checkpoint serialization helpers
MODEL_MARKER = "__af_model__"
DATACLASS_MARKER = "__af_dataclass__"

# Guards to prevent runaway recursion while encoding arbitrary user data
_MAX_ENCODE_DEPTH = 100
_CYCLE_SENTINEL = "<cycle>"

logger = logging.getLogger(__name__)


def encode_checkpoint_value(value: Any) -> Any:
    """Recursively encode values into JSON-serializable structures.

    - Objects exposing to_dict/to_json -> { MODEL_MARKER: "module:Class", value: encoded }
    - dataclass instances -> { DATACLASS_MARKER: "module:Class", value: {field: encoded} }
    - dict -> encode keys as str and values recursively
    - list/tuple/set -> list of encoded items
    - other -> returned as-is if already JSON-serializable

    Includes cycle and depth protection to avoid infinite recursion.
    """

    def _enc(v: Any, stack: set[int], depth: int) -> Any:
        # Depth guard
        if depth > _MAX_ENCODE_DEPTH:
            logger.debug(f"Max encode depth reached at depth={depth} for type={type(v)}")
            return "<max_depth>"

        # Structured model handling (objects exposing to_dict/to_json)
        if _supports_model_protocol(v):
            cls = cast(type[Any], type(v))  # type: ignore
            try:
                if hasattr(v, "to_dict") and callable(getattr(v, "to_dict", None)):
                    raw = v.to_dict()  # type: ignore[attr-defined]
                    strategy = "to_dict"
                elif hasattr(v, "to_json") and callable(getattr(v, "to_json", None)):
                    serialized = v.to_json()  # type: ignore[attr-defined]
                    if isinstance(serialized, (bytes, bytearray)):
                        try:
                            serialized = serialized.decode()
                        except Exception:
                            serialized = serialized.decode(errors="replace")
                    raw = serialized
                    strategy = "to_json"
                else:
                    raise AttributeError("Structured model lacks serialization hooks")
                return {
                    MODEL_MARKER: f"{cls.__module__}:{cls.__name__}",
                    "strategy": strategy,
                    "value": _enc(raw, stack, depth + 1),
                }
            except Exception as exc:  # best-effort fallback
                logger.debug(f"Structured model serialization failed for {cls}: {exc}")
                return str(v)

        # Dataclasses (instances only)
        if is_dataclass(v) and not isinstance(v, type):
            oid = id(v)
            if oid in stack:
                logger.debug("Cycle detected while encoding dataclass instance")
                return _CYCLE_SENTINEL
            stack.add(oid)
            try:
                # type(v) already narrows sufficiently; cast was redundant
                dc_cls: type[Any] = type(v)
                field_values: dict[str, Any] = {}
                for f in fields(v):
                    field_values[f.name] = _enc(getattr(v, f.name), stack, depth + 1)
                return {
                    DATACLASS_MARKER: f"{dc_cls.__module__}:{dc_cls.__name__}",
                    "value": field_values,
                }
            finally:
                stack.remove(oid)

        # Collections
        if isinstance(v, dict):
            v_dict = cast("dict[object, object]", v)
            oid = id(v_dict)
            if oid in stack:
                logger.debug("Cycle detected while encoding dict")
                return _CYCLE_SENTINEL
            stack.add(oid)
            try:
                json_dict: dict[str, Any] = {}
                for k_any, val_any in v_dict.items():  # type: ignore[assignment]
                    k_str: str = str(k_any)
                    json_dict[k_str] = _enc(val_any, stack, depth + 1)
                return json_dict
            finally:
                stack.remove(oid)

        if isinstance(v, (list, tuple, set)):
            iterable_v = cast("list[object] | tuple[object, ...] | set[object]", v)
            oid = id(iterable_v)
            if oid in stack:
                logger.debug("Cycle detected while encoding iterable")
                return _CYCLE_SENTINEL
            stack.add(oid)
            try:
                seq: list[object] = list(iterable_v)
                encoded_list: list[Any] = []
                for item in seq:
                    encoded_list.append(_enc(item, stack, depth + 1))
                return encoded_list
            finally:
                stack.remove(oid)

        # Primitives (or unknown objects): ensure JSON-serializable
        if isinstance(v, (str, int, float, bool)) or v is None:
            return v
        # Fallback: stringify unknown objects to avoid JSON serialization errors
        try:
            return str(v)
        except Exception:
            return f"<{type(v).__name__}>"

    return _enc(value, set(), 0)


def decode_checkpoint_value(value: Any) -> Any:
    """Recursively decode values previously encoded by encode_checkpoint_value."""
    if isinstance(value, dict):
        value_dict = cast(dict[str, Any], value)  # encoded form always uses string keys
        # Structured model marker handling
        if MODEL_MARKER in value_dict and "value" in value_dict:
            type_key: str | None = value_dict.get(MODEL_MARKER)  # type: ignore[assignment]
            strategy: str | None = value_dict.get("strategy")  # type: ignore[assignment]
            raw_encoded: Any = value_dict.get("value")
            decoded_payload = decode_checkpoint_value(raw_encoded)
            if isinstance(type_key, str):
                try:
                    cls = _import_qualified_name(type_key)
                except Exception as exc:
                    logger.debug(f"Failed to import structured model {type_key}: {exc}")
                    cls = None

                if cls is not None:
                    # Verify the class actually supports the model protocol
                    if not _class_supports_model_protocol(cls):
                        logger.debug(f"Class {type_key} does not support model protocol; returning raw value")
                        return decoded_payload
                    if strategy == "to_dict" and hasattr(cls, "from_dict"):
                        with contextlib.suppress(Exception):
                            return cls.from_dict(decoded_payload)
                    if strategy == "to_json" and hasattr(cls, "from_json"):
                        if isinstance(decoded_payload, (str, bytes, bytearray)):
                            with contextlib.suppress(Exception):
                                return cls.from_json(decoded_payload)
                        if isinstance(decoded_payload, dict) and hasattr(cls, "from_dict"):
                            with contextlib.suppress(Exception):
                                return cls.from_dict(decoded_payload)
            return decoded_payload
        # Dataclass marker handling
        if DATACLASS_MARKER in value_dict and "value" in value_dict:
            type_key_dc: str | None = value_dict.get(DATACLASS_MARKER)  # type: ignore[assignment]
            raw_dc: Any = value_dict.get("value")
            decoded_raw = decode_checkpoint_value(raw_dc)
            if isinstance(type_key_dc, str):
                try:
                    module_name, class_name = type_key_dc.split(":", 1)
                    module = sys.modules.get(module_name)
                    if module is None:
                        module = importlib.import_module(module_name)
                    cls_dc: Any = getattr(module, class_name)
                    # Verify the class is actually a dataclass type (not an instance)
                    if not isinstance(cls_dc, type) or not is_dataclass(cls_dc):
                        logger.debug(f"Class {type_key_dc} is not a dataclass type; returning raw value")
                        return decoded_raw
                    constructed = _instantiate_checkpoint_dataclass(cls_dc, decoded_raw)
                    if constructed is not None:
                        return constructed
                except Exception as exc:
                    logger.debug(f"Failed to decode dataclass {type_key_dc}: {exc}; returning raw value")
            return decoded_raw

        # Regular dict: decode recursively
        decoded: dict[str, Any] = {}
        for k_any, v_any in value_dict.items():
            decoded[k_any] = decode_checkpoint_value(v_any)
        return decoded
    if isinstance(value, list):
        # After isinstance check, treat value as list[Any] for decoding
        value_list: list[Any] = value  # type: ignore[assignment]
        return [decode_checkpoint_value(v_any) for v_any in value_list]
    return value


def _class_supports_model_protocol(cls: type[Any]) -> bool:
    """Check if a class type supports the model serialization protocol.

    Checks for pairs of serialization/deserialization methods:
    - to_dict/from_dict
    - to_json/from_json
    """
    has_to_dict = hasattr(cls, "to_dict") and callable(getattr(cls, "to_dict", None))
    has_from_dict = hasattr(cls, "from_dict") and callable(getattr(cls, "from_dict", None))

    has_to_json = hasattr(cls, "to_json") and callable(getattr(cls, "to_json", None))
    has_from_json = hasattr(cls, "from_json") and callable(getattr(cls, "from_json", None))

    return (has_to_dict and has_from_dict) or (has_to_json and has_from_json)


def _supports_model_protocol(obj: object) -> bool:
    """Detect objects that expose dictionary serialization hooks."""
    try:
        obj_type: type[Any] = type(obj)
    except Exception:
        return False

    return _class_supports_model_protocol(obj_type)


def _import_qualified_name(qualname: str) -> type[Any] | None:
    if ":" not in qualname:
        return None
    module_name, class_name = qualname.split(":", 1)
    module = sys.modules.get(module_name)
    if module is None:
        module = importlib.import_module(module_name)
    attr: Any = module
    for part in class_name.split("."):
        attr = getattr(attr, part)
    return attr if isinstance(attr, type) else None


def _instantiate_checkpoint_dataclass(cls: type[Any], payload: Any) -> Any | None:
    if not isinstance(cls, type):
        logger.debug(f"Checkpoint decoder received non-type dataclass reference: {cls!r}")
        return None

    if isinstance(payload, dict):
        try:
            return cls(**payload)  # type: ignore[arg-type]
        except TypeError as exc:
            logger.debug(f"Checkpoint decoder could not call {cls.__name__}(**payload): {exc}")
        except Exception as exc:
            logger.warning(f"Checkpoint decoder encountered unexpected error calling {cls.__name__}(**payload): {exc}")
        try:
            instance = object.__new__(cls)
        except Exception as exc:
            logger.debug(f"Checkpoint decoder could not allocate {cls.__name__} without __init__: {exc}")
            return None
        for key, val in payload.items():  # type: ignore[attr-defined]
            try:
                setattr(instance, key, val)  # type: ignore[arg-type]
            except Exception as exc:
                logger.debug(f"Checkpoint decoder could not set attribute {key} on {cls.__name__}: {exc}")
        return instance

    try:
        return cls(payload)  # type: ignore[call-arg]
    except TypeError as exc:
        logger.debug(f"Checkpoint decoder could not call {cls.__name__}({payload!r}): {exc}")
    except Exception as exc:
        logger.warning(f"Checkpoint decoder encountered unexpected error calling {cls.__name__}({payload!r}): {exc}")
    return None
