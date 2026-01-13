# Copyright (c) Microsoft. All rights reserved.
import os
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any, Literal, TypeVar, Union

from agent_framework import get_logger
from agent_framework._serialization import SerializationMixin

try:
    from powerfx import Engine

    engine: Engine | None = Engine()
except (ImportError, RuntimeError):
    # ImportError: powerfx package not installed
    # RuntimeError: .NET runtime not available or misconfigured
    engine = None

from typing import overload

logger = get_logger("agent_framework.declarative")

# Context variable for safe_mode setting.
# When True (default), environment variables are NOT accessible in PowerFx expressions.
# When False, environment variables CAN be accessed via Env symbol in PowerFx.
_safe_mode_context: ContextVar[bool] = ContextVar("safe_mode", default=True)


@overload
def _try_powerfx_eval(value: None, log_value: bool = True) -> None: ...


@overload
def _try_powerfx_eval(value: str, log_value: bool = True) -> str: ...


def _try_powerfx_eval(value: str | None, log_value: bool = True) -> str | None:
    """Check if a value refers to a environment variable and parse it if so.

    Args:
        value: The value to check.
        log_value: Whether to log the full value on error or just a snippet.
    """
    if value is None:
        return value
    if not value.startswith("="):
        return value
    if engine is None:
        logger.warning(
            "PowerFx engine not available for evaluating values starting with '='. "
            "Ensure you are on python 3.13 or less and have the powerfx package installed. "
            "Otherwise replace all powerfx statements in your yaml with strings."
        )
        return value
    try:
        safe_mode = _safe_mode_context.get()
        if safe_mode:
            return engine.eval(value[1:])
        return engine.eval(value[1:], symbols={"Env": dict(os.environ)})
    except Exception as exc:
        if log_value:
            logger.debug(f"PowerFx evaluation failed for value '{value}': {exc}")
        else:
            logger.debug(f"PowerFx evaluation failed for value (first five characters shown) '{value[:5]}': {exc}")
        return value


class Binding(SerializationMixin):
    """Object representing a tool argument binding."""

    def __init__(
        self,
        name: str | None = None,
        input: str | None = None,
    ) -> None:
        self.name = _try_powerfx_eval(name)
        self.input = _try_powerfx_eval(input)


class Property(SerializationMixin):
    """Object representing a property in a schema."""

    def __init__(
        self,
        name: str | None = None,
        kind: str | None = None,
        description: str | None = None,
        required: bool | None = None,
        default: Any | None = None,
        example: Any | None = None,
        enum: list[Any] | None = None,
    ) -> None:
        self.name = _try_powerfx_eval(name)
        self.kind = _try_powerfx_eval(kind)
        self.description = _try_powerfx_eval(description)
        self.required = required
        self.default = default
        self.example = example
        self.enum = enum or []

    @classmethod
    def from_dict(
        cls, value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> "Property":
        """Create a Property instance from a dictionary, dispatching to the appropriate subclass."""
        # Only dispatch if we're being called on the base Property class
        if cls is not Property:
            # We're being called on a subclass, use the normal from_dict
            return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]

        # Filter out 'type' (if it exists) field which is not a Property parameter
        value.pop("type", None)
        kind = value.get("kind", "")
        if kind == "array":
            return ArrayProperty.from_dict(value, dependencies=dependencies)
        if kind == "object":
            return ObjectProperty.from_dict(value, dependencies=dependencies)
        # Default to Property for kind="property" or empty
        return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]


class ArrayProperty(Property):
    """Object representing an array property."""

    def __init__(
        self,
        name: str | None = None,
        kind: str = "array",
        description: str | None = None,
        required: bool | None = None,
        default: Any | None = None,
        example: Any | None = None,
        enum: list[Any] | None = None,
        items: Property | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            required=required,
            default=default,
            example=example,
            enum=enum,
        )
        if not isinstance(items, Property) and items is not None:
            items = Property.from_dict(items)
        self.items = items


