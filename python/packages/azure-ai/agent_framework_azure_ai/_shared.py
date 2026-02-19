# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, cast

from agent_framework import (
    FunctionTool,
)
from agent_framework.exceptions import ServiceInvalidRequestError
from azure.ai.agents.models import (
    CodeInterpreterToolDefinition,
    ToolDefinition,
)
from azure.ai.projects.models import (
    CodeInterpreterTool,
    MCPTool,
    ResponseTextFormatConfigurationJsonObject,
    ResponseTextFormatConfigurationJsonSchema,
    ResponseTextFormatConfigurationText,
    Tool,
    WebSearchPreviewTool,
)
from azure.ai.projects.models import (
    FileSearchTool as ProjectsFileSearchTool,
)
from azure.ai.projects.models import (
    FunctionTool as AzureFunctionTool,
)
from pydantic import BaseModel

if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

logger = logging.getLogger("agent_framework.azure")


class AzureAISettings(TypedDict, total=False):
    """Azure AI Project settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'AZURE_AI_'. If settings are missing after resolution, validation will fail.

    Keyword Args:
        project_endpoint: The Azure AI Project endpoint URL.
            Can be set via environment variable AZURE_AI_PROJECT_ENDPOINT.
        model_deployment_name: The name of the model deployment to use.
            Can be set via environment variable AZURE_AI_MODEL_DEPLOYMENT_NAME.
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework.azure import AzureAISettings

            # Using environment variables
            # Set AZURE_AI_PROJECT_ENDPOINT=https://your-project.cognitiveservices.azure.com
            # Set AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4
            settings = AzureAISettings()

            # Or passing parameters directly
            settings = AzureAISettings(
                project_endpoint="https://your-project.cognitiveservices.azure.com", model_deployment_name="gpt-4"
            )

            # Or loading from a .env file
            settings = AzureAISettings(env_file_path="path/to/.env")
    """

    project_endpoint: str | None
    model_deployment_name: str | None


def _extract_project_connection_id(additional_properties: dict[str, Any] | None) -> str | None:
    """Extract project_connection_id from tool additional_properties.

    Checks for both direct 'project_connection_id' key (programmatic usage)
    and 'connection.name' structure (declarative/YAML usage).

    Args:
        additional_properties: The additional_properties dict from a tool.

    Returns:
        The project_connection_id if found, None otherwise.
    """
    if not additional_properties:
        return None

    # Check for direct project_connection_id (programmatic usage)
    project_connection_id = additional_properties.get("project_connection_id")
    if isinstance(project_connection_id, str):
        return project_connection_id

    # Check for connection.name structure (declarative/YAML usage)
    if "connection" in additional_properties:
        conn = additional_properties["connection"]
        if isinstance(conn, dict):
            name = conn.get("name")
            if isinstance(name, str):
                return name

    return None


def to_azure_ai_agent_tools(
    tools: Sequence[FunctionTool | MutableMapping[str, Any]] | None,
    run_options: dict[str, Any] | None = None,
) -> list[ToolDefinition | dict[str, Any]]:
    """Convert Agent Framework tools to Azure AI V1 SDK tool definitions.

    Handles FunctionTool instances and dict-based tools from static factory methods.

    Args:
        tools: Sequence of Agent Framework tools to convert.
        run_options: Optional dict with run options.

    Returns:
        List of Azure AI V1 SDK tool definitions.

    Raises:
        ServiceInitializationError: If tool configuration is invalid.
    """
    if not tools:
        return []

    tool_definitions: list[ToolDefinition | dict[str, Any]] = []
    for tool in tools:
        if isinstance(tool, FunctionTool):
            tool_definitions.append(tool.to_json_schema_spec())  # type: ignore[reportUnknownArgumentType]
        elif isinstance(tool, ToolDefinition):
            # Pass through ToolDefinition subclasses unchanged (includes CodeInterpreterToolDefinition, etc.)
            tool_definitions.append(tool)
        elif hasattr(tool, "definitions") and not isinstance(tool, (dict, MutableMapping)):
            # SDK Tool wrappers (McpTool, FileSearchTool, BingGroundingTool, etc.)
            tool_definitions.extend(tool.definitions)
            # Handle tool resources (MCP resources handled separately)
            if (
                run_options is not None
                and hasattr(tool, "resources")
                and tool.resources
                and "mcp" not in tool.resources
            ):
                if "tool_resources" not in run_options:
                    run_options["tool_resources"] = {}
                run_options["tool_resources"].update(tool.resources)
        elif isinstance(tool, (dict, MutableMapping)):
            # Handle dict-based tools - pass through directly
            tool_dict = tool if isinstance(tool, dict) else dict(tool)
            tool_definitions.append(tool_dict)
        else:
            # Pass through other types unchanged
            tool_definitions.append(tool)
    return tool_definitions


