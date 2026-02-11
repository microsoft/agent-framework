# Copyright (c) Microsoft. All rights reserved.

"""Generic settings loader with environment variable resolution.

This module provides a ``load_settings()`` function that populates a ``TypedDict``
from environment variables, ``.env`` files, and explicit overrides.  It replaces
the previous pydantic-settings-based ``AFBaseSettings`` with a lighter-weight,
function-based approach that has no pydantic-settings dependency.

Usage::

    class MySettings(TypedDict, total=False):
        api_key: str | None  # optional — resolves to None if not set
        model_id: Required[str]  # required — raises if not set


    settings = load_settings(MySettings, env_prefix="MY_APP_", model_id="gpt-4")
    settings["api_key"]  # type-checked dict access
    settings["model_id"]  # str (never None)
"""

from __future__ import annotations

import os
import sys
from contextlib import suppress
from typing import Any, get_args, get_origin, get_type_hints

from dotenv import load_dotenv

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover

__all__ = ["SecretString", "load_settings"]

SettingsT = TypeVar("SettingsT", default=dict[str, Any])


class SecretString(str):
    """A string subclass that masks its value in repr() to prevent accidental exposure.

    SecretString behaves exactly like a regular string in all operations,
    but its repr() shows '**********' instead of the actual value.
    This helps prevent secrets from being accidentally logged or displayed.

    It also provides a ``get_secret_value()`` method for backward compatibility
    with code that previously used ``pydantic.SecretStr``.

    Example:
        ```python
        api_key = SecretString("sk-secret-key")
        print(api_key)  # sk-secret-key (normal string behavior)
        print(repr(api_key))  # SecretString('**********')
        print(f"Key: {api_key}")  # Key: sk-secret-key
        print(api_key.get_secret_value())  # sk-secret-key
        ```
    """

    def __repr__(self) -> str:
        """Return a masked representation to prevent secret exposure."""
        return "SecretString('**********')"

    def get_secret_value(self) -> str:
        """Return the underlying string value.

        Provided for backward compatibility with ``pydantic.SecretStr``.
        Since SecretString *is* a str, this simply returns ``str(self)``.
        """
        return str(self)


def _coerce_value(value: str, target_type: type) -> Any:
    """Coerce a string value to the target type."""
    origin = get_origin(target_type)
    args = get_args(target_type)

    # Handle Union types (e.g., str | None) — try each non-None arm
    if origin is type(None):
        return None

    if args and type(None) in args:
        for arg in args:
            if arg is not type(None):
                with suppress(ValueError, TypeError):
                    return _coerce_value(value, arg)
        return value

    # Handle SecretString
    if target_type is SecretString or (isinstance(target_type, type) and issubclass(target_type, SecretString)):
        return SecretString(value)

    # Handle basic types
    if target_type is str:
        return value
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    if target_type is bool:
        return value.lower() in ("true", "1", "yes", "on")

    return value


def load_settings(
    settings_type: type[SettingsT],
    *,
    env_prefix: str = "",
    env_file_path: str | None = None,
    env_file_encoding: str | None = None,
    **overrides: Any,
) -> SettingsT:
    """Load settings from environment variables, a ``.env`` file, and explicit overrides.

    The *settings_type* must be a ``TypedDict`` subclass.  Values are resolved in
    this order (highest priority first):

    1. Explicit keyword *overrides* (``None`` values are filtered out).
    2. Environment variables (``<env_prefix><FIELD_NAME>``).
    3. A ``.env`` file (loaded via ``python-dotenv``; existing env vars take precedence).
    4. Default values — fields with class-level defaults on the TypedDict, or
       ``None`` for fields whose type includes ``None``.

    Fields marked ``Required`` (e.g. ``model_id: Required[str]``) or defined in
    a ``total=True`` base class are treated as required.  If no value can be
    resolved for such a field, a ``SettingNotFoundError`` is raised.

    Note:
        ``Required`` relies on the TypedDict metaclass inspecting annotations at
        class creation time.  ``from __future__ import annotations`` (PEP 563) turns
        annotations into plain strings, which prevents ``Required`` from being
        recognised — all fields will silently become optional.  Do **not** use
        ``from __future__ import annotations`` in modules that define a TypedDict
        with ``Required`` fields.  On Python 3.10+ the ``X | Y`` union syntax works
        natively, so the future import is not needed.

    Args:
        settings_type: A ``TypedDict`` class describing the settings schema.
        env_prefix: Prefix for environment variable lookup (e.g. ``"OPENAI_"``).
        env_file_path: Path to ``.env`` file.  Defaults to ``".env"`` when omitted.
        env_file_encoding: Encoding for reading the ``.env`` file.  Defaults to ``"utf-8"``.
        **overrides: Field values.  ``None`` values are ignored so that callers can
            forward optional parameters without masking env-var / default resolution.

    Returns:
        A populated dict matching *settings_type*.

    Raises:
        SettingNotFoundError: If a required field (in ``__required_keys__``)
            could not be resolved from any source.
    """
    encoding = env_file_encoding or "utf-8"

    # Load .env file if it exists (existing env vars take precedence by default)
    env_path = env_file_path or ".env"
    if os.path.isfile(env_path):
        load_dotenv(dotenv_path=env_path, encoding=encoding)

    # Filter out None overrides so defaults / env vars are preserved
    overrides = {k: v for k, v in overrides.items() if v is not None}

    # Get field type hints from the TypedDict
    hints = get_type_hints(settings_type)
    required_keys: frozenset[str] = getattr(settings_type, "__required_keys__", frozenset())

    result: dict[str, Any] = {}
    for field_name, field_type in hints.items():
        # 1. Explicit override wins
        if field_name in overrides:
            override_value = overrides[field_name]
            # Coerce plain str → SecretString if the annotation expects it
            if isinstance(override_value, str) and not isinstance(override_value, SecretString):
                with suppress(ValueError, TypeError):
                    coerced = _coerce_value(override_value, field_type)
                    if isinstance(coerced, SecretString):
                        override_value = coerced
            result[field_name] = override_value
            continue

        # 2. Environment variable
        env_var_name = f"{env_prefix}{field_name.upper()}"
        env_value = os.getenv(env_var_name)
        if env_value is not None:
            try:
                result[field_name] = _coerce_value(env_value, field_type)
            except (ValueError, TypeError):
                result[field_name] = env_value
            continue

        # 3. Default from TypedDict class-level defaults, or None for optional fields
        if hasattr(settings_type, field_name):
            result[field_name] = getattr(settings_type, field_name)
        elif field_name in required_keys:
            from .exceptions import SettingNotFoundError

            env_var_name = f"{env_prefix}{field_name.upper()}"
            raise SettingNotFoundError(
                f"Required setting '{field_name}' was not provided. "
                f"Set it via the '{field_name}' parameter or the "
                f"'{env_var_name}' environment variable."
            )
        else:
            result[field_name] = None

    return result  # type: ignore[return-value]
