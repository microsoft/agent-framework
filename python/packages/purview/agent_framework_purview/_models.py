# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime
from enum import Enum, Flag, auto
from typing import Any, ClassVar, TypeVar, cast
from uuid import uuid4

from agent_framework._logging import get_logger
from agent_framework._serialization import SerializationMixin

logger = get_logger("agent_framework.purview")

# --------------------------------------------------------------------------------------
# Enums & flag helpers
# --------------------------------------------------------------------------------------


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
        return self.value


FlagT = TypeVar("FlagT", bound=Flag)

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
    """Deserialize arbitrary input into a flag enum instance."""
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, int):
        try:
            return enum_cls(value)
        except Exception:
            return None

    flag_value = enum_cls(0)
    parts: list[str] = []

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return enum_cls(0)
        parts.extend([p.strip() for p in raw.split(",") if p.strip()])
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, str):
                parts.extend([p.strip() for p in item.split(",") if p.strip()])
            elif isinstance(item, enum_cls):
                flag_value |= item
            elif isinstance(item, int):
                try:
                    flag_value |= enum_cls(item)
                except Exception:
                    logger.warning(f"Failed to convert int {item} to {enum_cls.__name__}")
    else:
        return None

    for part in parts:
        member = mapping.get(part)
        if member is not None:
            flag_value |= member

    if flag_value == enum_cls(0):
        none_member = mapping.get("none")
        if none_member is not None:
            return none_member  # type: ignore[return-value,index]
    return flag_value


def serialize_flag(
    flag_value: Flag | int | None, ordered_parts: Sequence[tuple[str, Flag]]
) -> str | None:  # pragma: no cover
    """Serialize a flag enum (or int) into a stable, comma-separated string."""
    if flag_value is None:
        return None
    if isinstance(flag_value, int):
        if flag_value == 0:
            return "none"
        int_parts: list[str] = []
        for name, member in ordered_parts:
            if flag_value & member.value:
                int_parts.append(name)
        return ",".join(int_parts) if int_parts else "none"
    if not isinstance(flag_value, Flag):
        return None
    if flag_value.value == 0:
        return "none"
    parts: list[str] = []
    for name, member in ordered_parts:
        if flag_value & member:
            parts.append(name)
    return ",".join(parts) if parts else "none"


class DlpAction(str, Enum):
    BLOCK_ACCESS = "blockAccess"
    OTHER = "other"


class RestrictionAction(str, Enum):
    BLOCK = "block"
    OTHER = "other"


class ProtectionScopeState(str, Enum):
    NOT_MODIFIED = "notModified"
    MODIFIED = "modified"
    UNKNOWN_FUTURE_VALUE = "unknownFutureValue"


class ExecutionMode(str, Enum):
    EVALUATE_INLINE = "evaluateInline"
    EVALUATE_OFFLINE = "evaluateOffline"
    UNKNOWN_FUTURE_VALUE = "unknownFutureValue"


class PolicyPivotProperty(str, Enum):
    NONE = "none"
    ACTIVITY = "activity"
    LOCATION = "location"
    UNKNOWN_FUTURE_VALUE = "unknownFutureValue"


def translate_activity(activity: Activity) -> ProtectionScopeActivities:
    mapping = {
        Activity.UNKNOWN: ProtectionScopeActivities.NONE,
        Activity.UPLOAD_TEXT: ProtectionScopeActivities.UPLOAD_TEXT,
        Activity.UPLOAD_FILE: ProtectionScopeActivities.UPLOAD_FILE,
        Activity.DOWNLOAD_TEXT: ProtectionScopeActivities.DOWNLOAD_TEXT,
        Activity.DOWNLOAD_FILE: ProtectionScopeActivities.DOWNLOAD_FILE,
    }
    return mapping.get(activity, ProtectionScopeActivities.UNKNOWN_FUTURE_VALUE)


# --------------------------------------------------------------------------------------
# Simple value models
# --------------------------------------------------------------------------------------

