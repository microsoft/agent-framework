# Copyright (c) Microsoft. All rights reserved.

"""Settings base class with environment variable resolution.

This module provides a base class for settings that can be loaded from environment
variables and .env files, with support for backend-aware resolution and precedence rules.
"""

import os
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, TypeVar, get_args, get_origin, get_type_hints

from pydantic import SecretStr

__all__ = ["AFSettings", "BackendConfig"]


TSettings = TypeVar("TSettings", bound="AFSettings")


@dataclass
class BackendConfig:
    """Configuration for a specific backend.

    Attributes:
        env_prefix: The environment variable prefix for this backend (e.g., "AZURE_OPENAI_").
        precedence: The precedence order for auto-detection (lower = higher priority).
        detection_fields: Fields that must have values to auto-detect this backend.
        field_env_vars: Mapping of field names to environment variable names (without prefix).
            If not specified, the field name in uppercase is used.
    """

    env_prefix: str
    precedence: int = 100
    detection_fields: "set[str]" = field(default_factory=set)  # type: ignore[assignment]
    field_env_vars: "dict[str, str]" = field(default_factory=dict)  # type: ignore[assignment]


def _parse_dotenv_file(file_path: str | Path, encoding: str = "utf-8") -> dict[str, str]:
    """Parse a .env file and return a dictionary of key-value pairs.

    This is a simple parser that handles:
    - KEY=value
    - KEY="quoted value"
    - KEY='single quoted value'
    - # comments
    - Empty lines
    - Export prefix (export KEY=value)

    Args:
        file_path: Path to the .env file.
        encoding: File encoding.

    Returns:
        Dictionary of environment variable names to values.
    """
    result: dict[str, str] = {}
    path = Path(file_path)

    if not path.exists():
        return result

    with path.open(encoding=encoding) as f:
        for line in f:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Handle export prefix
            if line.startswith("export "):
                line = line[7:].strip()

            # Find the first = sign
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            # Remove quotes if present
            if len(value) >= 2 and (
                (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))
            ):
                value = value[1:-1]

            result[key] = value

    return result


def _coerce_value(value: str, target_type: type) -> Any:
    """Coerce a string value to the target type.

    Args:
        value: The string value to coerce.
        target_type: The target type.

    Returns:
        The coerced value.

    Raises:
        ValueError: If the value cannot be coerced.
    """
    origin = get_origin(target_type)
    args = get_args(target_type)

    # Handle Union types (e.g., str | None)
    if origin is type(None):
        return None

    # Handle str | None, int | None, etc.
    if origin is not None and hasattr(origin, "__mro__") and type(None) in args:
        # This is a Union with None, try the non-None types
        for arg in args:
            if arg is not type(None):
                try:
                    return _coerce_value(value, arg)
                except (ValueError, TypeError):
                    continue
        return value

    # Handle SecretStr
    if target_type is SecretStr or (hasattr(target_type, "__mro__") and SecretStr in target_type.__mro__):
        return SecretStr(value)

    # Handle basic types
    if target_type is str:
        return value
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    if target_type is bool:
        return value.lower() in ("true", "1", "yes", "on")

    # For other types, return the string value and let pydantic handle validation
    return value