class ObjectProperty(Property):
    """Object representing an object property."""

    def __init__(
        self,
        name: str | None = None,
        kind: str = "object",
        description: str | None = None,
        required: bool | None = None,
        default: Any | None = None,
        example: Any | None = None,
        enum: list[Any] | None = None,
        properties: list[Property] | dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            required=required,
            default=default,
            example=example,
            enum=enum,
        )
        converted_properties: list[Property] = []
        if isinstance(properties, list):
            for prop in properties:
                if not isinstance(prop, Property):
                    prop = Property.from_dict(prop)
                converted_properties.append(prop)
        elif isinstance(properties, dict):
            for k, v in properties.items():
                temp_prop = {"name": k, **v}
                prop = Property.from_dict(temp_prop)
                converted_properties.append(prop)
        self.properties = converted_properties


class PropertySchema(SerializationMixin):
    """Object representing a property schema."""

    def __init__(
        self,
        examples: list[dict[str, Any]] | None = None,
        strict: bool = False,
        properties: list[Property] | dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.examples = examples or []
        self.strict = strict
        converted_properties: list[Property] = []
        if isinstance(properties, list):
            for prop in properties:
                if not isinstance(prop, Property):
                    prop = Property.from_dict(prop)
                converted_properties.append(prop)
        elif isinstance(properties, dict):
            for k, v in properties.items():
                temp_prop = {"name": k, **v}
                prop = Property.from_dict(temp_prop)
                converted_properties.append(prop)
        self.properties = converted_properties

    @classmethod
    def from_dict(
        cls, value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> "PropertySchema":
        """Create a PropertySchema instance from a dictionary, filtering out 'kind' field."""
        # Filter out 'kind', 'type', 'name', and 'description' fields that may appear in YAML
        # but aren't PropertySchema params
        kwargs = {k: v for k, v in value.items() if k not in ("type", "kind", "name", "description")}
        return SerializationMixin.from_dict.__func__(cls, kwargs, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]

    def to_json_schema(self) -> dict[str, Any]:
        """Get a schema out of this PropertySchema to create pydantic models."""
        json_schema = self.to_dict(exclude={"type"}, exclude_none=True)
        new_props = {}
        for prop in json_schema.get("properties", []):
            prop_name = prop.pop("name")
            prop["type"] = prop.pop("kind", None)
            new_props[prop_name] = prop
        json_schema["properties"] = new_props
        return json_schema


TConnection = TypeVar("TConnection", bound="Connection")


class Connection(SerializationMixin):
    """Object representing a connection specification."""

    def __init__(
        self,
        kind: Literal["reference", "remote", "key", "anonymous"],
        authenticationMode: str | None = None,
        usageDescription: str | None = None,
    ) -> None:
        self.kind = kind
        self.authenticationMode = _try_powerfx_eval(authenticationMode)
        self.usageDescription = _try_powerfx_eval(usageDescription)

    @classmethod
    def from_dict(
        cls: type[TConnection],
        value: MutableMapping[str, Any],
        /,
        *,
        dependencies: MutableMapping[str, Any] | None = None,
    ) -> TConnection:
        """Create a Connection instance from a dictionary, dispatching to the appropriate subclass."""
        # Only dispatch if we're being called on the base Connection class
        if cls is not Connection:
            # We're being called on a subclass, use the normal from_dict
            return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]

        kind = value.get("kind", "").lower()
        if kind == "reference":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                ReferenceConnection, value, dependencies=dependencies
            )
        if kind == "remote":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                RemoteConnection, value, dependencies=dependencies
            )
        if kind in ("key", "apikey"):
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                ApiKeyConnection, value, dependencies=dependencies
            )
        if kind == "anonymous":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                AnonymousConnection, value, dependencies=dependencies
            )
        return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]


class ReferenceConnection(Connection):
    """Object representing a reference connection."""

    def __init__(
        self,
        kind: Literal["reference"] = "reference",
        authenticationMode: str | None = None,
        usageDescription: str | None = None,
        name: str | None = None,
        target: str | None = None,
    ) -> None:
        super().__init__(
            kind=kind,
            authenticationMode=authenticationMode,
            usageDescription=usageDescription,
        )
        self.name = _try_powerfx_eval(name)
        self.target = _try_powerfx_eval(target)


