# Copyright (c) Microsoft. All rights reserved.

import os
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, ClassVar, Literal, cast

from agent_framework import (
    Content,
    FunctionTool,
    HostedCodeInterpreterTool,
    HostedFileSearchTool,
    HostedImageGenerationTool,
    HostedMCPTool,
    HostedWebSearchTool,
    ToolProtocol,
    get_logger,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidRequestError
from azure.ai.agents.models import (
    BingCustomSearchTool,
    BingGroundingTool,
    CodeInterpreterToolDefinition,
    McpTool,
    ToolDefinition,
)
from azure.ai.agents.models import FileSearchTool as AgentsFileSearchTool
from azure.ai.projects.models import (
    ApproximateLocation,
    CodeInterpreterTool,
    CodeInterpreterToolAuto,
    ImageGenTool,
    ImageGenToolInputImageMask,
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

logger = get_logger("agent_framework.azure")


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


def _extract_project_connection_id(additional_properties: dict[str, Any] | None) -> str | None:
    """Extract project_connection_id from HostedMCPTool additional_properties.

    Checks for both direct 'project_connection_id' key (programmatic usage)
    and 'connection.name' structure (declarative/YAML usage).

    Args:
        additional_properties: The additional_properties dict from a HostedMCPTool.

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
            case FunctionTool():
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
                vector_stores = [inp for inp in tool.inputs or [] if inp.type == "hosted_vector_store"]
                if vector_stores:
                    file_search = AgentsFileSearchTool(vector_store_ids=[vs.vector_store_id for vs in vector_stores])  # type: ignore[misc]
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
        inputs = [Content.from_hosted_vector_store(vector_store_id=vs_id) for vs_id in vector_store_ids]
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
        # Hosted MCP tools are defined on the Azure agent, no local handling needed
        # Azure may not return full server_url, so skip conversion
        return None

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
        inputs = [Content.from_hosted_vector_store(vector_store_id=vs_id) for vs_id in vector_store_ids]
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
        # Hosted MCP tools are defined on the Azure agent, no local handling needed
        # Azure may not return full server_url, so skip conversion
        return None

    if tool_type == "function":
        # Function tools from SDK don't have implementations - skip
        return None

    # Unknown tool type - convert to dict if possible
    if hasattr(tool, "as_dict"):
        return tool.as_dict()  # type: ignore[union-attr]
    return {"type": tool_type} if tool_type else {}


def from_azure_ai_tools(tools: Sequence[Tool | dict[str, Any]] | None) -> list[ToolProtocol | dict[str, Any]]:
    """Parses and converts a sequence of Azure AI tools into Agent Framework compatible tools.

    Args:
        tools: A sequence of tool objects or dictionaries
            defining the tools to be parsed. Can be None.

    Returns:
        list[ToolProtocol | dict[str, Any]]: A list of converted tools compatible with the
            Agent Framework.
    """
    agent_tools: list[ToolProtocol | dict[str, Any]] = []
    if not tools:
        return agent_tools
    for tool in tools:
        # Handle raw dictionary tools
        tool_dict = tool if isinstance(tool, dict) else dict(tool)
        tool_type = tool_dict.get("type")

        if tool_type == "mcp":
            mcp_tool = cast(MCPTool, tool_dict)
            approval_mode: Literal["always_require", "never_require"] | dict[str, set[str]] | None = None
            if require_approval := mcp_tool.get("require_approval"):
                if require_approval == "always":
                    approval_mode = "always_require"
                elif require_approval == "never":
                    approval_mode = "never_require"
                elif isinstance(require_approval, dict):
                    approval_mode = {}
                    if "always" in require_approval:
                        approval_mode["always_require_approval"] = set(require_approval["always"].get("tool_names", []))  # type: ignore
                    if "never" in require_approval:
                        approval_mode["never_require_approval"] = set(require_approval["never"].get("tool_names", []))  # type: ignore

            # Preserve project_connection_id in additional_properties
            additional_props: dict[str, Any] | None = None
            if project_connection_id := mcp_tool.get("project_connection_id"):
                additional_props = {"connection": {"name": project_connection_id}}

            agent_tools.append(
                HostedMCPTool(
                    name=mcp_tool.get("server_label", "").replace("_", " "),
                    url=mcp_tool.get("server_url", ""),
                    description=mcp_tool.get("server_description"),
                    headers=mcp_tool.get("headers"),
                    allowed_tools=mcp_tool.get("allowed_tools"),
                    approval_mode=approval_mode,  # type: ignore
                    additional_properties=additional_props,
                )
            )
        elif tool_type == "code_interpreter":
            ci_tool = cast(CodeInterpreterTool, tool_dict)
            container = ci_tool.get("container", {})
            ci_inputs: list[Content] = []
            if "file_ids" in container:
                for file_id in container["file_ids"]:
                    ci_inputs.append(Content.from_hosted_file(file_id=file_id))

            agent_tools.append(HostedCodeInterpreterTool(inputs=ci_inputs if ci_inputs else None))  # type: ignore
        elif tool_type == "file_search":
            fs_tool = cast(ProjectsFileSearchTool, tool_dict)
            fs_inputs: list[Content] = []
            if "vector_store_ids" in fs_tool:
                for vs_id in fs_tool["vector_store_ids"]:
                    fs_inputs.append(Content.from_hosted_vector_store(vector_store_id=vs_id))

            agent_tools.append(
                HostedFileSearchTool(
                    inputs=fs_inputs if fs_inputs else None,  # type: ignore
                    max_results=fs_tool.get("max_num_results"),
                )
            )
        elif tool_type == "web_search_preview":
            ws_tool = cast(WebSearchPreviewTool, tool_dict)
            additional_properties: dict[str, Any] = {}
            if user_location := ws_tool.get("user_location"):
                additional_properties["user_location"] = {
                    "city": user_location.get("city"),
                    "country": user_location.get("country"),
                    "region": user_location.get("region"),
                    "timezone": user_location.get("timezone"),
                }

            agent_tools.append(HostedWebSearchTool(additional_properties=additional_properties))
        else:
            agent_tools.append(tool_dict)
    return agent_tools


def to_azure_ai_tools(
    tools: Sequence[ToolProtocol | MutableMapping[str, Any]] | None,
) -> list[Tool | dict[str, Any]]:
    """Converts Agent Framework tools into Azure AI compatible tools.

    Args:
        tools: A sequence of Agent Framework tool objects or dictionaries
            defining the tools to be converted. Can be None.

    Returns:
        list[Tool | dict[str, Any]]: A list of converted tools compatible with Azure AI.
    """
    azure_tools: list[Tool | dict[str, Any]] = []
    if not tools:
        return azure_tools

    for tool in tools:
        if isinstance(tool, ToolProtocol):
            match tool:
                case HostedMCPTool():
                    azure_tools.append(_prepare_mcp_tool_for_azure_ai(tool))
                case HostedCodeInterpreterTool():
                    file_ids: list[str] = []
                    if tool.inputs:
                        for tool_input in tool.inputs:
                            if tool_input.type == "hosted_file":
                                file_ids.append(tool_input.file_id)  # type: ignore[misc, arg-type]
                    container = CodeInterpreterToolAuto(file_ids=file_ids if file_ids else None)
                    ci_tool: CodeInterpreterTool = CodeInterpreterTool(container=container)
                    azure_tools.append(ci_tool)
                case FunctionTool():
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
                case HostedFileSearchTool():
                    if not tool.inputs:
                        raise ValueError("HostedFileSearchTool requires inputs to be specified.")
                    vector_store_ids: list[str] = [
                        inp.vector_store_id  # type: ignore[misc]
                        for inp in tool.inputs
                        if inp.type == "hosted_vector_store"
                    ]
                    if not vector_store_ids:
                        raise ValueError(
                            "HostedFileSearchTool requires inputs to be of type `Content` with "
                            "type 'hosted_vector_store'."
                        )
                    fs_tool: ProjectsFileSearchTool = ProjectsFileSearchTool(vector_store_ids=vector_store_ids)
                    if tool.max_results:
                        fs_tool["max_num_results"] = tool.max_results
                    azure_tools.append(fs_tool)
                case HostedWebSearchTool():
                    ws_tool: WebSearchPreviewTool = WebSearchPreviewTool()
                    if tool.additional_properties:
                        location: dict[str, str] | None = (
                            tool.additional_properties.get("user_location", None)
                            if tool.additional_properties
                            else None
                        )
                        if location:
                            ws_tool.user_location = ApproximateLocation(
                                city=location.get("city"),
                                country=location.get("country"),
                                region=location.get("region"),
                                timezone=location.get("timezone"),
                            )
                    azure_tools.append(ws_tool)
                case HostedImageGenerationTool():
                    opts = tool.options or {}
                    addl = tool.additional_properties or {}
                    # Azure ImageGenTool requires the constant model "gpt-image-1"
                    ig_tool: ImageGenTool = ImageGenTool(
                        model=opts.get("model_id", "gpt-image-1"),  # type: ignore
                        size=cast(
                            Literal["1024x1024", "1024x1536", "1536x1024", "auto"] | None, opts.get("image_size")
                        ),
                        output_format=cast(Literal["png", "webp", "jpeg"] | None, opts.get("media_type")),
                        input_image_mask=(
                            ImageGenToolInputImageMask(
                                image_url=addl.get("input_image_mask", {}).get("image_url"),
                                file_id=addl.get("input_image_mask", {}).get("file_id"),
                            )
                            if isinstance(addl.get("input_image_mask"), dict)
                            else None
                        ),
                        quality=cast(Literal["low", "medium", "high", "auto"] | None, addl.get("quality")),
                        background=cast(Literal["transparent", "opaque", "auto"] | None, addl.get("background")),
                        output_compression=cast(int | None, addl.get("output_compression")),
                        moderation=cast(Literal["auto", "low"] | None, addl.get("moderation")),
                        partial_images=opts.get("streaming_count"),
                    )
                    azure_tools.append(ig_tool)
                case _:
                    logger.debug("Unsupported tool passed (type: %s)", type(tool))
        else:
            # Handle raw dictionary tools
            tool_dict = tool if isinstance(tool, dict) else dict(tool)
            azure_tools.append(tool_dict)

    return azure_tools


def _prepare_mcp_tool_for_azure_ai(tool: HostedMCPTool) -> MCPTool:
    """Convert HostedMCPTool to Azure AI MCPTool format.

    Args:
        tool: The HostedMCPTool to convert.

    Returns:
        MCPTool: The converted Azure AI MCPTool.
    """
    mcp: MCPTool = MCPTool(server_label=tool.name.replace(" ", "_"), server_url=str(tool.url))

    if tool.description:
        mcp["server_description"] = tool.description

    # Check for project_connection_id in additional_properties (for Azure AI Foundry connections)
    project_connection_id = _extract_project_connection_id(tool.additional_properties)
    if project_connection_id:
        mcp["project_connection_id"] = project_connection_id
    elif tool.headers:
        # Only use headers if no project_connection_id is available
        # Note: Azure AI Agent Service may reject headers with sensitive info
        mcp["headers"] = tool.headers

    if tool.allowed_tools:
        mcp["allowed_tools"] = list(tool.allowed_tools)

    if tool.approval_mode:
        match tool.approval_mode:
            case str():
                mcp["require_approval"] = "always" if tool.approval_mode == "always_require" else "never"
            case _:
                if always_require_approvals := tool.approval_mode.get("always_require_approval"):
                    mcp["require_approval"] = {"always": {"tool_names": list(always_require_approvals)}}
                if never_require_approvals := tool.approval_mode.get("never_require_approval"):
                    mcp["require_approval"] = {"never": {"tool_names": list(never_require_approvals)}}

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
