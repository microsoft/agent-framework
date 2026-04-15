# Copyright (c) Microsoft. All rights reserved.

"""Checkpoint encoding using JSON structure with pickle+base64 for arbitrary data.

This hybrid approach provides:
- Human-readable JSON structure for debugging and inspection of primitives and collections
- Full Python object fidelity via pickle for data values (non-JSON-native types)
- Base64 encoding to embed binary pickle data in JSON strings

When ``allowed_types`` is supplied to :func:`decode_checkpoint_value`, a
``RestrictedUnpickler`` is used that limits which classes may be instantiated
during deserialization.  The default built-in safe set covers common Python
value types (primitives, datetime, uuid, ...) and all ``agent_framework``
internal types.  Callers can extend the set by passing additional
``"module:qualname"`` strings.
"""

from __future__ import annotations

import base64
import io
import logging
import pickle  # nosec  # noqa: S403
from typing import Any

from ..exceptions import WorkflowCheckpointException

logger = logging.getLogger("agent_framework")

# Marker to identify pickled values in serialized JSON
_PICKLE_MARKER = "__pickled__"
_TYPE_MARKER = "__type__"

# Types that are natively JSON-serializable and don't need pickling
_JSON_NATIVE_TYPES = (str, int, float, bool, type(None))

# Module prefix for framework-internal types that are always allowed
_FRAMEWORK_MODULE_PREFIX = "agent_framework."

# Built-in types considered safe for checkpoint deserialization.
# Each entry is a ``module:qualname`` string matching the format produced by
# :func:`_type_to_key`.  These are the classes for which pickle's
# ``find_class`` will be called when unpickling common Python value types.
_BUILTIN_ALLOWED_TYPE_KEYS: frozenset[str] = frozenset({
    # builtins
    "builtins:object",
    "builtins:complex",
    "builtins:range",
    "builtins:slice",
    "builtins:int",
    "builtins:float",
    "builtins:str",
    "builtins:bytes",
    "builtins:bytearray",
    "builtins:bool",
    "builtins:set",
    "builtins:frozenset",
    "builtins:list",
    "builtins:dict",
    "builtins:tuple",
    "builtins:type",
    # getattr is used by pickle to reconstruct enum members
    "builtins:getattr",
    # copyreg helpers used by pickle for object reconstruction
    "copyreg:_reconstructor",
    # datetime
    "datetime:datetime",
    "datetime:date",
    "datetime:time",
    "datetime:timedelta",
    "datetime:timezone",
    # uuid
    "uuid:UUID",
    # decimal
    "decimal:Decimal",
    # collections
    "collections:OrderedDict",
    "collections:defaultdict",
    "collections:deque",
})


class _RestrictedUnpickler(pickle.Unpickler):  # noqa: S301
    """Unpickler that restricts which classes may be instantiated.

    Only classes whose ``module:qualname`` key appears in the combined allow
    set (built-in safe types + framework types + caller-specified extras) are
    permitted.  All other classes raise :class:`pickle.UnpicklingError`.
    """

    def __init__(self, data: bytes, allowed_types: frozenset[str]) -> None:
        super().__init__(io.BytesIO(data))
        self._allowed_types = allowed_types

    def find_class(self, module: str, name: str) -> type:
        type_key = f"{module}:{name}"

        if (
            type_key in _BUILTIN_ALLOWED_TYPE_KEYS
            or type_key in self._allowed_types
            or module.startswith(_FRAMEWORK_MODULE_PREFIX)
        ):
            return super().find_class(module, name)  # type: ignore[no-any-return]  # nosec

        raise pickle.UnpicklingError(
            f"Checkpoint deserialization blocked for type '{type_key}'. "
            f"To allow this type, either include its 'module:qualname' key in the "
            f"'allowed_types' set passed to 'decode_checkpoint_value', or add it to "
            f"'allowed_checkpoint_types' on your checkpoint storage "
            f"(for example, 'FileCheckpointStorage.allowed_checkpoint_types')."
        )


def encode_checkpoint_value(value: Any) -> Any:
    """Encode a Python value for checkpoint storage.

    JSON-native types (str, int, float, bool, None) pass through unchanged.
    Collections (dict, list) are recursed with their values encoded.
    All other types (dataclasses, custom objects, datetime, etc.) are pickled
    and stored as base64-encoded strings.

    Args:
        value: Any Python value to encode.

    Returns:
        A JSON-serializable representation of the value.
    """
    return _encode(value)