class RemoteConnection(Connection):
    """Object representing a remote connection."""

    def __init__(
        self,
        kind: Literal["remote"] = "remote",
        authenticationMode: str | None = None,
        usageDescription: str | None = None,
        name: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(
            kind=kind,
            authenticationMode=authenticationMode,
            usageDescription=usageDescription,
        )
        self.name = _try_powerfx_eval(name)
        self.endpoint = _try_powerfx_eval(endpoint)


class ApiKeyConnection(Connection):
    """Object representing an API key connection."""

    def __init__(
        self,
        kind: Literal["key"] = "key",
        authenticationMode: str | None = None,
        usageDescription: str | None = None,
        endpoint: str | None = None,
        apiKey: str | None = None,
        key: str | None = None,
    ) -> None:
        super().__init__(
            kind=kind,
            authenticationMode=authenticationMode,
            usageDescription=usageDescription,
        )
        self.endpoint = _try_powerfx_eval(endpoint)
        # Support both 'apiKey' and 'key' fields, with 'key' taking precedence if both are provided
        self.apiKey = _try_powerfx_eval(key if key else apiKey, False)


class AnonymousConnection(Connection):
    """Object representing an anonymous connection."""

    def __init__(
        self,
        kind: Literal["anonymous"] = "anonymous",
        authenticationMode: str | None = None,
        usageDescription: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(
            kind=kind,
            authenticationMode=authenticationMode,
            usageDescription=usageDescription,
        )
        self.endpoint = _try_powerfx_eval(endpoint)


Connections = Union[
    ReferenceConnection,
    RemoteConnection,
    ApiKeyConnection,
    AnonymousConnection,
]


class ModelOptions(SerializationMixin):
    """Object representing model options."""

    def __init__(
        self,
        frequencyPenalty: float | None = None,
        maxOutputTokens: int | None = None,
        presencePenalty: float | None = None,
        seed: int | None = None,
        temperature: float | None = None,
        topK: int | None = None,
        topP: float | None = None,
        stopSequences: list[str] | None = None,
        allowMultipleToolCalls: bool | None = None,
        additionalProperties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.frequencyPenalty = frequencyPenalty
        self.maxOutputTokens = maxOutputTokens
        self.presencePenalty = presencePenalty
        self.seed = seed
        self.temperature = temperature
        self.topK = topK
        self.topP = topP
        self.stopSequences = stopSequences or []
        self.allowMultipleToolCalls = allowMultipleToolCalls
        # Merge any additional properties from kwargs into additionalProperties
        self.additionalProperties = additionalProperties or {}
        self.additionalProperties.update(kwargs)


class Model(SerializationMixin):
    """Object representing a model specification."""

    def __init__(
        self,
        id: str | None = None,
        provider: str | None = None,
        apiType: str | None = None,
        connection: Connections | None = None,
        options: ModelOptions | None = None,
    ) -> None:
        self.id = _try_powerfx_eval(id)
        self.provider = _try_powerfx_eval(provider)
        self.apiType = _try_powerfx_eval(apiType)
        if not isinstance(connection, Connection) and connection is not None:
            connection = Connection.from_dict(connection)
        self.connection = connection
        if not isinstance(options, ModelOptions) and options is not None:
            options = ModelOptions.from_dict(options)
        self.options = options


class Format(SerializationMixin):
    """Object representing template format."""

    def __init__(
        self,
        kind: str | None = None,
        strict: bool = False,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.kind = _try_powerfx_eval(kind)
        self.strict = strict
        self.options = options or {}


class Parser(SerializationMixin):
    """Object representing template parser."""

    def __init__(
        self,
        kind: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.kind = _try_powerfx_eval(kind)
        self.options = options or {}


class Template(SerializationMixin):
    """Object representing a template configuration."""

    def __init__(
        self,
        format: Format | None = None,
        parser: Parser | None = None,
    ) -> None:
        if not isinstance(format, Format) and format is not None:
            format = Format.from_dict(format)
        self.format = format
        if not isinstance(parser, Parser) and parser is not None:
            parser = Parser.from_dict(parser)
        self.parser = parser


class AgentDefinition(SerializationMixin):
    """Object representing a prompt specification."""

    def __init__(
        self,
        kind: str | None = None,
        name: str | None = None,
        displayName: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        inputSchema: PropertySchema | None = None,
        outputSchema: PropertySchema | None = None,
    ) -> None:
        self.kind = _try_powerfx_eval(kind)
        self.name = _try_powerfx_eval(name)
        self.displayName = _try_powerfx_eval(displayName)
        self.description = _try_powerfx_eval(description)
        self.metadata = metadata
        if not isinstance(inputSchema, PropertySchema) and inputSchema is not None:
            inputSchema = PropertySchema.from_dict(inputSchema)
        self.inputSchema = inputSchema
        if not isinstance(outputSchema, PropertySchema) and outputSchema is not None:
            outputSchema = PropertySchema.from_dict(outputSchema)
        self.outputSchema = outputSchema

    @classmethod
    def from_dict(
        cls, value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> "AgentDefinition":
        """Create an AgentDefinition instance from a dictionary, dispatching to the appropriate subclass."""
        # Only dispatch if we're being called on the base AgentDefinition class
        if cls is not AgentDefinition:
            # We're being called on a subclass, use the normal from_dict
            return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]

        kind = value.get("kind", "")
        if kind == "Prompt" or kind == "Agent":
            return PromptAgent.from_dict(value, dependencies=dependencies)
        # Default to AgentDefinition
        return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]


TTool = TypeVar("TTool", bound="Tool")


class Tool(SerializationMixin):
    """Base class for tools."""

    def __init__(
        self,
        name: str | None = None,
        kind: str | None = None,
        description: str | None = None,
        bindings: list[Binding] | dict[str, Any] | None = None,
    ) -> None:
        self.name = _try_powerfx_eval(name)
        self.kind = _try_powerfx_eval(kind)
        self.description = _try_powerfx_eval(description)
        converted_bindings: list[Binding] = []
        if isinstance(bindings, list):
            for binding in bindings:
                if not isinstance(binding, Binding):
                    binding = Binding.from_dict(binding)
                converted_bindings.append(binding)
        elif isinstance(bindings, dict):
            for k, v in bindings.items():
                temp_binding = {"name": k, "input": v} if isinstance(v, str) else {"name": k, **v}
                binding = Binding.from_dict(temp_binding)
                converted_bindings.append(binding)
        self.bindings = converted_bindings

    @classmethod
    def from_dict(
        cls: type[TTool], value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> "TTool":
        """Create a Tool instance from a dictionary, dispatching to the appropriate subclass."""
        # Only dispatch if we're being called on the base Tool class
        if cls is not Tool:
            # We're being called on a subclass, use the normal from_dict
            return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]

        kind = value.get("kind", "")
        if kind == "function":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                FunctionTool, value, dependencies=dependencies
            )
        if kind == "custom":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                CustomTool, value, dependencies=dependencies
            )
        if kind == "web_search":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                WebSearchTool, value, dependencies=dependencies
            )
        if kind == "file_search":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                FileSearchTool, value, dependencies=dependencies
            )
        if kind == "mcp":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                McpTool, value, dependencies=dependencies
            )
        if kind == "openapi":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                OpenApiTool, value, dependencies=dependencies
            )
        if kind == "code_interpreter":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                CodeInterpreterTool, value, dependencies=dependencies
            )
        # Default to base Tool class
        return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]