class AFSettings:
    """Base class for settings with environment variable resolution.

    This class provides a way to define settings that can be loaded from:
    1. Constructor arguments (highest priority)
    2. Environment variables
    3. .env file
    4. Default values (lowest priority)

    For simple settings without backend awareness, subclasses define fields as class
    attributes with type annotations and set `env_prefix` for the environment variable prefix.

    For backend-aware settings, subclasses also define `backend_configs` mapping backend
    names to `BackendConfig` objects, and optionally `backend_env_var` for the environment
    variable that specifies the backend.

    Example (simple settings):
        ```python
        class MySettings(AFSettings):
            env_prefix: ClassVar[str] = "MY_APP_"

            api_key: str | None = None
            timeout: int = 30
        ```

    Example (backend-aware settings):
        ```python
        class OpenAISettings(AFSettings):
            env_prefix: ClassVar[str] = "OPENAI_"
            backend_env_var: ClassVar[str] = "OPENAI_CHAT_CLIENT_BACKEND"
            field_env_vars: ClassVar[dict[str, str]] = {
                "model_id": "CHAT_MODEL_ID",  # Common field mapping
            }
            backend_configs: ClassVar[dict[str, BackendConfig]] = {
                "openai": BackendConfig(
                    env_prefix="OPENAI_",
                    precedence=1,
                    detection_fields={"api_key"},
                ),
                "azure": BackendConfig(
                    env_prefix="AZURE_OPENAI_",
                    precedence=2,
                    detection_fields={"endpoint"},
                    field_env_vars={"deployment_name": "CHAT_DEPLOYMENT_NAME"},
                ),
            }

            api_key: str | None = None
            endpoint: str | None = None
            model_id: str | None = None  # Uses OPENAI_CHAT_MODEL_ID
            deployment_name: str | None = None  # Uses AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
        ```

    Attributes:
        env_prefix: The default environment variable prefix.
        backend_env_var: Environment variable name for explicit backend selection.
        field_env_vars: Class-level mapping of field names to env var suffixes (common fields).
        backend_configs: Mapping of backend names to their configurations.
    """

    env_prefix: ClassVar[str] = ""
    backend_env_var: ClassVar[str | None] = None
    field_env_vars: ClassVar[dict[str, str]] = {}
    backend_configs: ClassVar[dict[str, BackendConfig]] = {}

    def __init__(
        self,
        *,
        backend: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize settings from environment variables and constructor arguments.

        Keyword Args:
            backend: Explicit backend selection. If not provided, auto-detection is used.
            env_file_path: Path to .env file. Defaults to ".env" if not provided.
            env_file_encoding: Encoding for .env file. Defaults to "utf-8".
            **kwargs: Field values. These take precedence over environment variables.
        """
        # Set default encoding
        encoding = env_file_encoding or "utf-8"

        # Load .env file
        dotenv_path = env_file_path or ".env"
        dotenv_vars = _parse_dotenv_file(dotenv_path, encoding)

        # Store settings metadata
        self._env_file_path = env_file_path
        self._env_file_encoding = encoding

        # Filter out None values from kwargs (matching AFBaseSettings behavior)
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        # Build combined env dict (os.environ takes precedence over dotenv)
        # This is read once and reused for both detection and field loading
        combined_env: dict[str, str] = {**dotenv_vars, **dict(os.environ)}

        # Determine the backend to use and load all field values in one pass
        resolved_backend: str | None
        field_values: dict[str, str]
        resolved_backend, field_values = self._resolve_backend(backend, combined_env, kwargs)
        self._backend: str | None = resolved_backend

        # Get field definitions from type hints for type coercion
        field_hints = self._get_field_hints()

        # Set field values with type coercion
        for field_name, field_type in field_hints.items():
            if field_name.startswith("_"):
                continue

            # kwargs take precedence
            if field_name in kwargs:
                setattr(self, field_name, kwargs[field_name])
                continue

            # Then env var values
            if field_name in field_values:
                env_value: str = field_values[field_name]
                try:
                    value = _coerce_value(env_value, field_type)
                    setattr(self, field_name, value)
                except (ValueError, TypeError):
                    setattr(self, field_name, env_value)
                continue

            # Finally, default value from class
            default_value = getattr(self.__class__, field_name, None)
            setattr(self, field_name, default_value)

    def _get_field_hints(self) -> dict[str, type]:
        """Get type hints for fields defined on this class and its bases.

        Returns:
            Dictionary mapping field names to their types.
        """
        hints: dict[str, type] = {}

        # Collect hints from all classes in MRO (excluding AFSettings and object)
        for cls in type(self).__mro__:
            if cls in (AFSettings, object):
                continue

            # get_type_hints can fail in some edge cases (e.g., forward references)
            with suppress(TypeError):
                cls_hints = get_type_hints(cls)
                for name, hint in cls_hints.items():
                    if name not in hints and not name.startswith("_"):
                        # Skip ClassVar annotations
                        origin = get_origin(hint)
                        if origin is ClassVar:
                            continue
                        hints[name] = hint

        return hints

    def _resolve_backend(
        self,
        explicit_backend: str | None,
        combined_env: dict[str, str],
        kwargs: dict[str, Any],
    ) -> tuple[str | None, dict[str, str]]:
        """Resolve backend and load all field values from environment in one pass.

        This method:
        1. Determines which backend to use
        2. Loads all field values from the combined environment dict

        Resolution order for backend:
        1. Explicit `backend` parameter
        2. Backend environment variable (e.g., OPENAI_CHAT_CLIENT_BACKEND)
        3. Auto-detection based on which backend's detection fields are satisfied,
           checking in precedence order (lower precedence number = higher priority)

        Args:
            explicit_backend: Backend provided via constructor parameter.
            combined_env: Combined dict of dotenv + os.environ (os.environ wins).
            kwargs: Constructor keyword arguments.

        Returns:
            Tuple of (resolved_backend, field_values) where field_values maps
            field names to their string values from the environment.
        """
        field_hints = self._get_field_hints()
        field_names = [f for f in field_hints if not f.startswith("_")]

        # If no backend configs defined, this is a simple settings class
        if not self.backend_configs:
            field_values = self._load_fields_for_backend(None, combined_env, field_names)
            return None, field_values

        # 1. Check explicit parameter
        if explicit_backend is not None:
            if explicit_backend not in self.backend_configs:
                valid_backends = ", ".join(sorted(self.backend_configs.keys()))
                raise ValueError(f"Invalid backend '{explicit_backend}'. Valid backends: {valid_backends}")
            field_values = self._load_fields_for_backend(explicit_backend, combined_env, field_names)
            return explicit_backend, field_values

        # 2. Check backend environment variable
        if self.backend_env_var:
            env_backend = combined_env.get(self.backend_env_var)
            if env_backend:
                if env_backend not in self.backend_configs:
                    valid_backends = ", ".join(sorted(self.backend_configs.keys()))
                    raise ValueError(
                        f"Invalid backend '{env_backend}' from {self.backend_env_var}. Valid backends: {valid_backends}"
                    )
                field_values = self._load_fields_for_backend(env_backend, combined_env, field_names)
                return env_backend, field_values

        # 3. Auto-detect by checking backends in precedence order
        # Pre-load field values for each backend and check detection fields
        sorted_backends = sorted(self.backend_configs.items(), key=lambda x: x[1].precedence)

        for backend_name, config in sorted_backends:
            field_values = self._load_fields_for_backend(backend_name, combined_env, field_names)

            # Check if any detection field has a value (from kwargs or loaded env)
            detected = False
            for detection_field in config.detection_fields:
                if detection_field in kwargs or detection_field in field_values:
                    detected = True
                    break

            if detected:
                return backend_name, field_values

        # No backend detected - load with default prefix
        field_values = self._load_fields_for_backend(None, combined_env, field_names)
        return None, field_values

    def _load_fields_for_backend(
        self,
        backend: str | None,
        combined_env: dict[str, str],
        field_names: list[str],
    ) -> dict[str, str]:
        """Load all field values from environment for a specific backend.

        Args:
            backend: The backend name, or None for default behavior.
            combined_env: Combined dict of dotenv + os.environ.
            field_names: List of field names to load.

        Returns:
            Dict mapping field names to their string values (only fields with values).
        """
        field_values: dict[str, str] = {}

        for field_name in field_names:
            env_var_name = self._get_env_var_name(field_name, backend)
            if env_var_name in combined_env:
                field_values[field_name] = combined_env[env_var_name]

        return field_values

    def _get_env_var_name(self, field_name: str, backend: str | None) -> str:
        """Get the environment variable name for a field.

        Resolution order:
        1. If backend is set, check backend's field_env_vars for backend-specific mapping
        2. Check class-level field_env_vars for common field mapping
        3. Fall back to appropriate prefix + field_name.upper()
           - Uses backend's env_prefix if backend is set
           - Uses class env_prefix otherwise

        Args:
            field_name: The field name.
            backend: The backend name, or None for default behavior.

        Returns:
            The environment variable name.
        """
        # 1. Check backend-specific mapping
        if backend and backend in self.backend_configs:
            config = self.backend_configs[backend]
            if field_name in config.field_env_vars:
                return f"{config.env_prefix}{config.field_env_vars[field_name]}"

        # 2. Check class-level common field mapping
        if field_name in self.field_env_vars:
            return f"{self.env_prefix}{self.field_env_vars[field_name]}"

        # 3. Default behavior: use backend prefix if available, else class prefix
        if backend and backend in self.backend_configs:
            prefix = self.backend_configs[backend].env_prefix
        else:
            prefix = self.env_prefix
        return f"{prefix}{field_name.upper()}"

    @property
    def backend(self) -> str | None:
        """Get the resolved backend name."""
        return self._backend

    def __repr__(self) -> str:
        """Return a string representation of the settings."""
        cls_name = self.__class__.__name__
        field_hints = self._get_field_hints()
        fields: list[str] = []
        for field_name in field_hints:
            if field_name.startswith("_"):
                continue
            value = getattr(self, field_name, None)
            # Mask secret values
            if isinstance(value, SecretStr):
                fields.append(f"{field_name}=SecretStr('**********')")
            elif value is not None:
                fields.append(f"{field_name}={value!r}")
        return f"{cls_name}({', '.join(fields)})"
