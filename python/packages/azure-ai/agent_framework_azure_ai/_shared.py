# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, ClassVar, Literal, cast

from agent_framework import (
    AIFunction,
    Contents,
    HostedCodeInterpreterTool,
    HostedFileContent,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedVectorStoreContent,
    HostedWebSearchTool,
    ToolProtocol,
    get_logger,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInvalidRequestError
from azure.ai.projects.models import (
    ApproximateLocation,
    CodeInterpreterTool,
    CodeInterpreterToolAuto,
    FileSearchTool,
    FunctionTool,
    MCPTool,
    ResponseTextFormatConfigurationJsonObject,
    ResponseTextFormatConfigurationJsonSchema,
    ResponseTextFormatConfigurationText,
    Tool,
    WebSearchPreviewTool,
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

            agent_tools.append(
                HostedMCPTool(
                    name=mcp_tool.get("server_label", "").replace("_", " "),
                    url=mcp_tool.get("server_url", ""),
                    description=mcp_tool.get("server_description"),
                    headers=mcp_tool.get("headers"),
                    allowed_tools=mcp_tool.get("allowed_tools"),
                    approval_mode=approval_mode,  # type: ignore
                )
            )
        elif tool_type == "code_interpreter":
            ci_tool = cast(CodeInterpreterTool, tool_dict)
            container = ci_tool.get("container", {})
            ci_inputs: list[Contents] = []
            if "file_ids" in container:
                for file_id in container["file_ids"]:
                    ci_inputs.append(HostedFileContent(file_id=file_id))

            agent_tools.append(HostedCodeInterpreterTool(inputs=ci_inputs if ci_inputs else None))  # type: ignore
        elif tool_type == "file_search":
            fs_tool = cast(FileSearchTool, tool_dict)
            fs_inputs: list[Contents] = []
            if "vector_store_ids" in fs_tool:
                for vs_id in fs_tool["vector_store_ids"]:
                    fs_inputs.append(HostedVectorStoreContent(vector_store_id=vs_id))

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
                            if isinstance(tool_input, HostedFileContent):
                                file_ids.append(tool_input.file_id)
                    container = CodeInterpreterToolAuto(file_ids=file_ids if file_ids else None)
                    ci_tool: CodeInterpreterTool = CodeInterpreterTool(container=container)
                    azure_tools.append(ci_tool)
                case AIFunction():
                    params = tool.parameters()
                    params["additionalProperties"] = False
                    azure_tools.append(
                        FunctionTool(
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
                        inp.vector_store_id for inp in tool.inputs if isinstance(inp, HostedVectorStoreContent)
                    ]
                    if not vector_store_ids:
                        raise ValueError(
                            "HostedFileSearchTool requires inputs to be of type `HostedVectorStoreContent`."
                        )
                    fs_tool: FileSearchTool = FileSearchTool(vector_store_ids=vector_store_ids)
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

    if tool.headers:
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