class FunctionTool(Tool):
    """Object representing a function tool."""

    def __init__(
        self,
        name: str | None = None,
        kind: str = "function",
        description: str | None = None,
        bindings: list[Binding] | None = None,
        parameters: PropertySchema | list[Property] | dict[str, Any] | None = None,
        strict: bool = False,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            bindings=bindings,
        )
        if isinstance(parameters, list):
            # If parameters is a list, wrap it in a PropertySchema
            parameters = PropertySchema(properties=parameters)
        elif not isinstance(parameters, PropertySchema) and parameters is not None:
            parameters = PropertySchema.from_dict(parameters)
        self.parameters = parameters
        self.strict = strict


class CustomTool(Tool):
    """Object representing a custom tool."""

    def __init__(
        self,
        name: str | None = None,
        kind: str = "custom",
        description: str | None = None,
        bindings: list[Binding] | None = None,
        connection: Connection | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            bindings=bindings,
        )
        if not isinstance(connection, Connection) and connection is not None:
            connection = Connection.from_dict(connection)
        self.connection = connection
        self.options = options or {}


class WebSearchTool(Tool):
    """Object representing a web search tool."""

    def __init__(
        self,
        name: str | None = None,
        kind: str = "web_search",
        description: str | None = None,
        bindings: list[Binding] | None = None,
        connection: Connection | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            bindings=bindings,
        )
        if not isinstance(connection, Connection) and connection is not None:
            connection = Connection.from_dict(connection)
        self.connection = connection
        self.options = options or {}


