# Copyright (c) Microsoft. All rights reserved.

from typing import Any

import yaml

from ._models import (
    AgentDefinition,
    AgentManifest,
    AnonymousConnection,
    ApiKeyConnection,
    ArrayProperty,
    Binding,
    CodeInterpreterTool,
    Connection,
    CustomTool,
    EnvironmentVariable,
    FileSearchTool,
    Format,
    FunctionTool,
    McpServerApprovalMode,
    McpServerToolAlwaysRequireApprovalMode,
    McpServerToolNeverRequireApprovalMode,
    McpServerToolSpecifyApprovalMode,
    McpTool,
    Model,
    ModelOptions,
    ModelResource,
    ObjectProperty,
    OpenApiTool,
    Parser,
    PromptAgent,
    Property,
    PropertySchema,
    ProtocolVersionRecord,
    ReferenceConnection,
    RemoteConnection,
    Resource,
    Template,
    ToolResource,
    WebSearchTool,
)


def load_maml(yaml_str: str) -> Any:
    """Load a MAML object from a YAML string.

    This function can parse any MAML object type and return the appropriate
    Python object. The type is determined by the 'kind' field in the YAML.
    If no 'kind' field is present, it's assumed to be an AgentManifest.

    Args:
        yaml_str: YAML string representation of a MAML object

    Returns:
        The appropriate MAML object instance, or None if the kind is not recognized
    """
    as_dict = yaml.safe_load(yaml_str)

    # If no kind field, assume it's an AgentManifest
    if "kind" not in as_dict:
        return AgentManifest.from_dict(as_dict)

    kind = as_dict["kind"]

    # Match on the kind field to determine which class to instantiate
    match kind:
        # Agent types
        case "Prompt":
            return PromptAgent.from_dict(as_dict)
        case "Agent":
            return AgentDefinition.from_dict(as_dict)

        # Resource types
        case "Tool":
            return ToolResource.from_dict(as_dict)
        case "Model":
            return ModelResource.from_dict(as_dict)
        case "Resource":
            return Resource.from_dict(as_dict)

        # Tool types
        case "function":
            return FunctionTool.from_dict(as_dict)
        case "custom":
            return CustomTool.from_dict(as_dict)
        case "web_search":
            return WebSearchTool.from_dict(as_dict)
        case "file_search":
            return FileSearchTool.from_dict(as_dict)
        case "mcp":
            return McpTool.from_dict(as_dict)
        case "openapi":
            return OpenApiTool.from_dict(as_dict)
        case "code_interpreter":
            return CodeInterpreterTool.from_dict(as_dict)

        # Connection types
        case "reference":
            return ReferenceConnection.from_dict(as_dict)
        case "remote":
            return RemoteConnection.from_dict(as_dict)
        case "key":
            return ApiKeyConnection.from_dict(as_dict)
        case "anonymous":
            return AnonymousConnection.from_dict(as_dict)
        case "connection":
            return Connection.from_dict(as_dict)

        # Property types
        case "array":
            return ArrayProperty.from_dict(as_dict)
        case "object":
            return ObjectProperty.from_dict(as_dict)
        case "property":
            return Property.from_dict(as_dict)

        # MCP Server Approval Mode types
        case "always":
            return McpServerToolAlwaysRequireApprovalMode.from_dict(as_dict)
        case "never":
            return McpServerToolNeverRequireApprovalMode.from_dict(as_dict)
        case "specify":
            return McpServerToolSpecifyApprovalMode.from_dict(as_dict)
        case "approval_mode":
            return McpServerApprovalMode.from_dict(as_dict)

        # Other component types
        case "binding":
            return Binding.from_dict(as_dict)
        case "format":
            return Format.from_dict(as_dict)
        case "parser":
            return Parser.from_dict(as_dict)
        case "template":
            return Template.from_dict(as_dict)
        case "model":
            return Model.from_dict(as_dict)
        case "model_options":
            return ModelOptions.from_dict(as_dict)
        case "property_schema":
            return PropertySchema.from_dict(as_dict)
        case "protocol_version":
            return ProtocolVersionRecord.from_dict(as_dict)
        case "environment_variable":
            return EnvironmentVariable.from_dict(as_dict)

        # Unknown kind
        case _:
            return None
