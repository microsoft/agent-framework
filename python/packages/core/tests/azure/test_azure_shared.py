# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework import Content
from agent_framework.azure._shared import (
    _normalize_hosted_ids,
    _require_string,
    create_a2a_tool,
    create_azure_ai_search_tool,
    create_bing_tool,
    create_browser_automation_tool,
    create_code_interpreter_tool,
    create_fabric_data_agent_tool,
    create_file_search_tool,
    create_image_generation_tool,
    create_mcp_tool,
    create_memory_search_tool,
    create_openapi_tool,
    create_sharepoint_grounding_tool,
    create_web_search_tool,
    load_foundry_project_settings,
)


def test_require_string_success_and_failure() -> None:
    assert _require_string("value", "field") == "value"
    with pytest.raises(ValueError, match="'field' is required."):
        _require_string("", "field")


def test_normalize_hosted_ids_variants() -> None:
    assert _normalize_hosted_ids(
        "file-1",
        expected_content_type="hosted_file",
        content_id_field="file_id",
        parameter_name="file_ids",
    ) == ["file-1"]
    assert _normalize_hosted_ids(
        [Content.from_hosted_file(file_id="file-2"), "file-3"],
        expected_content_type="hosted_file",
        content_id_field="file_id",
        parameter_name="file_ids",
    ) == ["file-2", "file-3"]


def test_normalize_hosted_ids_invalid_content_type_raises() -> None:
    with pytest.raises(TypeError, match="hosted_vector_store"):
        _normalize_hosted_ids(
            Content.from_hosted_file(file_id="file-1"),
            expected_content_type="hosted_vector_store",
            content_id_field="vector_store_id",
            parameter_name="vector_store_ids",
        )


def test_create_code_interpreter_tool_normalizes_from_container() -> None:
    tool = create_code_interpreter_tool(container={"file_ids": ["file-1", "file-2"]})
    assert tool["container"]["file_ids"] == ["file-1", "file-2"]


def test_create_file_search_tool_with_content_and_requires_ids() -> None:
    tool = create_file_search_tool(
        vector_store_ids=[Content.from_hosted_vector_store(vector_store_id="vs-1"), "vs-2"],
        max_num_results=5,
    )
    assert tool["vector_store_ids"] == ["vs-1", "vs-2"]
    assert tool["max_num_results"] == 5

    with pytest.raises(ValueError, match="vector_store_ids"):
        create_file_search_tool(vector_store_ids=None)


def test_create_web_search_tool_with_location() -> None:
    tool = create_web_search_tool(user_location={"city": "Seattle", "country": "US"}, search_context_size="high")
    assert tool.search_context_size == "high"
    assert tool.user_location is not None
    assert tool.user_location.city == "Seattle"


def test_create_bing_tool_grounding_explicit_connection() -> None:
    tool = create_bing_tool(variant="grounding", project_connection_id="conn-1", market="en-US")
    config = tool["bing_grounding"]["search_configurations"][0]
    assert tool["type"] == "bing_grounding"
    assert config["project_connection_id"] == "conn-1"
    assert config["market"] == "en-US"


def test_create_bing_tool_custom_search_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID", "conn-custom")
    monkeypatch.setenv("BING_CUSTOM_SEARCH_INSTANCE_NAME", "instance-1")
    tool = create_bing_tool(variant="custom_search")
    config = tool["bing_custom_search_preview"]["search_configurations"][0]
    assert tool["type"] == "bing_custom_search_preview"
    assert config["project_connection_id"] == "conn-custom"
    assert config["instance_name"] == "instance-1"


def test_create_bing_tool_custom_search_requires_instance_name() -> None:
    with pytest.raises(ValueError, match="'instance_name' is required."):
        create_bing_tool(variant="custom_search", project_connection_id="conn-only")


def test_create_image_generation_tool_sets_values() -> None:
    tool = create_image_generation_tool(model="gpt-image-1", size="1024x1024", output_format="png", quality="high")
    assert tool["model"] == "gpt-image-1"
    assert tool["size"] == "1024x1024"
    assert tool["output_format"] == "png"
    assert tool["quality"] == "high"


def test_create_mcp_tool_with_approval_modes() -> None:
    tool = create_mcp_tool(
        name="my mcp",
        url="https://example.com",
        approval_mode={"always_require_approval": ["danger"], "never_require_approval": ["safe"]},
        allowed_tools=["safe"],
        headers={"Authorization": "Bearer token"},
    )
    assert tool["server_label"] == "my_mcp"
    assert tool["allowed_tools"] == ["safe"]
    assert "require_approval" in tool


def test_create_fabric_and_sharepoint_tools_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FABRIC_PROJECT_CONNECTION_ID", "fabric-conn")
    monkeypatch.setenv("SHAREPOINT_PROJECT_CONNECTION_ID", "sharepoint-conn")
    assert (
        create_fabric_data_agent_tool()["fabric_dataagent_preview"]["project_connections"][0]["project_connection_id"]
        == "fabric-conn"
    )
    assert (
        create_sharepoint_grounding_tool()["sharepoint_grounding_preview"]["project_connections"][0][
            "project_connection_id"
        ]
        == "sharepoint-conn"
    )


def test_create_azure_ai_search_tool_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SEARCH_PROJECT_CONNECTION_ID", "search-conn")
    monkeypatch.setenv("AI_SEARCH_INDEX_NAME", "index-1")
    tool = create_azure_ai_search_tool(query_type="simple")
    index = tool["azure_ai_search"]["indexes"][0]
    assert tool["type"] == "azure_ai_search"
    assert index["project_connection_id"] == "search-conn"
    assert index["index_name"] == "index-1"
    assert index["query_type"] == "simple"


def test_create_browser_automation_tool_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER_AUTOMATION_PROJECT_CONNECTION_ID", "browser-conn")
    tool = create_browser_automation_tool()
    assert tool["browser_automation_preview"]["connection"]["project_connection_id"] == "browser-conn"


def test_create_openapi_tool_with_auth() -> None:
    tool = create_openapi_tool(
        name="status_api",
        spec={"openapi": "3.0.0", "info": {"title": "Status", "version": "1.0.0"}, "paths": {}},
        description="Status endpoint",
        auth={"type": "anonymous"},
    )
    assert tool["type"] == "openapi"
    assert tool["openapi"]["name"] == "status_api"
    assert tool["openapi"]["auth"]["type"] == "anonymous"


def test_create_a2a_tool_and_memory_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("A2A_PROJECT_CONNECTION_ID", "a2a-conn")
    monkeypatch.setenv("A2A_ENDPOINT", "https://a2a.example.com")
    a2a_tool = create_a2a_tool()
    assert a2a_tool["project_connection_id"] == "a2a-conn"
    assert a2a_tool["base_url"] == "https://a2a.example.com"

    memory_tool = create_memory_search_tool(memory_store_name="store-1", scope="scope-1", update_delay=5)
    assert memory_tool["type"] == "memory_search"
    assert memory_tool["update_delay"] == 5


def test_load_foundry_project_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://project.example.com")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    settings = load_foundry_project_settings()
    assert settings["project_endpoint"] == "https://project.example.com"
    assert settings["model_deployment_name"] == "gpt-4o"
