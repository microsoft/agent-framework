# Copyright (c) Microsoft. All rights reserved.

import os
from collections.abc import MutableMapping, Sequence
from typing import Any, ClassVar

from agent_framework import (
    AIFunction,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedVectorStoreContent,
    HostedWebSearchTool,
    ToolProtocol,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError
from azure.ai.agents.models import (
    BingCustomSearchTool,
    BingGroundingTool,
    CodeInterpreterToolDefinition,
    FileSearchTool,
    McpTool,
    ToolDefinition,
)


class AzureAISettings(AFBaseSettings):
    """Azure AI Project settings.

    The settings are first loaded from environment variables with the prefix 'AZURE_AI_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

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

    env_prefix: ClassVar[str] = "AZURE_AI_"

    project_endpoint: str | None = None
    model_deployment_name: str | None = None


def to_azure_ai_agent_tools(
    tools: Sequence[ToolProtocol | MutableMapping[str, Any]] | None,
    run_options: dict[str, Any] | None = None,
) -> list[ToolDefinition | dict[str, Any]]:
    """Convert Agent Framework tools to Azure AI V1 SDK tool definitions.

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
        match tool:
            case AIFunction():
                tool_definitions.append(tool.to_json_schema_spec())  # type: ignore[reportUnknownArgumentType]
            case HostedWebSearchTool():
                additional_props = tool.additional_properties or {}
                config_args: dict[str, Any] = {}
                if count := additional_props.get("count"):
                    config_args["count"] = count
                if freshness := additional_props.get("freshness"):
                    config_args["freshness"] = freshness
                if market := additional_props.get("market"):
                    config_args["market"] = market
                if set_lang := additional_props.get("set_lang"):
                    config_args["set_lang"] = set_lang
                # Bing Grounding
                connection_id = additional_props.get("connection_id") or os.getenv("BING_CONNECTION_ID")
                # Custom Bing Search
                custom_connection_id = additional_props.get("custom_connection_id") or os.getenv(
                    "BING_CUSTOM_CONNECTION_ID"
                )
                custom_instance_name = additional_props.get("custom_instance_name") or os.getenv(
                    "BING_CUSTOM_INSTANCE_NAME"
                )
                bing_search: BingGroundingTool | BingCustomSearchTool | None = None
                if connection_id and not custom_connection_id and not custom_instance_name:
                    bing_search = BingGroundingTool(connection_id=connection_id, **config_args)
                if custom_connection_id and custom_instance_name:
                    bing_search = BingCustomSearchTool(
                        connection_id=custom_connection_id,
                        instance_name=custom_instance_name,
                        **config_args,
                    )
                if not bing_search:
                    raise ServiceInitializationError(
                        "Bing search tool requires either 'connection_id' for Bing Grounding "
                        "or both 'custom_connection_id' and 'custom_instance_name' for Custom Bing Search. "
                        "These can be provided via additional_properties or environment variables: "
                        "'BING_CONNECTION_ID', 'BING_CUSTOM_CONNECTION_ID', 'BING_CUSTOM_INSTANCE_NAME'"
                    )
                tool_definitions.extend(bing_search.definitions)
            case HostedCodeInterpreterTool():
                tool_definitions.append(CodeInterpreterToolDefinition())
            case HostedMCPTool():
                mcp_tool = McpTool(
                    server_label=tool.name.replace(" ", "_"),
                    server_url=str(tool.url),
                    allowed_tools=list(tool.allowed_tools) if tool.allowed_tools else [],
                )
                tool_definitions.extend(mcp_tool.definitions)
            case HostedFileSearchTool():
                vector_stores = [inp for inp in tool.inputs or [] if isinstance(inp, HostedVectorStoreContent)]
                if vector_stores:
                    file_search = FileSearchTool(vector_store_ids=[vs.vector_store_id for vs in vector_stores])
                    tool_definitions.extend(file_search.definitions)
                    # Set tool_resources for file search to work properly with Azure AI
                    if run_options is not None and "tool_resources" not in run_options:
                        run_options["tool_resources"] = file_search.resources
            case ToolDefinition():
                tool_definitions.append(tool)
            case dict():
                tool_definitions.append(tool)
            case _:
                raise ServiceInitializationError(f"Unsupported tool type: {type(tool)}")
    return tool_definitions


def from_azure_ai_agent_tools(
    tools: Sequence[ToolDefinition | dict[str, Any]] | None,
) -> list[ToolProtocol | dict[str, Any]]:
    """Convert Azure AI V1 SDK tool definitions to Agent Framework tools.

    Args:
        tools: Sequence of Azure AI V1 SDK tool definitions.

    Returns:
        List of Agent Framework tools.
    """
    if not tools:
        return []

    result: list[ToolProtocol | dict[str, Any]] = []
    for tool in tools:
        # Handle SDK objects
        if isinstance(tool, CodeInterpreterToolDefinition):
            result.append(HostedCodeInterpreterTool())
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


def _convert_dict_tool(tool: dict[str, Any]) -> ToolProtocol | dict[str, Any] | None:
    """Convert a dict-format Azure AI tool to Agent Framework tool."""
    tool_type = tool.get("type")

    if tool_type == "code_interpreter":
        return HostedCodeInterpreterTool()

    if tool_type == "file_search":
        file_search_config = tool.get("file_search", {})
        vector_store_ids = file_search_config.get("vector_store_ids", [])
        inputs = [HostedVectorStoreContent(vector_store_id=vs_id) for vs_id in vector_store_ids]
        return HostedFileSearchTool(inputs=inputs if inputs else None)  # type: ignore

    if tool_type == "bing_grounding":
        bing_config = tool.get("bing_grounding", {})
        connection_id = bing_config.get("connection_id")
        return HostedWebSearchTool(additional_properties={"connection_id": connection_id} if connection_id else None)

    if tool_type == "bing_custom_search":
        bing_config = tool.get("bing_custom_search", {})
        return HostedWebSearchTool(
            additional_properties={
                "custom_connection_id": bing_config.get("connection_id"),
                "custom_instance_name": bing_config.get("instance_name"),
            }
        )

    if tool_type == "mcp":
        mcp_config = tool.get("mcp", {})
        return HostedMCPTool(
            name=mcp_config.get("server_label", "mcp_server"),
            url=mcp_config.get("server_url", ""),
            allowed_tools=mcp_config.get("allowed_tools"),
        )

    if tool_type == "function":
        # Function tools are returned as dicts - users must provide implementations
        return tool

    # Unknown tool type - pass through
    return tool


def _convert_sdk_tool(tool: ToolDefinition) -> ToolProtocol | dict[str, Any] | None:
    """Convert an SDK-object Azure AI tool to Agent Framework tool."""
    tool_type = getattr(tool, "type", None)

    if tool_type == "code_interpreter":
        return HostedCodeInterpreterTool()

    if tool_type == "file_search":
        file_search_config = getattr(tool, "file_search", None)
        vector_store_ids = getattr(file_search_config, "vector_store_ids", []) if file_search_config else []
        inputs = [HostedVectorStoreContent(vector_store_id=vs_id) for vs_id in vector_store_ids]
        return HostedFileSearchTool(inputs=inputs if inputs else None)  # type: ignore

    if tool_type == "bing_grounding":
        bing_config = getattr(tool, "bing_grounding", None)
        connection_id = getattr(bing_config, "connection_id", None) if bing_config else None
        return HostedWebSearchTool(additional_properties={"connection_id": connection_id} if connection_id else None)

    if tool_type == "bing_custom_search":
        bing_config = getattr(tool, "bing_custom_search", None)
        return HostedWebSearchTool(
            additional_properties={
                "custom_connection_id": getattr(bing_config, "connection_id", None) if bing_config else None,
                "custom_instance_name": getattr(bing_config, "instance_name", None) if bing_config else None,
            }
        )

    if tool_type == "mcp":
        mcp_config = getattr(tool, "mcp", None)
        return HostedMCPTool(
            name=getattr(mcp_config, "server_label", "mcp_server") if mcp_config else "mcp_server",
            url=getattr(mcp_config, "server_url", "") if mcp_config else "",
            allowed_tools=getattr(mcp_config, "allowed_tools", None) if mcp_config else None,
        )

    if tool_type == "function":
        # Function tools from SDK don't have implementations - skip
        return None

    # Unknown tool type - convert to dict if possible
    if hasattr(tool, "as_dict"):
        return tool.as_dict()  # type: ignore[union-attr]
    return {"type": tool_type} if tool_type else {}