def from_azure_ai_agent_tools(
    tools: Sequence[ToolDefinition | dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Convert Azure AI V1 SDK tool definitions to dict-based tools.

    Args:
        tools: Sequence of Azure AI V1 SDK tool definitions.

    Returns:
        List of dict-based tool definitions.
    """
    if not tools:
        return []

    result: list[dict[str, Any]] = []
    for tool in tools:
        # Handle SDK objects
        if isinstance(tool, CodeInterpreterToolDefinition):
            result.append({"type": "code_interpreter"})
        elif isinstance(tool, dict):
            # Handle dict format
            converted = _convert_dict_tool(tool)
            if converted is not None:
                result.append(converted)
        elif hasattr(tool, "type"):
            # Handle other SDK objects by type
            converted = _convert_sdk_tool(tool)
            if converted is not None:
                result.append(converted)
    return result


def _convert_dict_tool(tool: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a dict-format Azure AI tool to dict-based tool format."""
    tool_type = tool.get("type")

    if tool_type == "code_interpreter":
        return {"type": "code_interpreter"}

    if tool_type == "file_search":
        file_search_config = tool.get("file_search", {})
        vector_store_ids = file_search_config.get("vector_store_ids", [])
        return {"type": "file_search", "vector_store_ids": vector_store_ids}

    if tool_type == "bing_grounding":
        bing_config = tool.get("bing_grounding", {})
        connection_id = bing_config.get("connection_id")
        return {"type": "bing_grounding", "connection_id": connection_id} if connection_id else None

    if tool_type == "bing_custom_search":
        bing_config = tool.get("bing_custom_search", {})
        connection_id = bing_config.get("connection_id")
        instance_name = bing_config.get("instance_name")
        # Only return if both required fields are present
        if connection_id and instance_name:
            return {
                "type": "bing_custom_search",
                "connection_id": connection_id,
                "instance_name": instance_name,
            }
        return None

    if tool_type == "mcp":
        # MCP tools are defined on the Azure agent, no local handling needed
        # Azure may not return full server_url, so skip conversion
        return None

    if tool_type == "function":
        # Function tools are returned as dicts - users must provide implementations
        return tool

    # Unknown tool type - pass through
    return tool


def _convert_sdk_tool(tool: ToolDefinition) -> dict[str, Any] | None:
    """Convert an SDK-object Azure AI tool to dict-based tool format."""
    tool_type = getattr(tool, "type", None)

    if tool_type == "code_interpreter":
        return {"type": "code_interpreter"}

    if tool_type == "file_search":
        file_search_config = getattr(tool, "file_search", None)
        vector_store_ids = getattr(file_search_config, "vector_store_ids", []) if file_search_config else []
        return {"type": "file_search", "vector_store_ids": vector_store_ids}

    if tool_type == "bing_grounding":
        bing_config = getattr(tool, "bing_grounding", None)
        connection_id = getattr(bing_config, "connection_id", None) if bing_config else None
        return {"type": "bing_grounding", "connection_id": connection_id} if connection_id else None

    if tool_type == "bing_custom_search":
        bing_config = getattr(tool, "bing_custom_search", None)
        connection_id = getattr(bing_config, "connection_id", None) if bing_config else None
        instance_name = getattr(bing_config, "instance_name", None) if bing_config else None
        # Only return if both required fields are present
        if connection_id and instance_name:
            return {
                "type": "bing_custom_search",
                "connection_id": connection_id,
                "instance_name": instance_name,
            }
        return None

    if tool_type == "mcp":
        # MCP tools are defined on the Azure agent, no local handling needed
        # Azure may not return full server_url, so skip conversion
        return None

    if tool_type == "function":
        # Function tools from SDK don't have implementations - skip
        return None

    # Unknown tool type - convert to dict if possible
    if hasattr(tool, "as_dict"):
        return tool.as_dict()  # type: ignore[union-attr]
    return {"type": tool_type} if tool_type else {}


def from_azure_ai_tools(tools: Sequence[Tool | dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Parses and converts a sequence of Azure AI tools into dict-based tools.

    Args:
        tools: A sequence of tool objects or dictionaries
            defining the tools to be parsed. Can be None.

    Returns:
        list[dict[str, Any]]: A list of dict-based tool definitions.
    """
    agent_tools: list[dict[str, Any]] = []
    if not tools:
        return agent_tools
    for tool in tools:
        # Handle raw dictionary tools
        tool_dict = tool if isinstance(tool, dict) else dict(tool)
        tool_type = tool_dict.get("type")

        if tool_type == "mcp":
            mcp_tool = cast(MCPTool, tool_dict)
            result: dict[str, Any] = {
                "type": "mcp",
                "server_label": mcp_tool.get("server_label", ""),
                "server_url": mcp_tool.get("server_url", ""),
            }
            if description := mcp_tool.get("server_description"):
                result["server_description"] = description
            if headers := mcp_tool.get("headers"):
                result["headers"] = headers
            if allowed_tools := mcp_tool.get("allowed_tools"):
                result["allowed_tools"] = allowed_tools
            if require_approval := mcp_tool.get("require_approval"):
                result["require_approval"] = require_approval
            if project_connection_id := mcp_tool.get("project_connection_id"):
                result["project_connection_id"] = project_connection_id
            agent_tools.append(result)
        elif tool_type == "code_interpreter":
            ci_tool = cast(CodeInterpreterTool, tool_dict)
            container = ci_tool.get("container", {})
            result = {"type": "code_interpreter"}
            if "file_ids" in container:
                result["file_ids"] = container["file_ids"]
            agent_tools.append(result)
        elif tool_type == "file_search":
            fs_tool = cast(ProjectsFileSearchTool, tool_dict)
            result = {"type": "file_search"}
            if "vector_store_ids" in fs_tool:
                result["vector_store_ids"] = fs_tool["vector_store_ids"]
            if max_results := fs_tool.get("max_num_results"):
                result["max_num_results"] = max_results
            agent_tools.append(result)
        elif tool_type == "web_search_preview":
            ws_tool = cast(WebSearchPreviewTool, tool_dict)
            result = {"type": "web_search_preview"}
            if user_location := ws_tool.get("user_location"):
                result["user_location"] = {
                    "city": user_location.get("city"),
                    "country": user_location.get("country"),
                    "region": user_location.get("region"),
                    "timezone": user_location.get("timezone"),
                }
            agent_tools.append(result)
        else:
            agent_tools.append(tool_dict)
    return agent_tools


def to_azure_ai_tools(
    tools: Sequence[FunctionTool | MutableMapping[str, Any] | Tool] | None,
) -> list[Tool | dict[str, Any]]:
    """Converts Agent Framework tools into Azure AI compatible tools.

    Handles FunctionTool instances and passes through SDK Tool types directly.

    Args:
        tools: A sequence of Agent Framework tool objects, SDK Tool types, or dictionaries
            defining the tools to be converted. Can be None.

    Returns:
        list[Tool | dict[str, Any]]: A list of converted tools compatible with Azure AI.
    """
    azure_tools: list[Tool | dict[str, Any]] = []
    if not tools:
        return azure_tools

    for tool in tools:
        if isinstance(tool, FunctionTool):
            params = tool.parameters()
            params["additionalProperties"] = False
            azure_tools.append(
                AzureFunctionTool(
                    name=tool.name,
                    parameters=params,
                    strict=False,
                    description=tool.description,
                )
            )
        elif isinstance(tool, Tool):
            # Pass through SDK Tool types directly (CodeInterpreterTool, FileSearchTool, etc.)
            azure_tools.append(tool)
        else:
            # Pass through dict-based tools directly
            azure_tools.append(dict(tool) if isinstance(tool, MutableMapping) else tool)  # type: ignore[arg-type]

    return azure_tools


def _prepare_mcp_tool_dict_for_azure_ai(tool_dict: dict[str, Any]) -> MCPTool:
    """Convert dict-based MCP tool to Azure AI MCPTool format.

    Args:
        tool_dict: The dict-based MCP tool configuration.

    Returns:
        MCPTool: The converted Azure AI MCPTool.
    """
    server_label = tool_dict.get("server_label", "")
    server_url = tool_dict.get("server_url", "")
    mcp: MCPTool = MCPTool(server_label=server_label, server_url=server_url)

    if description := tool_dict.get("server_description"):
        mcp["server_description"] = description

    # Check for project_connection_id
    if project_connection_id := tool_dict.get("project_connection_id"):
        mcp["project_connection_id"] = project_connection_id
    elif headers := tool_dict.get("headers"):
        mcp["headers"] = headers

    if allowed_tools := tool_dict.get("allowed_tools"):
        mcp["allowed_tools"] = list(allowed_tools)

    if require_approval := tool_dict.get("require_approval"):
        mcp["require_approval"] = require_approval

    return mcp


def create_text_format_config(
    response_format: type[BaseModel] | Mapping[str, Any],
) -> (
    ResponseTextFormatConfigurationJsonSchema
    | ResponseTextFormatConfigurationJsonObject
    | ResponseTextFormatConfigurationText
):
    """Convert response_format into Azure text format configuration."""
    if isinstance(response_format, type) and issubclass(response_format, BaseModel):
        schema = response_format.model_json_schema()
        # Ensure additionalProperties is explicitly false to satisfy Azure validation
        if isinstance(schema, dict):
            schema.setdefault("additionalProperties", False)
        return ResponseTextFormatConfigurationJsonSchema(
            name=response_format.__name__,
            schema=schema,
            strict=True,
        )

    if isinstance(response_format, Mapping):
        format_config = _convert_response_format(response_format)
        format_type = format_config.get("type")
        if format_type == "json_schema":
            # Ensure schema includes additionalProperties=False to satisfy Azure validation
            schema = dict(format_config.get("schema", {}))  # type: ignore[assignment]
            schema.setdefault("additionalProperties", False)
            config_kwargs: dict[str, Any] = {
                "name": format_config.get("name") or "response",
                "schema": schema,
            }
            if "strict" in format_config:
                config_kwargs["strict"] = format_config["strict"]
            if "description" in format_config:
                config_kwargs["description"] = format_config["description"]
            return ResponseTextFormatConfigurationJsonSchema(**config_kwargs)
        if format_type == "json_object":
            return ResponseTextFormatConfigurationJsonObject()
        if format_type == "text":
            return ResponseTextFormatConfigurationText()

    raise ServiceInvalidRequestError("response_format must be a Pydantic model or mapping.")


def _convert_response_format(response_format: Mapping[str, Any]) -> dict[str, Any]:
    """Convert Chat style response_format into Responses text format config."""
    if "format" in response_format and isinstance(response_format["format"], Mapping):
        return dict(cast("Mapping[str, Any]", response_format["format"]))

    format_type = response_format.get("type")
    if format_type == "json_schema":
        schema_section = response_format.get("json_schema", response_format)
        if not isinstance(schema_section, Mapping):
            raise ServiceInvalidRequestError("json_schema response_format must be a mapping.")
        schema_section_typed = cast("Mapping[str, Any]", schema_section)
        schema: Any = schema_section_typed.get("schema")
        if schema is None:
            raise ServiceInvalidRequestError("json_schema response_format requires a schema.")
        name: str = str(
            schema_section_typed.get("name")
            or schema_section_typed.get("title")
            or (cast("Mapping[str, Any]", schema).get("title") if isinstance(schema, Mapping) else None)
            or "response"
        )
        format_config: dict[str, Any] = {
            "type": "json_schema",
            "name": name,
            "schema": schema,
        }
        if "strict" in schema_section:
            format_config["strict"] = schema_section["strict"]
        if "description" in schema_section and schema_section["description"] is not None:
            format_config["description"] = schema_section["description"]
        return format_config

    if format_type in {"json_object", "text"}:
        return {"type": format_type}

    raise ServiceInvalidRequestError("Unsupported response_format provided for Azure AI client.")