class FileSearchTool(Tool):
    """Object representing a file search tool."""

    def __init__(
        self,
        name: str | None = None,
        kind: str = "file_search",
        description: str | None = None,
        bindings: list[Binding] | None = None,
        connection: Connection | None = None,
        vectorStoreIds: list[str] | None = None,
        maximumResultCount: int | None = None,
        ranker: str | None = None,
        scoreThreshold: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            bindings=bindings,
        )
        if not isinstance(connection, Connection) and connection is not None:
            connection = Connection.from_dict(connection)
        self.connection = connection
        self.vectorStoreIds = vectorStoreIds or []
        self.maximumResultCount = maximumResultCount
        self.ranker = _try_powerfx_eval(ranker)
        self.scoreThreshold = scoreThreshold
        self.filters = filters or {}


class McpServerApprovalMode(SerializationMixin):
    """Base class for MCP server approval modes."""

    def __init__(
        self,
        kind: str | None = None,
    ) -> None:
        self.kind = _try_powerfx_eval(kind)


class McpServerToolAlwaysRequireApprovalMode(McpServerApprovalMode):
    """MCP server tool always require approval mode."""

    def __init__(
        self,
        kind: str = "always",
    ) -> None:
        super().__init__(kind=kind)


class McpServerToolNeverRequireApprovalMode(McpServerApprovalMode):
    """MCP server tool never require approval mode."""

    def __init__(
        self,
        kind: str = "never",
    ) -> None:
        super().__init__(kind=kind)


class McpServerToolSpecifyApprovalMode(McpServerApprovalMode):
    """MCP server tool specify approval mode."""

    def __init__(
        self,
        kind: str = "specify",
        alwaysRequireApprovalTools: list[str] | None = None,
        neverRequireApprovalTools: list[str] | None = None,
    ) -> None:
        super().__init__(kind=kind)
        self.alwaysRequireApprovalTools = alwaysRequireApprovalTools
        self.neverRequireApprovalTools = neverRequireApprovalTools


class McpTool(Tool):
    """Object representing an MCP tool."""

    def __init__(
        self,
        name: str | None = None,
        kind: str = "mcp",
        description: str | None = None,
        bindings: list[Binding] | None = None,
        connection: Connection | None = None,
        serverName: str | None = None,
        serverDescription: str | None = None,
        approvalMode: McpServerApprovalMode | None = None,
        allowedTools: list[str] | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            bindings=bindings,
        )
        if not isinstance(connection, Connection) and connection is not None:
            connection = Connection.from_dict(connection)
        self.connection = connection
        self.serverName = _try_powerfx_eval(serverName)
        self.serverDescription = _try_powerfx_eval(serverDescription)
        if not isinstance(approvalMode, McpServerApprovalMode) and approvalMode is not None:
            # Handle simplified string format: "always" -> {"kind": "always"}
            if isinstance(approvalMode, str):
                approvalMode = McpServerApprovalMode.from_dict({"kind": approvalMode})
            else:
                approvalMode = McpServerApprovalMode.from_dict(approvalMode)
        self.approvalMode = approvalMode
        self.allowedTools = allowedTools or []
        self.url = _try_powerfx_eval(url)


class OpenApiTool(Tool):
    """Object representing an OpenAPI tool."""

    def __init__(
        self,
        name: str | None = None,
        kind: str = "openapi",
        description: str | None = None,
        bindings: list[Binding] | None = None,
        connection: Connection | None = None,
        specification: str | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            bindings=bindings,
        )
        if not isinstance(connection, Connection) and connection is not None:
            connection = Connection.from_dict(connection)
        self.connection = connection
        self.specification = _try_powerfx_eval(specification)


