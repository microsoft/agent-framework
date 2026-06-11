# Copyright (c) Microsoft. All rights reserved.

"""Tests for MCP-based skills (MCPSkillsSource, MCPSkill, MCPSkillResource)."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import (
    BlobResourceContents,
    ErrorData,
    ReadResourceResult,
    TextResourceContents,
)
from pydantic import AnyUrl

from agent_framework import MCPSkill, MCPSkillResource, MCPSkillsSource
from agent_framework._skills import _parse_mcp_skill_index

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

SAMPLE_SKILL_MD = """\
---
name: unit-converter
description: Convert between common units.
---
# Unit Converter

Body content here.
"""

SAMPLE_SKILL_INDEX = json.dumps({
    "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
    "skills": [
        {
            "name": "unit-converter",
            "type": "skill-md",
            "description": "Convert between common units.",
            "url": "skill://unit-converter/SKILL.md",
        }
    ],
})


def _make_text_result(text: str, uri: str = "skill://test") -> ReadResourceResult:
    """Create a ReadResourceResult with a single TextResourceContents."""
    return ReadResourceResult(contents=[TextResourceContents(uri=AnyUrl(uri), text=text, mimeType="text/markdown")])


def _make_blob_result(
    data: bytes,
    uri: str = "skill://test",
    mime_type: str = "application/octet-stream",
) -> ReadResourceResult:
    """Create a ReadResourceResult with a single BlobResourceContents."""
    return ReadResourceResult(
        contents=[BlobResourceContents(uri=AnyUrl(uri), blob=base64.b64encode(data).decode(), mimeType=mime_type)]
    )


def _make_empty_result() -> ReadResourceResult:
    """Create a ReadResourceResult with no contents."""
    return ReadResourceResult(contents=[])


def _make_client(**read_resource_responses: ReadResourceResult) -> AsyncMock:
    """Create a mock ClientSession whose read_resource returns different results per URI.

    Args:
        **read_resource_responses: Mapping of URI string to ReadResourceResult.
            Any URI not in this mapping raises McpError with the MCP-spec
            "Resource not found" code (-32002).
    """
    client = AsyncMock()

    async def _read_resource(uri: AnyUrl) -> ReadResourceResult:
        uri_str = str(uri)
        if uri_str in read_resource_responses:
            return read_resource_responses[uri_str]
        raise McpError(error=ErrorData(code=-32002, message=f"Resource not found: {uri_str}"))

    client.read_resource = AsyncMock(side_effect=_read_resource)
    return client


# ---------------------------------------------------------------------------
# _parse_mcp_skill_index tests
# ---------------------------------------------------------------------------


class TestParseMCPSkillIndex:
    """Tests for the _parse_mcp_skill_index helper."""

    def test_parses_valid_index(self) -> None:
        index = _parse_mcp_skill_index(SAMPLE_SKILL_INDEX)
        assert index.schema == "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
        assert len(index.skills) == 1
        assert index.skills[0].name == "unit-converter"
        assert index.skills[0].type == "skill-md"
        assert index.skills[0].url == "skill://unit-converter/SKILL.md"

    def test_parses_empty_skills_array(self) -> None:
        index = _parse_mcp_skill_index('{"$schema": "test", "skills": []}')
        assert index.skills == []

    def test_parses_missing_skills_key(self) -> None:
        index = _parse_mcp_skill_index('{"$schema": "test"}')
        assert index.skills == []

    def test_raises_on_non_object(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON object"):
            _parse_mcp_skill_index("[]")

    def test_raises_on_invalid_json(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_mcp_skill_index("not json")

    def test_skips_non_dict_entries(self) -> None:
        index = _parse_mcp_skill_index('{"skills": ["not-a-dict", {"name": "ok", "type": "skill-md"}]}')
        assert len(index.skills) == 1
        assert index.skills[0].name == "ok"


# ---------------------------------------------------------------------------
# MCPSkillResource tests
# ---------------------------------------------------------------------------


class TestMCPSkillResource:
    """Tests for MCPSkillResource."""

    @pytest.mark.asyncio
    async def test_read_text_content(self) -> None:
        result = _make_text_result("hello world")
        resource = MCPSkillResource(name="test.md", result=result)
        content = await resource.read()
        assert content == "hello world"

    @pytest.mark.asyncio
    async def test_read_binary_content(self) -> None:
        data = bytes([0x01, 0x02, 0x03, 0x04])
        result = _make_blob_result(data)
        resource = MCPSkillResource(name="icon.bin", result=result)
        content = await resource.read()
        assert content == data

    @pytest.mark.asyncio
    async def test_read_empty_returns_none(self) -> None:
        result = _make_empty_result()
        resource = MCPSkillResource(name="empty", result=result)
        content = await resource.read()
        assert content is None

    @pytest.mark.asyncio
    async def test_read_multiple_text_contents_joined(self) -> None:
        result = ReadResourceResult(
            contents=[
                TextResourceContents(uri=AnyUrl("skill://a"), text="line1", mimeType="text/plain"),
                TextResourceContents(uri=AnyUrl("skill://b"), text="line2", mimeType="text/plain"),
            ]
        )
        resource = MCPSkillResource(name="multi", result=result)
        content = await resource.read()
        assert content == "line1\nline2"

    @pytest.mark.asyncio
    async def test_binary_takes_precedence_over_text(self) -> None:
        data = b"\xff\xfe"
        result = ReadResourceResult(
            contents=[
                TextResourceContents(uri=AnyUrl("skill://a"), text="text", mimeType="text/plain"),
                BlobResourceContents(
                    uri=AnyUrl("skill://b"),
                    blob=base64.b64encode(data).decode(),
                    mimeType="application/octet-stream",
                ),
            ]
        )
        resource = MCPSkillResource(name="mixed", result=result)
        content = await resource.read()
        # The implementation iterates all contents checking for BlobResourceContents
        # first, so when both text and binary are present, binary is returned.
        assert content == data


# ---------------------------------------------------------------------------
# MCPSkill tests
# ---------------------------------------------------------------------------


class TestMCPSkill:
    """Tests for MCPSkill."""

    @pytest.mark.asyncio
    async def test_get_content_fetches_and_caches(self) -> None:
        client = _make_client(**{"skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD)})
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://unit-converter/SKILL.md", client=client)

        content1 = await skill.get_content()
        content2 = await skill.get_content()

        assert "Body content here." in content1
        assert content1 == content2
        # Only one MCP call should be made (cached)
        assert client.read_resource.call_count == 1

    @pytest.mark.asyncio
    async def test_get_content_raises_on_empty(self) -> None:
        client = _make_client(**{"skill://empty/SKILL.md": _make_empty_result()})
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="empty-skill", description="Empty skill.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://empty/SKILL.md", client=client)

        with pytest.raises(ValueError, match="no text content"):
            await skill.get_content()

    @pytest.mark.asyncio
    async def test_get_resource_text(self) -> None:
        client = _make_client(**{
            "skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD),
            "skill://unit-converter/references/checklist.md": _make_text_result("- check thing 1\n- check thing 2"),
        })
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://unit-converter/SKILL.md", client=client)

        resource = await skill.get_resource("references/checklist.md")
        assert resource is not None
        content = await resource.read()
        assert content == "- check thing 1\n- check thing 2"

    @pytest.mark.asyncio
    async def test_get_resource_binary(self) -> None:
        data = bytes([0x01, 0x02, 0x03, 0x04])
        client = _make_client(**{
            "skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD),
            "skill://unit-converter/assets/icon.bin": _make_blob_result(data),
        })
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://unit-converter/SKILL.md", client=client)

        resource = await skill.get_resource("assets/icon.bin")
        assert resource is not None
        content = await resource.read()
        assert content == data

    @pytest.mark.asyncio
    async def test_get_resource_unknown_returns_none(self) -> None:
        client = _make_client(**{"skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD)})
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://unit-converter/SKILL.md", client=client)

        resource = await skill.get_resource("references/does-not-exist.md")
        assert resource is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name",
        [
            "../escape.md",
            "references/../../escape.md",
            "..",
            "..\\escape.md",
            "/etc/passwd",
            "http://attacker.example.com/payload",
        ],
    )
    async def test_get_resource_path_traversal_returns_none(self, name: str) -> None:
        # Register a permissive mock that would happily return content for any URI,
        # so the test fails unless the client-side validation rejects the name
        # before issuing the read.
        client = AsyncMock()
        client.read_resource = AsyncMock(return_value=_make_text_result("should never be returned"))

        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://unit-converter/SKILL.md", client=client)

        resource = await skill.get_resource(name)
        assert resource is None
        client.read_resource.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_resource_empty_name_returns_none(self) -> None:
        client = _make_client()
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)

        assert await skill.get_resource("") is None
        assert await skill.get_resource("   ") is None

    @pytest.mark.asyncio
    async def test_get_script_returns_none(self) -> None:
        client = _make_client()
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)

        assert await skill.get_script("anything") is None

    def test_compute_skill_root_uri_strips_suffix(self) -> None:
        assert MCPSkill._compute_skill_root_uri("skill://unit-converter/SKILL.md") == "skill://unit-converter/"

    def test_compute_skill_root_uri_trailing_slash(self) -> None:
        assert MCPSkill._compute_skill_root_uri("skill://unit-converter/") == "skill://unit-converter/"

    def test_compute_skill_root_uri_no_suffix_adds_slash(self) -> None:
        assert MCPSkill._compute_skill_root_uri("skill://unit-converter") == "skill://unit-converter/"


# ---------------------------------------------------------------------------
# MCPSkillsSource tests
# ---------------------------------------------------------------------------


class TestMCPSkillsSource:
    """Tests for MCPSkillsSource."""

    @pytest.mark.asyncio
    async def test_index_based_discovery_returns_skill(self) -> None:
        client = _make_client(**{
            "skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json"),
            "skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD),
        })
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()

        assert len(skills) == 1
        assert skills[0].frontmatter.name == "unit-converter"
        assert skills[0].frontmatter.description == "Convert between common units."

        # Content is fetched on demand, not during discovery
        content = await skills[0].get_content()
        assert "Body content here." in content

    @pytest.mark.asyncio
    async def test_no_index_returns_empty(self) -> None:
        client = _make_client()  # No resources at all
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()
        assert skills == []

    @pytest.mark.asyncio
    async def test_does_not_read_skill_md_during_discovery(self) -> None:
        # Index points to a skill, but SKILL.md is not registered on the server.
        # Discovery should succeed because it only reads the index.
        client = _make_client(**{"skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()

        assert len(skills) == 1
        assert skills[0].frontmatter.name == "unit-converter"

    @pytest.mark.asyncio
    async def test_invalid_name_is_skipped(self) -> None:
        index_json = json.dumps({
            "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
            "skills": [
                {
                    "name": "UnitConverter",  # Invalid: uppercase
                    "type": "skill-md",
                    "description": "Convert between common units.",
                    "url": "skill://UnitConverter/SKILL.md",
                }
            ],
        })
        client = _make_client(**{"skill://index.json": _make_text_result(index_json, uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()
        assert skills == []

    @pytest.mark.asyncio
    async def test_missing_required_fields_is_skipped(self) -> None:
        index_json = json.dumps({
            "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
            "skills": [
                {
                    "name": "unit-converter",
                    "type": "skill-md",
                    # Missing description and url
                }
            ],
        })
        client = _make_client(**{"skill://index.json": _make_text_result(index_json, uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()
        assert skills == []

    @pytest.mark.asyncio
    async def test_unsupported_type_is_skipped(self) -> None:
        index_json = json.dumps({
            "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
            "skills": [
                {
                    "name": "some-skill",
                    "type": "archive",
                    "description": "Packaged skill.",
                    "url": "skill://some-skill.tar.gz",
                }
            ],
        })
        client = _make_client(**{"skill://index.json": _make_text_result(index_json, uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()
        assert skills == []

    @pytest.mark.asyncio
    async def test_template_type_is_skipped(self) -> None:
        index_json = json.dumps({
            "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
            "skills": [
                {
                    "type": "mcp-resource-template",
                    "description": "Per-product documentation skill",
                    "url": "skill://docs/{product}/SKILL.md",
                }
            ],
        })
        client = _make_client(**{"skill://index.json": _make_text_result(index_json, uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()
        assert skills == []

    @pytest.mark.asyncio
    async def test_empty_index_returns_empty(self) -> None:
        client = _make_client(**{"skill://index.json": _make_text_result('{"skills": []}', uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()
        assert skills == []

    @pytest.mark.asyncio
    async def test_malformed_index_json_returns_empty(self) -> None:
        client = _make_client(**{"skill://index.json": _make_text_result("not valid json", uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()
        assert skills == []

    @pytest.mark.asyncio
    async def test_sibling_text_resource(self) -> None:
        client = _make_client(**{
            "skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json"),
            "skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD),
            "skill://unit-converter/references/checklist.md": _make_text_result("- check thing 1\n- check thing 2"),
        })
        source = MCPSkillsSource(client=client)
        skill = (await source.get_skills())[0]
        resource = await skill.get_resource("references/checklist.md")
        assert resource is not None
        content = await resource.read()
        assert content == "- check thing 1\n- check thing 2"

    @pytest.mark.asyncio
    async def test_sibling_binary_resource(self) -> None:
        data = bytes([0x01, 0x02, 0x03, 0x04])
        client = _make_client(**{
            "skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json"),
            "skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD),
            "skill://unit-converter/assets/icon.bin": _make_blob_result(data),
        })
        source = MCPSkillsSource(client=client)
        skill = (await source.get_skills())[0]
        resource = await skill.get_resource("assets/icon.bin")
        assert resource is not None
        content = await resource.read()
        assert content == data


# ---------------------------------------------------------------------------
# McpError code branching tests
# ---------------------------------------------------------------------------


class TestMCPSkillsSourceErrorCodeBranching:
    """Tests that MCPSkillsSource and MCPSkill branch on McpError.error.code.

    Only "not found" codes (RESOURCE_NOT_FOUND -32002, METHOD_NOT_FOUND -32601)
    should be silently swallowed as "no skills available." Other McpError codes
    and non-McpError exceptions must propagate so that auth failures, server
    crashes, and connection drops are visible.
    """

    @pytest.mark.asyncio
    async def test_index_method_not_found_returns_empty(self) -> None:
        """METHOD_NOT_FOUND (-32601) -> server doesn't support resources/read."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=-32601, message="Method not found")))
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()
        assert skills == []

    @pytest.mark.asyncio
    async def test_index_resource_not_found_returns_empty(self) -> None:
        """MCP-spec "Resource not found" (-32002) -> server has no index."""
        client = AsyncMock()
        client.read_resource = AsyncMock(
            side_effect=McpError(error=ErrorData(code=-32002, message="Resource not found"))
        )
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills()
        assert skills == []

    @pytest.mark.asyncio
    async def test_index_invalid_params_propagates(self) -> None:
        """INVALID_PARAMS (-32602) is a real bug, must propagate (not "not found")."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=-32602, message="Invalid params")))
        source = MCPSkillsSource(client=client)
        with pytest.raises(McpError):
            await source.get_skills()

    @pytest.mark.asyncio
    async def test_index_internal_error_propagates(self) -> None:
        """INTERNAL_ERROR (-32603) must propagate, not silently return empty."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=-32603, message="Internal error")))
        source = MCPSkillsSource(client=client)
        with pytest.raises(McpError):
            await source.get_skills()

    @pytest.mark.asyncio
    async def test_index_connection_closed_propagates(self) -> None:
        """CONNECTION_CLOSED (-32000) must propagate."""
        client = AsyncMock()
        client.read_resource = AsyncMock(
            side_effect=McpError(error=ErrorData(code=-32000, message="Connection closed"))
        )
        source = MCPSkillsSource(client=client)
        with pytest.raises(McpError):
            await source.get_skills()

    @pytest.mark.asyncio
    async def test_index_generic_error_code_propagates(self) -> None:
        """Generic handler error (code 0) must propagate."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=0, message="Some handler error")))
        source = MCPSkillsSource(client=client)
        with pytest.raises(McpError):
            await source.get_skills()

    @pytest.mark.asyncio
    async def test_index_non_mcp_error_propagates(self) -> None:
        """Non-McpError exceptions (connection drop, timeout) must propagate."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=ConnectionError("connection lost"))
        source = MCPSkillsSource(client=client)
        with pytest.raises(ConnectionError):
            await source.get_skills()

    @pytest.mark.asyncio
    async def test_get_resource_internal_error_propagates(self) -> None:
        """McpError with INTERNAL_ERROR on get_resource must propagate."""
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=-32603, message="Server crashed")))
        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)
        with pytest.raises(McpError):
            await skill.get_resource("references/file.md")

    @pytest.mark.asyncio
    async def test_get_resource_not_found_returns_none(self) -> None:
        """McpError with RESOURCE_NOT_FOUND (-32002) on get_resource returns None."""
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource = AsyncMock(
            side_effect=McpError(error=ErrorData(code=-32002, message="Resource not found"))
        )
        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)
        result = await skill.get_resource("references/file.md")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_resource_connection_error_propagates(self) -> None:
        """A plain ConnectionError on get_resource must propagate, not return None."""
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=ConnectionError("connection lost"))
        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)
        with pytest.raises(ConnectionError):
            await skill.get_resource("references/file.md")

    @pytest.mark.asyncio
    async def test_get_resource_timeout_error_propagates(self) -> None:
        """A TimeoutError on get_resource must propagate, not return None."""
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=TimeoutError("read timed out"))
        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)
        with pytest.raises(TimeoutError):
            await skill.get_resource("references/file.md")

    @pytest.mark.asyncio
    async def test_get_resource_generic_mcp_error_propagates(self) -> None:
        """McpError with a generic code (0) on get_resource must propagate."""
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=0, message="Handler error")))
        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)
        with pytest.raises(McpError):
            await skill.get_resource("references/file.md")

    @pytest.mark.asyncio
    async def test_index_timeout_error_propagates(self) -> None:
        """A TimeoutError reading skill://index.json must propagate."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=TimeoutError("read timed out"))
        source = MCPSkillsSource(client=client)
        with pytest.raises(TimeoutError):
            await source.get_skills()
