# Copyright (c) Microsoft. All rights reserved.

"""Enumerations and flag helpers for Purview policy evaluation models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum, Flag, auto
from typing import TypeVar

FlagT = TypeVar("FlagT", bound=Flag)


class Activity(str, Enum):
    """High-level activity types representing user or agent operations."""

    UNKNOWN = "unknown"
    UPLOAD_TEXT = "uploadText"
    UPLOAD_FILE = "uploadFile"
    DOWNLOAD_TEXT = "downloadText"
    DOWNLOAD_FILE = "downloadFile"


class ProtectionScopeActivities(Flag):
    """Flag enumeration of activities used in policy protection scopes."""

    NONE = 0
    UPLOAD_TEXT = auto()
    UPLOAD_FILE = auto()
    DOWNLOAD_TEXT = auto()
    DOWNLOAD_FILE = auto()
    UNKNOWN_FUTURE_VALUE = auto()

    def __int__(self) -> int:  # pragma: no cover
        """Return the flag's integer representation (pydantic friendly)."""
        return self.value


# Mapping & generic helpers for flag enums
_PROTECTION_SCOPE_ACTIVITIES_MAP: dict[str, ProtectionScopeActivities] = {
    "none": ProtectionScopeActivities.NONE,
    "uploadText": ProtectionScopeActivities.UPLOAD_TEXT,
    "uploadFile": ProtectionScopeActivities.UPLOAD_FILE,
    "downloadText": ProtectionScopeActivities.DOWNLOAD_TEXT,
    "downloadFile": ProtectionScopeActivities.DOWNLOAD_FILE,
    "unknownFutureValue": ProtectionScopeActivities.UNKNOWN_FUTURE_VALUE,
}
_PROTECTION_SCOPE_ACTIVITIES_SERIALIZE_ORDER: list[tuple[str, ProtectionScopeActivities]] = [
    ("uploadText", ProtectionScopeActivities.UPLOAD_TEXT),
    ("uploadFile", ProtectionScopeActivities.UPLOAD_FILE),
    ("downloadText", ProtectionScopeActivities.DOWNLOAD_TEXT),
    ("downloadFile", ProtectionScopeActivities.DOWNLOAD_FILE),
]


def deserialize_flag(
    value: object, mapping: Mapping[str, FlagT], enum_cls: type[FlagT]
) -> FlagT | None:  # pragma: no cover
    """Deserialize arbitrary input into a flag enum instance.

    Accepts existing enum instances, integers, comma separated strings, or iterables
    of parts. Unknown parts are ignored. Returns ``None`` for unsupported input.
    """
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    # Accept int directly
    if isinstance(value, int):
        try:
            return enum_cls(value)
        except Exception:
            return None
    # Accept comma separated string or single string
    parts: list[str]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return enum_cls(0)
        parts = [p.strip() for p in value.split(",") if p.strip()]
    elif isinstance(value, (list, tuple, set)):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.extend([p.strip() for p in item.split(",") if p.strip()])
            elif isinstance(item, enum_cls):
                # accumulate and continue
                return_flag = enum_cls(0)
                return_flag |= item
        # fall through
    else:
        return None
    flag_value = enum_cls(0)
    for part in parts:
        member = mapping.get(part)
        if member is not None:
            flag_value |= member
    if flag_value == enum_cls(0) and mapping.get("none") is not None:
        return mapping["none"]  # type: ignore[index]
    return flag_value


def serialize_flag(
    flag_value: Flag | int | None, ordered_parts: Sequence[tuple[str, Flag]]
) -> str | None:  # pragma: no cover
    """Serialize a flag enum (or int) into a stable, comma-separated string."""
    if flag_value is None:
        return None
    # Convert int to Flag value for bitwise operations
    if isinstance(flag_value, int):
        if flag_value == 0:
            return "none"
        # Use int value directly for bitwise comparison
        int_parts: list[str] = []
        for name, member in ordered_parts:
            if flag_value & member.value:
                int_parts.append(name)
        if not int_parts:
            return "none"
        return ",".join(int_parts)
    # Handle Flag enum
    if not isinstance(flag_value, Flag):
        return None
    if flag_value.value == 0:
        return "none"
    parts: list[str] = []
    for name, member in ordered_parts:
        if flag_value & member:
            parts.append(name)
    if not parts:
        return "none"
    return ",".join(parts)


class DlpAction(str, Enum):
    """Data Loss Prevention (DLP) action outcomes returned by policy evaluation."""

    BLOCK_ACCESS = "blockAccess"
    OTHER = "other"


class RestrictionAction(str, Enum):
    """Restriction actions applied to content when blocked or limited."""

    BLOCK = "block"
    OTHER = "other"


class ProtectionScopeState(str, Enum):
    """State of a protection scope relative to evaluation (modified or not)."""

    NOT_MODIFIED = "notModified"
    MODIFIED = "modified"
    UNKNOWN_FUTURE_VALUE = "unknownFutureValue"


class ExecutionMode(str, Enum):
    """Whether evaluation occurs inline (synchronous) or offline (asynchronous)."""

    EVALUATE_INLINE = "evaluateInline"
    EVALUATE_OFFLINE = "evaluateOffline"
    UNKNOWN_FUTURE_VALUE = "unknownFutureValue"


class PolicyPivotProperty(str, Enum):
    """Dimension by which protection scopes can be pivoted (e.g. activity or location)."""

    NONE = "none"
    ACTIVITY = "activity"
    LOCATION = "location"
    UNKNOWN_FUTURE_VALUE = "unknownFutureValue"


def translate_activity(activity: Activity) -> ProtectionScopeActivities:
    """Map Activity enum to ProtectionScopeActivities flag value.

    Keeps UNKNOWN -> NONE for backward compatibility; unknown future values map to UNKNOWN_FUTURE_VALUE.
    """
    mapping = {
        Activity.UNKNOWN: ProtectionScopeActivities.NONE,
        Activity.UPLOAD_TEXT: ProtectionScopeActivities.UPLOAD_TEXT,
        Activity.UPLOAD_FILE: ProtectionScopeActivities.UPLOAD_FILE,
        Activity.DOWNLOAD_TEXT: ProtectionScopeActivities.DOWNLOAD_TEXT,
        Activity.DOWNLOAD_FILE: ProtectionScopeActivities.DOWNLOAD_FILE,
    }
    return mapping.get(activity, ProtectionScopeActivities.UNKNOWN_FUTURE_VALUE)