def decode_checkpoint_value(value: Any, *, allowed_types: frozenset[str] | None = None) -> Any:
    """Decode a value from checkpoint storage.

    Reverses the encoding performed by encode_checkpoint_value.
    Pickled values (identified by _PICKLE_MARKER) are decoded and unpickled.

    Args:
        value: A JSON-deserialized value from checkpoint storage.
        allowed_types: If not ``None``, restrict pickle deserialization to the
            built-in safe set, framework types, and the types listed here.
            Each entry should use ``"module:qualname"`` format — that is, the
            dotted module path followed by a colon and the class
            ``__qualname__``.  For example, given a user-defined class::

                # my_app/models.py
                class MyState: ...

            the corresponding entry would be ``"my_app.models:MyState"``::

                decode_checkpoint_value(
                    data,
                    allowed_types=frozenset({"my_app.models:MyState"}),
                )

            When using :class:`FileCheckpointStorage`, pass the same strings
            via ``allowed_checkpoint_types``::

                storage = FileCheckpointStorage(
                    "/tmp/checkpoints",
                    allowed_checkpoint_types=["my_app.models:MyState"],
                )

            If ``None``, no restriction is applied (backward-compatible
            behavior).

    Returns:
        The original Python value.

    Raises:
        WorkflowCheckpointException: If the unpickled object's type doesn't match
            the recorded type, indicating corruption, if the base64/pickle
            data is malformed, or if a disallowed type is encountered during
            restricted deserialization.
    """
    return _decode(value, allowed_types=allowed_types)


def _encode(value: Any) -> Any:
    """Recursively encode a value for JSON storage."""
    # JSON-native types pass through
    if isinstance(value, _JSON_NATIVE_TYPES):
        return value

    # Recursively encode dict values (keys become strings)
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}  # type: ignore

    # Recursively encode list items (lists are JSON-native collections)
    if isinstance(value, list):
        return [_encode(item) for item in value]  # type: ignore

    # Everything else (tuples, sets, dataclasses, custom objects, etc.): pickle and base64 encode
    return {
        _PICKLE_MARKER: _pickle_to_base64(value),
        _TYPE_MARKER: _type_to_key(type(value)),  # type: ignore
    }


def _decode(value: Any, *, allowed_types: frozenset[str] | None = None) -> Any:
    """Recursively decode a value from JSON storage."""
    # JSON-native types pass through
    if isinstance(value, _JSON_NATIVE_TYPES):
        return value

    # Handle encoded dicts
    if isinstance(value, dict):
        # Pickled value: decode, unpickle, and verify type
        if _PICKLE_MARKER in value and _TYPE_MARKER in value:
            obj = _base64_to_unpickle(value[_PICKLE_MARKER], allowed_types=allowed_types)  # type: ignore
            _verify_type(obj, value.get(_TYPE_MARKER))  # type: ignore
            return obj

        # Regular dict: decode values recursively
        return {k: _decode(v, allowed_types=allowed_types) for k, v in value.items()}  # type: ignore

    # Handle encoded lists
    if isinstance(value, list):
        return [_decode(item, allowed_types=allowed_types) for item in value]  # type: ignore

    return value


def _verify_type(obj: Any, expected_type_key: str) -> None:
    """Verify that an unpickled object matches its recorded type.

    This is a post-deserialization integrity check that detects accidental
    corruption or type mismatches. It does not prevent arbitrary code execution
    from malicious pickle payloads, since ``pickle.loads()`` has already
    executed by the time this function is called.

    Args:
        obj: The unpickled object.
        expected_type_key: The recorded type key (module:qualname format).

    Raises:
        WorkflowCheckpointException: If the types don't match.
    """
    actual_type_key = _type_to_key(type(obj))  # type: ignore
    if actual_type_key != expected_type_key:
        raise WorkflowCheckpointException(
            f"Type mismatch during checkpoint decoding: "
            f"expected '{expected_type_key}', got '{actual_type_key}'. "
            f"The checkpoint may be corrupted or tampered with."
        )


def _pickle_to_base64(value: Any) -> str:
    """Pickle a value and encode as base64 string."""
    pickled = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    return base64.b64encode(pickled).decode("ascii")


def _base64_to_unpickle(encoded: str, *, allowed_types: frozenset[str] | None = None) -> Any:
    """Decode base64 string and unpickle.

    Args:
        encoded: Base64-encoded pickle data.
        allowed_types: If not ``None``, use restricted unpickling that only
            permits built-in safe types, framework types, and the specified
            extra types.

    Raises:
        WorkflowCheckpointException: If the base64 data is corrupted, the pickle
            format is incompatible, or a disallowed type is encountered.
    """
    try:
        pickled = base64.b64decode(encoded.encode("ascii"))
        if allowed_types is not None:
            return _RestrictedUnpickler(pickled, allowed_types).load()
        return pickle.loads(pickled)  # nosec  # noqa: S301
    except Exception as exc:
        raise WorkflowCheckpointException(f"Failed to decode pickled checkpoint data: {exc}") from exc


def _type_to_key(t: type) -> str:
    """Convert a type to a module:qualname string."""
    return f"{t.__module__}:{t.__qualname__}"