class CodeInterpreterTool(Tool):
    """Object representing a code interpreter tool."""

    def __init__(
        self,
        name: str | None = None,
        kind: str = "code_interpreter",
        description: str | None = None,
        bindings: list[Binding] | None = None,
        fileIds: list[str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            bindings=bindings,
        )
        self.fileIds = fileIds or []


class PromptAgent(AgentDefinition):
    """Object representing a prompt agent specification."""

    def __init__(
        self,
        kind: str = "Prompt",
        name: str | None = None,
        displayName: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        inputSchema: PropertySchema | None = None,
        outputSchema: PropertySchema | None = None,
        model: Model | dict[str, Any] | None = None,
        tools: list[Tool] | None = None,
        template: Template | dict[str, Any] | None = None,
        instructions: str | None = None,
        additionalInstructions: str | None = None,
    ) -> None:
        super().__init__(
            kind=kind,
            name=name,
            displayName=displayName,
            description=description,
            metadata=metadata,
            inputSchema=inputSchema,
            outputSchema=outputSchema,
        )
        if not isinstance(model, Model) and model is not None:
            model = Model.from_dict(model)
        self.model = model
        converted_tools: list[Tool] = []
        for tool in tools or []:
            if not isinstance(tool, Tool):
                tool = Tool.from_dict(tool)
            converted_tools.append(tool)
        self.tools = converted_tools
        if not isinstance(template, Template) and template is not None:
            template = Template.from_dict(template)
        self.template = template
        self.instructions = _try_powerfx_eval(instructions)
        self.additionalInstructions = _try_powerfx_eval(additionalInstructions)


class Resource(SerializationMixin):
    """Object representing a resource."""

    def __init__(
        self,
        name: str | None = None,
        kind: str | None = None,
    ) -> None:
        self.name = _try_powerfx_eval(name)
        self.kind = _try_powerfx_eval(kind)

    @classmethod
    def from_dict(
        cls, value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> "Resource":
        """Create a Resource instance from a dictionary, dispatching to the appropriate subclass."""
        # Only dispatch if we're being called on the base Resource class
        if cls is not Resource:
            # We're being called on a subclass, use the normal from_dict
            return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]

        kind = value.get("kind", "")
        if kind == "model":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                ModelResource, value, dependencies=dependencies
            )
        if kind == "tool":
            return SerializationMixin.from_dict.__func__(  # type: ignore[attr-defined, no-any-return]
                ToolResource, value, dependencies=dependencies
            )
        return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[attr-defined, no-any-return]


class ModelResource(Resource):
    """Object representing a model resource."""

    def __init__(
        self,
        kind: str = "model",
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name)
        self.id = _try_powerfx_eval(id)


class ToolResource(Resource):
    """Object representing a tool resource."""

    def __init__(
        self,
        kind: str = "tool",
        name: str | None = None,
        id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name)
        self.id = _try_powerfx_eval(id)
        self.options = options or {}


class ProtocolVersionRecord(SerializationMixin):
    """Object representing a protocol version record."""

    def __init__(
        self,
        protocol: str | None = None,
        version: str | None = None,
    ) -> None:
        self.protocol = _try_powerfx_eval(protocol)
        self.version = _try_powerfx_eval(version)


class EnvironmentVariable(SerializationMixin):
    """Object representing an environment variable."""

    def __init__(
        self,
        name: str | None = None,
        value: str | None = None,
    ) -> None:
        self.name = _try_powerfx_eval(name)
        self.value = _try_powerfx_eval(value)


class AgentManifest(SerializationMixin):
    """Object representing an agent manifest."""

    def __init__(
        self,
        name: str | None = None,
        displayName: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        template: AgentDefinition | None = None,
        parameters: PropertySchema | None = None,
        resources: list[Resource] | dict[str, Any] | None = None,
    ) -> None:
        self.name = _try_powerfx_eval(name)
        self.displayName = _try_powerfx_eval(displayName)
        self.description = _try_powerfx_eval(description)
        self.metadata = metadata or {}
        if not isinstance(template, AgentDefinition) and template is not None:
            template = AgentDefinition.from_dict(template)
        self.template = template or AgentDefinition()
        if not isinstance(parameters, PropertySchema) and parameters is not None:
            parameters = PropertySchema.from_dict(parameters)
        self.parameters = parameters or PropertySchema()
        converted_resources: list[Resource] = []
        if isinstance(resources, list):
            for resource in resources:
                if not isinstance(resource, Resource):
                    resource = Resource.from_dict(resource)
                converted_resources.append(resource)
        elif isinstance(resources, dict):
            for k, v in resources.items():
                temp_resource = {"name": k, **v}
                resource = Resource.from_dict(temp_resource)
                converted_resources.append(resource)
        self.resources = converted_resources