TAliasSerializable = TypeVar("TAliasSerializable", bound="_AliasSerializable")


class _AliasSerializable(SerializationMixin):
    """Base class adding alias mapping + pydantic-compat helpers.

    Each subclass can define ``_ALIASES`` mapping internal attribute name -> external serialized key.
    ``to_dict`` will emit external keys; ``from_dict`` (via ``__init__`` preprocessing) accepts either form.

    Provides light-weight compatibility helpers ``model_dump`` / ``model_validate``
    """

    _ALIASES: ClassVar[dict[str, str]] = {}

    def __init__(self, **kwargs: Any) -> None:
        # Normalize alias keys -> internal names across the entire class hierarchy
        # Collect all aliases from parent classes too
        all_aliases: dict[str, str] = {}
        for cls in type(self).__mro__:
            if hasattr(cls, "_ALIASES") and isinstance(cls._ALIASES, dict):
                for internal, external in cls._ALIASES.items():
                    if external not in all_aliases:
                        all_aliases[external] = internal

        # Normalize all aliased keys in kwargs
        for external, internal in all_aliases.items():
            if external in kwargs and internal not in kwargs:
                kwargs[internal] = kwargs.pop(external)

        # Set normalized kwargs as attributes
        # This will overwrite any None values that child __init__ may have set from default params
        for k, v in kwargs.items():
            setattr(self, k, v)

    # ------------------------------------------------------------------
    # Compatibility helpers
    # ------------------------------------------------------------------
    def model_dump(self, *, by_alias: bool = True, exclude_none: bool = True, **_: Any) -> dict[str, Any]:
        # Use self.to_dict() to get alias translation
        d = self.to_dict(exclude_none=exclude_none)
        # If by_alias=False, translate external -> internal (rarely needed; default True)
        if not by_alias and self._ALIASES:
            reverse = {v: k for k, v in self._ALIASES.items()}
            translated: dict[str, Any] = {}
            for k, v in d.items():
                translated[reverse.get(k, k)] = v
            return translated
        return d

    def model_dump_json(self, *, by_alias: bool = True, exclude_none: bool = True, **kwargs: Any) -> str:
        import json

        return json.dumps(self.model_dump(by_alias=by_alias, exclude_none=exclude_none, **kwargs))

    @classmethod
    def model_validate(cls: type[TAliasSerializable], value: MutableMapping[str, Any]) -> TAliasSerializable:  # type: ignore[name-defined]
        return cls(**value)

    # ------------------------------------------------------------------
    # Override to handle alias emission
    # ------------------------------------------------------------------
    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:  # type: ignore[override]
        base = SerializationMixin.to_dict(self, exclude=exclude, exclude_none=exclude_none)

        # For Graph API models, remove the auto-generated 'type' field if it's in DEFAULT_EXCLUDE
        if "type" in self.DEFAULT_EXCLUDE:
            base.pop("type", None)

        # Collect all aliases from class hierarchy
        all_aliases: dict[str, str] = {}
        for cls in type(self).__mro__:
            if hasattr(cls, "_ALIASES") and isinstance(cls._ALIASES, dict):
                # Parent aliases first (will be overridden by child if same key)
                for internal, external in cls._ALIASES.items():
                    if internal not in all_aliases:
                        all_aliases[internal] = external

        if not all_aliases:
            return base

        # Translate internal -> external keys (except 'type' reserved)
        translated: dict[str, Any] = {}
        for k, v in base.items():
            if k == "type":
                translated[k] = v
                continue
            external = all_aliases.get(k, k)
            translated[external] = v
        return translated


class PolicyLocation(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {"data_type": "@odata.type"}
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"type"}  # Exclude auto-generated type field for Graph API

    def __init__(self, data_type: str | None = None, value: str | None = None, **kwargs: Any) -> None:
        # Extract aliased values from kwargs
        if "@odata.type" in kwargs:
            data_type = kwargs["@odata.type"]

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.data_type = data_type
        self.value = value


