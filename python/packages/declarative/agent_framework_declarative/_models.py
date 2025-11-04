# Copyright (c) Microsoft. All rights reserved.

from collections.abc import MutableMapping
from typing import Any

from agent_framework._serialization import SerializationMixin


class Binding(SerializationMixin):
    """Object representing a tool argument binding."""

    def __init__(
        self,
        name: str = "",
        input: str = "",
    ) -> None:
        self.name = name
        self.input = input


class Property(SerializationMixin):
    """Object representing a property in a schema."""

    def __init__(
        self,
        name: str = "",
        kind: str = "",
        description: str | None = None,
        required: bool | None = None,
        default: Any | None = None,
        example: Any | None = None,
        enumValues: list[Any] | None = None,
    ) -> None:
        self.name = name
        self.kind = kind
        self.description = description
        self.required = required
        self.default = default
        self.example = example
        self.enumValues = enumValues or []

    @classmethod
    def from_dict(
        cls, value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> "Property":
        """Create a Property instance from a dictionary, dispatching to the appropriate subclass."""
        # Only dispatch if we're being called on the base Property class
        if cls is not Property:
            # We're being called on a subclass, use the normal from_dict
            return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[misc]

        kind = value.get("kind", "")
        if kind == "array":
            from agent_framework_declarative._models import ArrayProperty

            return ArrayProperty.from_dict(value, dependencies=dependencies)
        if kind == "object":
            from agent_framework_declarative._models import ObjectProperty

            return ObjectProperty.from_dict(value, dependencies=dependencies)
        # Default to Property for kind="property" or empty
        return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[misc]


class ArrayProperty(Property):
    """Object representing an array property."""

    def __init__(
        self,
        name: str = "",
        kind: str = "array",
        description: str | None = None,
        required: bool | None = None,
        default: Any | None = None,
        example: Any | None = None,
        enumValues: list[Any] | None = None,
        items: Property | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            required=required,
            default=default,
            example=example,
            enumValues=enumValues,
        )
        if not isinstance(items, Property) and items is not None:
            items = Property.from_dict(items)
        self.items = items


class ObjectProperty(Property):
    """Object representing an object property."""

    def __init__(
        self,
        name: str = "",
        kind: str = "object",
        description: str | None = None,
        required: bool | None = None,
        default: Any | None = None,
        example: Any | None = None,
        enumValues: list[Any] | None = None,
        properties: list[Property] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            required=required,
            default=default,
            example=example,
            enumValues=enumValues,
        )
        converted_properties = []
        for prop in properties or []:
            if not isinstance(prop, Property):
                prop = Property.from_dict(prop)
            converted_properties.append(prop)
        self.properties = converted_properties


class PropertySchema(SerializationMixin):
    """Object representing a property schema."""

    def __init__(
        self,
        examples: list[dict[str, Any]] | None = None,
        strict: bool = False,
        properties: list[Property] | None = None,
    ) -> None:
        self.examples = examples or []
        self.strict = strict
        converted_properties = []
        for prop in properties or []:
            if not isinstance(prop, Property):
                prop = Property.from_dict(prop)
            converted_properties.append(prop)
        self.properties = converted_properties

    @classmethod
    def from_dict(
        cls, value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> "PropertySchema":
        """Create a PropertySchema instance from a dictionary, filtering out 'kind' field."""
        # Filter out 'kind' and 'type' fields
        kwargs = {k: v for k, v in value.items() if k not in ("type", "kind")}
        return SerializationMixin.from_dict.__func__(cls, kwargs, dependencies=dependencies)  # type: ignore[misc]


class Connection(SerializationMixin):
    """Object representing a connection specification."""

    def __init__(
        self,
        kind: str = "",
        authenticationMode: str = "",
        usageDescription: str = "",
    ) -> None:
        self.kind = kind
        self.authenticationMode = authenticationMode
        self.usageDescription = usageDescription

    @classmethod
    def from_dict(
        cls, value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> "Connection":
        """Create a Connection instance from a dictionary, dispatching to the appropriate subclass."""
        # Only dispatch if we're being called on the base Connection class
        if cls is not Connection:
            # We're being called on a subclass, use the normal from_dict
            return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[misc]

        kind = value.get("kind", "")
        if kind == "reference":
            return SerializationMixin.from_dict.__func__(  # type: ignore[misc]
                ReferenceConnection, value, dependencies=dependencies
            )
        if kind == "remote":
            return SerializationMixin.from_dict.__func__(  # type: ignore[misc]
                RemoteConnection, value, dependencies=dependencies
            )
        if kind == "key":
            return SerializationMixin.from_dict.__func__(  # type: ignore[misc]
                ApiKeyConnection, value, dependencies=dependencies
            )
        if kind == "anonymous":
            return SerializationMixin.from_dict.__func__(  # type: ignore[misc]
                AnonymousConnection, value, dependencies=dependencies
            )
        return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[misc]


class ReferenceConnection(Connection):
    """Object representing a reference connection."""

    def __init__(
        self,
        kind: str = "reference",
        authenticationMode: str = "",
        usageDescription: str = "",
        name: str = "",
        target: str = "",
    ) -> None:
        super().__init__(
            kind=kind,
            authenticationMode=authenticationMode,
            usageDescription=usageDescription,
        )
        self.name = name
        self.target = target


class RemoteConnection(Connection):
    """Object representing a remote connection."""

    def __init__(
        self,
        kind: str = "remote",
        authenticationMode: str = "",
        usageDescription: str = "",
        name: str = "",
        endpoint: str = "",
    ) -> None:
        super().__init__(
            kind=kind,
            authenticationMode=authenticationMode,
            usageDescription=usageDescription,
        )
        self.name = name
        self.endpoint = endpoint


class ApiKeyConnection(Connection):
    """Object representing an API key connection."""

    def __init__(
        self,
        kind: str = "key",
        authenticationMode: str = "",
        usageDescription: str = "",
        endpoint: str = "",
        apiKey: str = "",
    ) -> None:
        super().__init__(
            kind=kind,
            authenticationMode=authenticationMode,
            usageDescription=usageDescription,
        )
        self.endpoint = endpoint
        self.apiKey = apiKey


class AnonymousConnection(Connection):
    """Object representing an anonymous connection."""

    def __init__(
        self,
        kind: str = "anonymous",
        authenticationMode: str = "",
        usageDescription: str = "",
        endpoint: str = "",
    ) -> None:
        super().__init__(
            kind=kind,
            authenticationMode=authenticationMode,
            usageDescription=usageDescription,
        )
        self.endpoint = endpoint


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
        self.additionalProperties = additionalProperties or {}


class Model(SerializationMixin):
    """Object representing a model specification."""

    def __init__(
        self,
        id: str = "",
        provider: str = "",
        apiType: str = "",
        connection: Connection | None = None,
        options: ModelOptions | None = None,
    ) -> None:
        self.id = id
        self.provider = provider
        self.apiType = apiType
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
        kind: str = "",
        strict: bool = False,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.kind = kind
        self.strict = strict
        self.options = options or {}


class Parser(SerializationMixin):
    """Object representing template parser."""

    def __init__(
        self,
        kind: str = "",
        options: dict[str, Any] | None = None,
    ) -> None:
        self.kind = kind
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
        kind: str = "",
        name: str = "",
        displayName: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
        inputSchema: PropertySchema | None = None,
        outputSchema: PropertySchema | None = None,
    ) -> None:
        self.kind = kind
        self.name = name
        self.displayName = displayName
        self.description = description
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
            return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[misc]

        kind = value.get("kind", "")
        if kind == "Prompt" or kind == "Agent":
            from agent_framework_declarative._models import PromptAgent

            return PromptAgent.from_dict(value, dependencies=dependencies)
        # Default to AgentDefinition
        return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[misc]


class Tool(SerializationMixin):
    """Base class for tools."""

    def __init__(
        self,
        name: str = "",
        kind: str = "",
        description: str = "",
        bindings: list[Binding] | None = None,
    ) -> None:
        self.name = name
        self.kind = kind
        self.description = description
        converted_bindings = []
        for binding in bindings or []:
            if not isinstance(binding, Binding):
                binding = Binding.from_dict(binding)
            converted_bindings.append(binding)
        self.bindings = converted_bindings


class FunctionTool(Tool):
    """Object representing a function tool."""

    def __init__(
        self,
        name: str = "",
        kind: str = "function",
        description: str = "",
        bindings: list[Binding] | None = None,
        parameters: PropertySchema | None = None,
        strict: bool = False,
    ) -> None:
        super().__init__(
            name=name,
            kind=kind,
            description=description,
            bindings=bindings,
        )
        if not isinstance(parameters, PropertySchema) and parameters is not None:
            parameters = PropertySchema.from_dict(parameters)
        self.parameters = parameters
        self.strict = strict


class CustomTool(Tool):
    """Object representing a custom tool."""

    def __init__(
        self,
        name: str = "",
        kind: str = "custom",
        description: str = "",
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
        name: str = "",
        kind: str = "web_search",
        description: str = "",
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
        name: str = "",
        kind: str = "file_search",
        description: str = "",
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
        self.ranker = ranker
        self.scoreThreshold = scoreThreshold
        self.filters = filters or {}


class McpServerApprovalMode(SerializationMixin):
    """Base class for MCP server approval modes."""

    def __init__(
        self,
        kind: str = "",
    ) -> None:
        self.kind = kind


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
        self.alwaysRequireApprovalTools = alwaysRequireApprovalTools or []
        self.neverRequireApprovalTools = neverRequireApprovalTools or []


class McpTool(Tool):
    """Object representing an MCP tool."""

    def __init__(
        self,
        name: str = "",
        kind: str = "mcp",
        description: str = "",
        bindings: list[Binding] | None = None,
        connection: Connection | None = None,
        serverName: str = "",
        serverDescription: str = "",
        approvalMode: McpServerApprovalMode | None = None,
        allowedTools: list[str] | None = None,
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
        self.serverName = serverName
        self.serverDescription = serverDescription
        if not isinstance(approvalMode, McpServerApprovalMode) and approvalMode is not None:
            approvalMode = McpServerApprovalMode.from_dict(approvalMode)
        self.approvalMode = approvalMode
        self.allowedTools = allowedTools or []


class OpenApiTool(Tool):
    """Object representing an OpenAPI tool."""

    def __init__(
        self,
        name: str = "",
        kind: str = "openapi",
        description: str = "",
        bindings: list[Binding] | None = None,
        connection: Connection | None = None,
        specification: str = "",
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
        self.specification = specification


class CodeInterpreterTool(Tool):
    """Object representing a code interpreter tool."""

    def __init__(
        self,
        name: str = "",
        kind: str = "code_interpreter",
        description: str = "",
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
        name: str = "",
        displayName: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
        inputSchema: PropertySchema | None = None,
        outputSchema: PropertySchema | None = None,
        model: Model | None = None,
        tools: list[Tool] | None = None,
        template: Template | None = None,
        instructions: str = "",
        additionalInstructions: str = "",
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
        converted_tools = []
        for tool in tools or []:
            if not isinstance(tool, Tool):
                tool = Tool.from_dict(tool)
            converted_tools.append(tool)
        self.tools = converted_tools
        if not isinstance(template, Template) and template is not None:
            template = Template.from_dict(template)
        self.template = template
        self.instructions = instructions
        self.additionalInstructions = additionalInstructions


class Resource(SerializationMixin):
    """Object representing a resource."""

    def __init__(
        self,
        name: str = "",
        kind: str = "",
    ) -> None:
        self.name = name
        self.kind = kind

    @classmethod
    def from_dict(
        cls, value: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> "Resource":
        """Create a Resource instance from a dictionary, dispatching to the appropriate subclass."""
        # Only dispatch if we're being called on the base Resource class
        if cls is not Resource:
            # We're being called on a subclass, use the normal from_dict
            return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[misc]

        kind = value.get("kind", "")
        if kind == "model":
            return SerializationMixin.from_dict.__func__(  # type: ignore[misc]
                ModelResource, value, dependencies=dependencies
            )
        if kind == "tool":
            return SerializationMixin.from_dict.__func__(  # type: ignore[misc]
                ToolResource, value, dependencies=dependencies
            )
        return SerializationMixin.from_dict.__func__(cls, value, dependencies=dependencies)  # type: ignore[misc]


class ModelResource(Resource):
    """Object representing a model resource."""

    def __init__(
        self,
        kind: str = "model",
        name: str = "",
        id: str = "",
    ) -> None:
        super().__init__(kind=kind, name=name)
        self.id = id


class ToolResource(Resource):
    """Object representing a tool resource."""

    def __init__(
        self,
        kind: str = "tool",
        name: str = "",
        id: str = "",
        options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(kind=kind, name=name)
        self.id = id
        self.options = options or {}


class ProtocolVersionRecord(SerializationMixin):
    """Object representing a protocol version record."""

    def __init__(
        self,
        protocol: str = "",
        version: str = "",
    ) -> None:
        self.protocol = protocol
        self.version = version


class EnvironmentVariable(SerializationMixin):
    """Object representing an environment variable."""

    def __init__(
        self,
        name: str = "",
        value: str = "",
    ) -> None:
        self.name = name
        self.value = value


class AgentManifest(SerializationMixin):
    """Object representing an agent manifest."""

    def __init__(
        self,
        name: str = "",
        displayName: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
        template: AgentDefinition | None = None,
        parameters: PropertySchema | None = None,
        resources: list[Resource] | None = None,
    ) -> None:
        self.name = name
        self.displayName = displayName
        self.description = description
        self.metadata = metadata or {}
        if not isinstance(template, AgentDefinition) and template is not None:
            template = AgentDefinition.from_dict(template)
        self.template = template or AgentDefinition()
        if not isinstance(parameters, PropertySchema) and parameters is not None:
            parameters = PropertySchema.from_dict(parameters)
        self.parameters = parameters or PropertySchema()
        converted_resources = []
        for resource in resources or []:
            if not isinstance(resource, Resource):
                resource = Resource.from_dict(resource)
            converted_resources.append(resource)
        self.resources = converted_resources