AgentSchemaSpec = Union[
    AgentManifest,
    AgentDefinition,
    PromptAgent,
    Tool,
    FunctionTool,
    CustomTool,
    WebSearchTool,
    FileSearchTool,
    McpTool,
    OpenApiTool,
    CodeInterpreterTool,
    Resource,
    ModelResource,
    ToolResource,
    Connection,
    ReferenceConnection,
    RemoteConnection,
    ApiKeyConnection,
    AnonymousConnection,
    Property,
    ArrayProperty,
    ObjectProperty,
    PropertySchema,
    McpServerApprovalMode,
    McpServerToolAlwaysRequireApprovalMode,
    McpServerToolNeverRequireApprovalMode,
    McpServerToolSpecifyApprovalMode,
    Binding,
    Format,
    Parser,
    Template,
    Model,
    ModelOptions,
    ProtocolVersionRecord,
    EnvironmentVariable,
]


def agent_schema_dispatch(schema: dict[str, Any]) -> AgentSchemaSpec | None:
    """Create a component instance from a dictionary, dispatching to the appropriate class based on 'kind' field."""
    kind = schema.get("kind")

    # If no kind field, assume it's an AgentManifest
    if kind is None:
        return AgentManifest.from_dict(schema)
    # Match on the kind field to determine which class to instantiate
    match kind.lower():
        # Agent types
        case "prompt":
            return PromptAgent.from_dict(schema)
        case "agent":
            return AgentDefinition.from_dict(schema)

        # Resource types
        case "tool":
            return ToolResource.from_dict(schema)
        case "model":
            return ModelResource.from_dict(schema)
        case "resource":
            return Resource.from_dict(schema)

        # Tool types
        case "function":
            return FunctionTool.from_dict(schema)
        case "custom":
            return CustomTool.from_dict(schema)
        case "web_search":
            return WebSearchTool.from_dict(schema)
        case "file_search":
            return FileSearchTool.from_dict(schema)
        case "mcp":
            return McpTool.from_dict(schema)
        case "openapi":
            return OpenApiTool.from_dict(schema)
        case "code_interpreter":
            return CodeInterpreterTool.from_dict(schema)

        # Connection types
        case "reference":
            return ReferenceConnection.from_dict(schema)
        case "remote":
            return RemoteConnection.from_dict(schema)
        case "key":
            return ApiKeyConnection.from_dict(schema)
        case "anonymous":
            return AnonymousConnection.from_dict(schema)
        case "connection":
            return Connection.from_dict(schema)

        # Property types
        case "array":
            return ArrayProperty.from_dict(schema)
        case "object":
            return ObjectProperty.from_dict(schema)
        case "property":
            return Property.from_dict(schema)

        # MCP Server Approval Mode types
        case "always":
            return McpServerToolAlwaysRequireApprovalMode.from_dict(schema)
        case "never":
            return McpServerToolNeverRequireApprovalMode.from_dict(schema)
        case "specify":
            return McpServerToolSpecifyApprovalMode.from_dict(schema)
        case "approval_mode":
            return McpServerApprovalMode.from_dict(schema)

        # Other component types
        case "binding":
            return Binding.from_dict(schema)
        case "format":
            return Format.from_dict(schema)
        case "parser":
            return Parser.from_dict(schema)
        case "template":
            return Template.from_dict(schema)
        case "model":
            return Model.from_dict(schema)
        case "model_options":
            return ModelOptions.from_dict(schema)
        case "property_schema":
            return PropertySchema.from_dict(schema)
        case "protocol_version":
            return ProtocolVersionRecord.from_dict(schema)
        case "environment_variable":
            return EnvironmentVariable.from_dict(schema)

        # Unknown kind
        case _:
            return None