class ActivityMetadata(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {"activity": "activity"}

    def __init__(self, activity: Activity, **kwargs: Any) -> None:
        super().__init__(activity=activity, **kwargs)
        self.activity = activity


class OperatingSystemSpecifications(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {
        "operating_system_platform": "operatingSystemPlatform",
        "operating_system_version": "operatingSystemVersion",
    }

    def __init__(
        self,
        operating_system_platform: str | None = None,
        operating_system_version: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "operatingSystemPlatform" in kwargs:
            operating_system_platform = kwargs["operatingSystemPlatform"]
        if "operatingSystemVersion" in kwargs:
            operating_system_version = kwargs["operatingSystemVersion"]

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.operating_system_platform = operating_system_platform
        self.operating_system_version = operating_system_version


class DeviceMetadata(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {
        "ip_address": "ipAddress",
        "operating_system_specifications": "operatingSystemSpecifications",
    }

    def __init__(
        self,
        ip_address: str | None = None,
        operating_system_specifications: OperatingSystemSpecifications | MutableMapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "ipAddress" in kwargs:
            ip_address = kwargs["ipAddress"]
        if "operatingSystemSpecifications" in kwargs:
            operating_system_specifications = kwargs["operatingSystemSpecifications"]

        # Convert nested objects
        if isinstance(operating_system_specifications, MutableMapping):
            operating_system_specifications = OperatingSystemSpecifications(**operating_system_specifications)

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.ip_address = ip_address
        self.operating_system_specifications = operating_system_specifications


class IntegratedAppMetadata(_AliasSerializable):
    def __init__(self, name: str | None = None, version: str | None = None, **kwargs: Any) -> None:
        super().__init__(name=name, version=version, **kwargs)
        self.name = name
        self.version = version


class ProtectedAppMetadata(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {"application_location": "applicationLocation"}

    def __init__(
        self,
        name: str | None = None,
        version: str | None = None,
        application_location: PolicyLocation | MutableMapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "applicationLocation" in kwargs:
            application_location = kwargs["applicationLocation"]

        # Convert nested objects
        if isinstance(application_location, MutableMapping):
            application_location = PolicyLocation(**application_location)

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.name = name
        self.version = version
        self.application_location = application_location  # type: ignore[assignment]


class DlpActionInfo(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {"restriction_action": "restrictionAction"}

    def __init__(
        self,
        action: DlpAction | None = None,
        restriction_action: RestrictionAction | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "restrictionAction" in kwargs:
            restriction_action = kwargs["restrictionAction"]

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.action = action
        self.restriction_action = restriction_action


class AccessedResourceDetails(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {
        "label_id": "labelId",
        "access_type": "accessType",
        "is_cross_prompt_injection_detected": "isCrossPromptInjectionDetected",
    }

    def __init__(
        self,
        identifier: str | None = None,
        name: str | None = None,
        url: str | None = None,
        label_id: str | None = None,
        access_type: str | None = None,
        status: str | None = None,
        is_cross_prompt_injection_detected: bool | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "labelId" in kwargs:
            label_id = kwargs["labelId"]
        if "accessType" in kwargs:
            access_type = kwargs["accessType"]
        if "isCrossPromptInjectionDetected" in kwargs:
            is_cross_prompt_injection_detected = kwargs["isCrossPromptInjectionDetected"]

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.identifier = identifier
        self.name = name
        self.url = url
        self.label_id = label_id
        self.access_type = access_type
        self.status = status
        self.is_cross_prompt_injection_detected = is_cross_prompt_injection_detected


class AiInteractionPlugin(_AliasSerializable):
    def __init__(
        self,
        identifier: str | None = None,
        name: str | None = None,
        version: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(identifier=identifier, name=name, version=version, **kwargs)
        self.identifier = identifier
        self.name = name
        self.version = version


class AiAgentInfo(_AliasSerializable):
    def __init__(
        self,
        identifier: str | None = None,
        name: str | None = None,
        version: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(identifier=identifier, name=name, version=version, **kwargs)
        self.identifier = identifier
        self.name = name
        self.version = version


# --------------------------------------------------------------------------------------
# Content models
# --------------------------------------------------------------------------------------


class GraphDataTypeBase(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {"data_type": "@odata.type"}
    # Exclude the auto-generated 'type' field - Graph API uses @odata.type instead
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"type"}

    def __init__(self, data_type: str, **kwargs: Any) -> None:
        super().__init__(data_type=data_type, **kwargs)
        self.data_type = data_type


class ContentBase(GraphDataTypeBase):
    pass


class PurviewTextContent(ContentBase):
    def __init__(self, data: str, data_type: str = "microsoft.graph.textContent", **kwargs: Any) -> None:
        super().__init__(data_type=data_type, **kwargs)
        self.data = data


class PurviewBinaryContent(ContentBase):
    def __init__(self, data: bytes, data_type: str = "microsoft.graph.binaryContent", **kwargs: Any) -> None:
        super().__init__(data_type=data_type, **kwargs)
        self.data = data

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:  # type: ignore[override]
        import base64

        base = super().to_dict(exclude=exclude, exclude_none=exclude_none)
        # Ensure bytes encoded as base64 string like pydantic
        data_bytes = getattr(self, "data", b"") or b""
        base["data"] = base64.b64encode(data_bytes).decode("utf-8")
        return base


class ProcessConversationMetadata(GraphDataTypeBase):
    _ALIASES: ClassVar[dict[str, str]] = {
        "correlation_id": "correlationId",
        "sequence_number": "sequenceNumber",
        "is_truncated": "isTruncated",
        "created_date_time": "createdDateTime",
        "modified_date_time": "modifiedDateTime",
        "parent_message_id": "parentMessageId",
        "accessed_resources": "accessedResources_v2",
    }

    def __init__(
        self,
        identifier: str | None = None,
        content: PurviewTextContent | PurviewBinaryContent | ContentBase | MutableMapping[str, Any] | None = None,
        name: str | None = None,
        is_truncated: bool | None = None,
        data_type: str = "microsoft.graph.processConversationMetadata",  # emitted via base
        correlation_id: str | None = None,
        sequence_number: int | None = None,
        length: int | None = None,
        created_date_time: datetime | None = None,
        modified_date_time: datetime | None = None,
        parent_message_id: str | None = None,
        accessed_resources: list[AccessedResourceDetails | MutableMapping[str, Any]] | None = None,
        plugins: list[AiInteractionPlugin | MutableMapping[str, Any]] | None = None,
        agents: list[AiAgentInfo | MutableMapping[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "correlationId" in kwargs:
            correlation_id = kwargs["correlationId"]
        if "sequenceNumber" in kwargs:
            sequence_number = kwargs["sequenceNumber"]
        if "isTruncated" in kwargs:
            is_truncated = kwargs["isTruncated"]
        if "createdDateTime" in kwargs:
            created_date_time = kwargs["createdDateTime"]
        if "modifiedDateTime" in kwargs:
            modified_date_time = kwargs["modifiedDateTime"]
        if "parentMessageId" in kwargs:
            parent_message_id = kwargs["parentMessageId"]
        if "accessedResources_v2" in kwargs:
            accessed_resources = kwargs["accessedResources_v2"]

        # Convert nested objects
        if isinstance(content, MutableMapping):
            # determine by type? fall back to text content
            c_type = content.get("@odata.type") or content.get("data_type")
            if c_type and "binary" in str(c_type):
                content = PurviewBinaryContent(**content)  # type: ignore[arg-type]
            else:
                content = PurviewTextContent(**content)  # type: ignore[arg-type]
        accessed_list: list[AccessedResourceDetails] | None = None
        if accessed_resources:
            accessed_list = [
                ar if isinstance(ar, AccessedResourceDetails) else AccessedResourceDetails(**ar)
                for ar in accessed_resources
            ]
        plugin_list: list[AiInteractionPlugin] | None = None
        if plugins:
            plugin_list = [p if isinstance(p, AiInteractionPlugin) else AiInteractionPlugin(**p) for p in plugins]
        agent_list: list[AiAgentInfo] | None = None
        if agents:
            agent_list = [a if isinstance(a, AiAgentInfo) else AiAgentInfo(**a) for a in agents]

        # Call parent without explicit params with aliases
        super().__init__(data_type=data_type, **kwargs)
        self.identifier = identifier
        self.content = content  # type: ignore[assignment]
        self.name = name
        self.correlation_id = correlation_id
        self.sequence_number = sequence_number
        self.length = length
        self.is_truncated = is_truncated
        self.created_date_time = created_date_time
        self.modified_date_time = modified_date_time
        self.parent_message_id = parent_message_id
        self.accessed_resources = accessed_list
        self.plugins = plugin_list
        self.agents = agent_list


class ContentToProcess(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {
        "content_entries": "contentEntries",
        "activity_metadata": "activityMetadata",
        "device_metadata": "deviceMetadata",
        "integrated_app_metadata": "integratedAppMetadata",
        "protected_app_metadata": "protectedAppMetadata",
    }

    def __init__(
        self,
        content_entries: list[ProcessConversationMetadata | MutableMapping[str, Any]],
        activity_metadata: ActivityMetadata | MutableMapping[str, Any],
        device_metadata: DeviceMetadata | MutableMapping[str, Any],
        integrated_app_metadata: IntegratedAppMetadata | MutableMapping[str, Any],
        protected_app_metadata: ProtectedAppMetadata | MutableMapping[str, Any],
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "contentEntries" in kwargs:
            content_entries = kwargs["contentEntries"]
        if "activityMetadata" in kwargs:
            activity_metadata = kwargs["activityMetadata"]
        if "deviceMetadata" in kwargs:
            device_metadata = kwargs["deviceMetadata"]
        if "integratedAppMetadata" in kwargs:
            integrated_app_metadata = kwargs["integratedAppMetadata"]
        if "protectedAppMetadata" in kwargs:
            protected_app_metadata = kwargs["protectedAppMetadata"]

        # Convert nested objects
        entries = [
            e if isinstance(e, ProcessConversationMetadata) else ProcessConversationMetadata(**e)
            for e in content_entries
        ]
        if isinstance(activity_metadata, MutableMapping):
            activity_metadata = ActivityMetadata(**activity_metadata)
        if isinstance(device_metadata, MutableMapping):
            device_metadata = DeviceMetadata(**device_metadata)
        if isinstance(integrated_app_metadata, MutableMapping):
            integrated_app_metadata = IntegratedAppMetadata(**integrated_app_metadata)
        if isinstance(protected_app_metadata, MutableMapping):
            protected_app_metadata = ProtectedAppMetadata(**protected_app_metadata)

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.content_entries = entries
        self.activity_metadata = activity_metadata  # type: ignore[assignment]
        self.device_metadata = device_metadata  # type: ignore[assignment]
        self.integrated_app_metadata = integrated_app_metadata  # type: ignore[assignment]
        self.protected_app_metadata = protected_app_metadata  # type: ignore[assignment]


# --------------------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------------------


class ProcessContentRequest(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {"content_to_process": "contentToProcess"}
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {
        "correlation_id",
    }

    def __init__(
        self,
        content_to_process: ContentToProcess | MutableMapping[str, Any],
        user_id: str,
        tenant_id: str,
        correlation_id: str | None = None,
        process_inline: bool | None = None,
        scope_identifier: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "contentToProcess" in kwargs:
            content_to_process = kwargs["contentToProcess"]

        # Convert nested objects
        if isinstance(content_to_process, MutableMapping):
            content_to_process = ContentToProcess(**content_to_process)

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.content_to_process = content_to_process  # type: ignore[assignment]
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.correlation_id = correlation_id
        self.process_inline = process_inline
        self.scope_identifier = scope_identifier


class ProtectionScopesRequest(_AliasSerializable):
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"correlation_id"}
    _ALIASES: ClassVar[dict[str, str]] = {
        "pivot_on": "pivotOn",
        "device_metadata": "deviceMetadata",
        "integrated_app_metadata": "integratedAppMetadata",
    }

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        activities: ProtectionScopeActivities | str | int | Sequence[str] | None = None,
        locations: list[PolicyLocation | MutableMapping[str, Any]] | None = None,
        pivot_on: PolicyPivotProperty | None = None,
        device_metadata: DeviceMetadata | MutableMapping[str, Any] | None = None,
        integrated_app_metadata: IntegratedAppMetadata | MutableMapping[str, Any] | None = None,
        correlation_id: str | None = None,
        scope_identifier: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "pivotOn" in kwargs:
            pivot_on = kwargs["pivotOn"]
        if "deviceMetadata" in kwargs:
            device_metadata = kwargs["deviceMetadata"]
        if "integratedAppMetadata" in kwargs:
            integrated_app_metadata = kwargs["integratedAppMetadata"]

        # Deserialize activities flag
        if not isinstance(activities, ProtectionScopeActivities) and activities is not None:
            activities = deserialize_flag(activities, _PROTECTION_SCOPE_ACTIVITIES_MAP, ProtectionScopeActivities)

        # Convert nested objects
        if locations:
            locations = [loc if isinstance(loc, PolicyLocation) else PolicyLocation(**loc) for loc in locations]
        if isinstance(device_metadata, MutableMapping):
            device_metadata = DeviceMetadata(**device_metadata)
        if isinstance(integrated_app_metadata, MutableMapping):
            integrated_app_metadata = IntegratedAppMetadata(**integrated_app_metadata)

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.activities = activities  # type: ignore[assignment]
        self.locations = locations
        self.pivot_on = pivot_on
        self.device_metadata = device_metadata
        self.integrated_app_metadata = integrated_app_metadata
        self.correlation_id = correlation_id
        self.scope_identifier = scope_identifier

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:  # type: ignore[override]
        # Get base dict (activities will be missing because Flag isn't JSON-serializable)
        base = super().to_dict(exclude=exclude, exclude_none=exclude_none)

        # Manually serialize activities flag if present and not excluded
        if self.activities is not None or not exclude_none:
            if self.activities is not None:
                base["activities"] = serialize_flag(self.activities, _PROTECTION_SCOPE_ACTIVITIES_SERIALIZE_ORDER)
            elif not exclude_none:
                base["activities"] = None

        return base


class ContentActivitiesRequest(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {
        "user_id": "userId",
        "scope_identifier": "scopeIdentifier",
        "content_to_process": "contentMetadata",
    }
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"correlation_id"}

    def __init__(
        self,
        user_id: str,
        content_to_process: ContentToProcess | MutableMapping[str, Any],
        tenant_id: str,
        id: str | None = None,
        scope_identifier: str | None = None,
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "userId" in kwargs:
            user_id = kwargs["userId"]
        if "scopeIdentifier" in kwargs:
            scope_identifier = kwargs["scopeIdentifier"]
        if "contentMetadata" in kwargs:
            content_to_process = kwargs["contentMetadata"]

        # Convert nested objects
        if isinstance(content_to_process, MutableMapping):
            content_to_process = ContentToProcess(**content_to_process)

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.id = id or str(uuid4())
        self.user_id = user_id
        self.content_to_process = content_to_process  # type: ignore[assignment]
        self.tenant_id = tenant_id
        self.scope_identifier = scope_identifier
        self.correlation_id = correlation_id


# --------------------------------------------------------------------------------------
# Response models
# --------------------------------------------------------------------------------------


class ErrorDetails(_AliasSerializable):
    def __init__(self, code: str | None = None, message: str | None = None, **kwargs: Any) -> None:
        super().__init__(code=code, message=message, **kwargs)
        self.code = code
        self.message = message


class ProcessingError(_AliasSerializable):
    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        super().__init__(message=message, **kwargs)
        self.message = message


class ProcessContentResponse(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {
        "protection_scope_state": "protectionScopeState",
        "policy_actions": "policyActions",
        "processing_errors": "processingErrors",
        "correlation_id": "correlationId",
    }
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"correlation_id"}

    id: str | None
    protection_scope_state: ProtectionScopeState | None
    policy_actions: list[DlpActionInfo] | None
    processing_errors: list[ProcessingError] | None
    correlation_id: str | None

    def __init__(
        self,
        id: str | None = None,
        protection_scope_state: ProtectionScopeState | None = None,
        policy_actions: list[DlpActionInfo | MutableMapping[str, Any]] | None = None,
        processing_errors: list[ProcessingError | MutableMapping[str, Any]] | None = None,
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "protectionScopeState" in kwargs:
            protection_scope_state = kwargs["protectionScopeState"]
        if "policyActions" in kwargs:
            policy_actions = kwargs["policyActions"]
        if "processingErrors" in kwargs:
            processing_errors = kwargs["processingErrors"]
        if "correlationId" in kwargs:
            correlation_id = kwargs["correlationId"]

        # Convert to objects
        converted_policy_actions: list[DlpActionInfo] | None = None
        if policy_actions is not None:
            converted_policy_actions = cast(
                list[DlpActionInfo],
                [p if isinstance(p, DlpActionInfo) else DlpActionInfo(**p) for p in policy_actions],
            )

        converted_processing_errors: list[ProcessingError] | None = None
        if processing_errors is not None:
            converted_processing_errors = cast(
                list[ProcessingError],
                [pe if isinstance(pe, ProcessingError) else ProcessingError(**pe) for pe in processing_errors],
            )

        super().__init__(**kwargs)
        self.id = id
        self.protection_scope_state = protection_scope_state
        self.policy_actions = converted_policy_actions
        self.processing_errors = converted_processing_errors
        self.correlation_id = correlation_id


class PolicyScope(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {"policy_actions": "policyActions", "execution_mode": "executionMode"}

    activities: ProtectionScopeActivities | None
    locations: list[PolicyLocation] | None
    policy_actions: list[DlpActionInfo] | None
    execution_mode: ExecutionMode | None

    def __init__(
        self,
        activities: ProtectionScopeActivities | str | int | Sequence[str] | None = None,
        locations: list[PolicyLocation | MutableMapping[str, Any]] | None = None,
        policy_actions: list[DlpActionInfo | MutableMapping[str, Any]] | None = None,
        execution_mode: ExecutionMode | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs
        if "policyActions" in kwargs:
            policy_actions = kwargs["policyActions"]
        if "executionMode" in kwargs:
            execution_mode = kwargs["executionMode"]

        # Deserialize activities flag
        if not isinstance(activities, ProtectionScopeActivities) and activities is not None:
            activities = deserialize_flag(activities, _PROTECTION_SCOPE_ACTIVITIES_MAP, ProtectionScopeActivities)

        # Convert nested objects
        converted_locations: list[PolicyLocation] | None = None
        if locations is not None:
            converted_locations = cast(
                list[PolicyLocation],
                [loc if isinstance(loc, PolicyLocation) else PolicyLocation(**loc) for loc in locations],
            )

        converted_policy_actions: list[DlpActionInfo] | None = None
        if policy_actions is not None:
            converted_policy_actions = cast(
                list[DlpActionInfo],
                [p if isinstance(p, DlpActionInfo) else DlpActionInfo(**p) for p in policy_actions],
            )

        # Call parent without explicit params with aliases
        super().__init__(**kwargs)
        self.activities = activities  # type: ignore[assignment]
        self.locations = converted_locations
        self.policy_actions = converted_policy_actions
        self.execution_mode = execution_mode

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:  # type: ignore[override]
        # Get base dict (activities will be missing because Flag isn't JSON-serializable)
        base = super().to_dict(exclude=exclude, exclude_none=exclude_none)

        # Manually serialize activities flag if present and not excluded
        if self.activities is not None or not exclude_none:
            if self.activities is not None:
                base["activities"] = serialize_flag(self.activities, _PROTECTION_SCOPE_ACTIVITIES_SERIALIZE_ORDER)
            elif not exclude_none:
                base["activities"] = None

        return base


class ProtectionScopesResponse(_AliasSerializable):
    _ALIASES: ClassVar[dict[str, str]] = {
        "scope_identifier": "scopeIdentifier",
        "scopes": "value",
        "correlation_id": "correlationId",
    }
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"correlation_id"}

    scope_identifier: str | None
    scopes: list[PolicyScope] | None
    correlation_id: str | None

    def __init__(
        self,
        scope_identifier: str | None = None,
        scopes: list[PolicyScope | MutableMapping[str, Any]] | None = None,
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Extract aliased values from kwargs before they're normalized by parent
        if "scopeIdentifier" in kwargs:
            scope_identifier = kwargs["scopeIdentifier"]
        if "value" in kwargs:
            scopes = kwargs["value"]
        if "correlationId" in kwargs:
            correlation_id = kwargs["correlationId"]

        converted_scopes: list[PolicyScope] | None = None
        if scopes is not None:
            converted_scopes = cast(
                list[PolicyScope], [s if isinstance(s, PolicyScope) else PolicyScope(**s) for s in scopes]
            )

        # Don't pass parameters that have aliases - let parent normalize them
        super().__init__(**kwargs)
        self.scope_identifier = scope_identifier
        self.scopes = converted_scopes
        self.correlation_id = correlation_id


class ContentActivitiesResponse(_AliasSerializable):
    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"correlation_id"}
    _ALIASES: ClassVar[dict[str, str]] = {"correlation_id": "correlationId"}

    status_code: int | None
    error: ErrorDetails | None
    correlation_id: str | None

    def __init__(
        self,
        status_code: int | None = None,
        error: ErrorDetails | MutableMapping[str, Any] | None = None,
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        if "correlationId" in kwargs:
            correlation_id = kwargs["correlationId"]
        if isinstance(error, MutableMapping):
            error = ErrorDetails(**error)
        super().__init__(status_code=status_code, error=error, correlation_id=correlation_id, **kwargs)
        self.status_code = status_code
        self.error = error  # type: ignore[assignment]
        self.correlation_id = correlation_id


__all__ = [
    "AccessedResourceDetails",
    "Activity",
    "ActivityMetadata",
    "AiAgentInfo",
    "AiInteractionPlugin",
    "ContentActivitiesRequest",
    "ContentActivitiesResponse",
    "ContentBase",
    "ContentToProcess",
    "DeviceMetadata",
    "DlpAction",
    "DlpActionInfo",
    "ExecutionMode",
    "GraphDataTypeBase",
    "IntegratedAppMetadata",
    "OperatingSystemSpecifications",
    "PolicyLocation",
    "PolicyPivotProperty",
    "PolicyScope",
    "ProcessContentRequest",
    "ProcessContentResponse",
    "ProcessConversationMetadata",
    "ProcessingError",
    "ProtectedAppMetadata",
    "ProtectionScopeActivities",
    "ProtectionScopeState",
    "ProtectionScopesRequest",
    "ProtectionScopesResponse",
    "PurviewBinaryContent",
    "PurviewTextContent",
    "RestrictionAction",
    "deserialize_flag",
    "serialize_flag",
    "translate_activity",
]
