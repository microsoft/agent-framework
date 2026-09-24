# Copyright (c) Microsoft. All rights reserved.

"""Tests for MCP-based skills (MCPSkillsSource, MCPSkill, MCPSkillResource)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import (
    BlobResourceContents,
    ErrorData,
    ReadResourceResult,
    TextResourceContents,
)
from pydantic import AnyUrl

from agent_framework import CachingSkillsSource, MCPSkill, MCPSkillResource, MCPSkillsSource, SkillsSourceContext
from agent_framework._skills import _fully_unquote, _parse_mcp_skill_index

from .conftest import MockAgent

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


# Shared context for exercising skill sources where the agent/session are irrelevant.
_SOURCE_CTX = SkillsSourceContext(agent=MockAgent())  # type: ignore[abstract]  # pyrefly: ignore[bad-instantiation]

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


@pytest.fixture(autouse=True)
def _clear_resource_name_decode_cache() -> Iterator[None]:
    _fully_unquote.cache_clear()
    yield
    _fully_unquote.cache_clear()


def _encode(depth: int) -> str:
    """Return ``"A"`` percent-encoded *depth* times, e.g. ``%2541`` for depth 2."""
    return "%" + "25" * (depth - 1) + "41"


# ---------------------------------------------------------------------------
# _fully_unquote tests
# ---------------------------------------------------------------------------


class TestFullyUnquote:
    """Tests for recursive, cached resource-name decoding."""

    def test_reuses_cached_layers(self) -> None:
        assert _fully_unquote("guide%2520one.md") == "guide one.md"

        with patch("agent_framework._skills.unquote", wraps=unquote) as decode:
            # A repeated name is served entirely from the cache.
            assert _fully_unquote("guide%2520one.md") == "guide one.md"
            decode.assert_not_called()
            # A different name reaching a cached layer ("guide%20one.md") decodes only its first layer.
            assert _fully_unquote("guide%25%32%30one.md") == "guide one.md"
            decode.assert_called_once_with("guide%25%32%30one.md")

    @pytest.mark.parametrize("depths", [(32, 33), (33, 32)])
    def test_cached_layers_preserve_depth_limit(self, depths: tuple[int, int]) -> None:
        for depth in depths:
            assert _fully_unquote(_encode(depth)) == ("A" if depth <= 32 else None)


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


class TestMCPSkillsExperimentalStage:
    """Tests confirming the MCP skills types remain experimental (MCP_SKILLS)."""

    def test_docstrings_include_experimental_warning(self) -> None:
        assert MCPSkillResource.__doc__ is not None
        assert MCPSkill.__doc__ is not None
        assert MCPSkillsSource.__doc__ is not None

        assert ".. warning:: Experimental" in MCPSkillResource.__doc__
        assert ".. warning:: Experimental" in MCPSkill.__doc__
        assert ".. warning:: Experimental" in MCPSkillsSource.__doc__

    def test_feature_metadata_is_set(self) -> None:
        for cls in (MCPSkillResource, MCPSkill, MCPSkillsSource):
            assert getattr(cls, "__feature_stage__", None) == "experimental"
            assert getattr(cls, "__feature_id__", None) == "MCP_SKILLS"


class TestMCPSkillResource:
    """Tests for MCPSkillResource."""

    async def test_read_text_content(self) -> None:
        result = _make_text_result("hello world")
        resource = MCPSkillResource(name="test.md", result=result)
        content = await resource.read()
        assert content == "hello world"

    async def test_read_binary_content(self) -> None:
        data = bytes([0x01, 0x02, 0x03, 0x04])
        result = _make_blob_result(data)
        resource = MCPSkillResource(name="icon.bin", result=result)
        content = await resource.read()
        assert content == data

    async def test_read_empty_returns_none(self) -> None:
        result = _make_empty_result()
        resource = MCPSkillResource(name="empty", result=result)
        content = await resource.read()
        assert content is None

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

    async def test_get_content_raises_on_empty(self) -> None:
        client = _make_client(**{"skill://empty/SKILL.md": _make_empty_result()})
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="empty-skill", description="Empty skill.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://empty/SKILL.md", client=client)

        with pytest.raises(ValueError, match="no text content"):
            await skill.get_content()

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

    async def test_get_resource_unknown_returns_none(self) -> None:
        client = _make_client(**{"skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD)})
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://unit-converter/SKILL.md", client=client)

        resource = await skill.get_resource("references/does-not-exist.md")
        assert resource is None

    @pytest.mark.parametrize(
        "name",
        [
            "../escape.md",
            "references/../../escape.md",
            "..",
            "..\\escape.md",
            "/etc/passwd",
            "http://attacker.example.com/payload",
            "%2e%2e/escape.md",
            "%2E./escape.md",
            ".%2e/escape.md",
            "references/%2e%2e/escape.md",
            "references%2f..%2f..%2fescape.md",
            "%2e%2e%5cescape.md",
            "%252e%252e%252fescape.md",
            "%25252e%25252e/escape.md",
            "%2fescape.md",
            "%5cescape.md",
            "%68ttp%3a%2f%2fexample.com/other",
            "..?download=1",
            "..#fragment",
            "%2e%2e%3fdownload=1",
            "references%3f/../../escape.md",
            "references%3f/%2e%2e/%2e%2e/escape.md",
            "references%23/%2e%2e/%2e%2e/escape.md",
            "references%3f%2f%2e%2e%2f%2e%2e%2fescape.md",
            "references%23%5c%2e%2e%5c%2e%2e%5cescape.md",
            "references%253f%252f%252e%252e%252f%252e%252e%252fescape.md",
            "references%2523%252f%252e%252e%252f%252e%252e%252fescape.md",
            "references%3f/%252e%252e/%252e%252e/escape.md",
            "references%3f/%2e%2e/%2e%2e/escape.md?version=1",
            "references%23/%2e%2e/%2e%2e/escape.md#section",
            "references%3f%2f%2e%2e%20",
            ".\t./escape.md",
            ".%09./escape.md",
            "references/\x00/guide.md",
            ".. ",
            ".%2e ",
            "%2e%2e ",
            "..%20",
            "%252e%252e%2520",
            "references/.. ",
            "references/.. ?version=1",
            "references/guide.md?value=%00",
            "references/guide.md#value=%2509",
            "references/guide.md?value=%C2%85",
            "references/%2500guide.md?version=1",
            "references/guide.md?version=1#value=%2509",
            "references/guide.md#section?value=%2509",
        ],
    )
    @pytest.mark.parametrize(
        "skill_md_uri",
        [
            "skill://unit-converter/SKILL.md",
            "skill://unit-converter/private/SKILL.md",
            "https://example.com/skills/private/SKILL.md",
            "file:///skills/private/SKILL.md",
            "custom:skills/private/SKILL.md",
        ],
    )
    async def test_get_resource_path_traversal_returns_none(self, name: str, skill_md_uri: str) -> None:
        # Register a permissive mock that would happily return content for any URI,
        # so the test fails unless the client-side validation rejects the name
        # before issuing the read.
        client = AsyncMock()
        client.read_resource = AsyncMock(return_value=_make_text_result("should never be returned"))

        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri=skill_md_uri, client=client)

        resource = await skill.get_resource(name)
        assert resource is None
        client.read_resource.assert_not_called()

    @pytest.mark.parametrize(
        "name",
        [
            "references/guide.md",
            "references\\guide.md",
            "references/guide%20one.md",
            "references/v1.2/guide.md",
            "references/%2520.md",
            "references/100%.md",
            "references/guide.md?version=1#section",
            "references/guide%3fname.md",
            "references/guide%23name.md",
            "references/guide%253fname.md",
            "references/guide.md?example=/../../other.md",
            "references/guide.md#example=/../../other.md",
            "references/guide.md?example=%2e%2e%2f%2e%2e%2fother.md",
            "references/guide.md?src=https://example.com/other",
            "references/guide%2520one.md?value=%2520#section%2520",
            "references/guide%253fname.md#section?value=%2520",
            "references/guide.md?",
            "references/guide.md#",
            "references/guide.md ",
        ],
    )
    @pytest.mark.parametrize(
        "root",
        [
            "skill://unit-converter/",
            "skill://unit-converter/private/",
            "https://example.com/skills/private/",
            "file:///skills/private/",
            "custom:skills/private/",
        ],
    )
    async def test_get_resource_preserves_safe_names_and_schemes(self, name: str, root: str) -> None:
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource.return_value = _make_text_result("safe content")
        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri=root + "SKILL.md", client=client)

        resource = await skill.get_resource(name)

        assert resource is not None
        assert resource.name == name
        assert await resource.read() == "safe content"
        client.read_resource.assert_awaited_once_with(AnyUrl(root + name.replace("\\", "/")))

    @pytest.mark.parametrize("depth", [1, 31, 32, 33, 4096])
    @pytest.mark.parametrize(
        "template",
        ["references/{}.md", "references/guide.md?value={}", "references/guide.md#value={}", "../{}.md"],
    )
    async def test_get_resource_decoding_depth_is_bounded(self, depth: int, template: str) -> None:
        from agent_framework import SkillFrontmatter

        root = "skill://unit-converter/private/"
        client = AsyncMock()
        client.read_resource.return_value = _make_text_result("safe content")
        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri=root + "SKILL.md", client=client)
        name = template.format(_encode(depth))

        with patch("agent_framework._skills.unquote", wraps=unquote) as decode:
            resource = await skill.get_resource(name)

        # One pass decodes the unencoded part; the encoded part takes depth + 1 passes, capped at 33.
        assert decode.call_count == min(depth + 1, 33) + 1
        if depth <= 32 and not name.startswith("../"):
            assert resource is not None
            assert resource.name == name
            client.read_resource.assert_awaited_once_with(AnyUrl(root + name))
        else:
            assert resource is None
            client.read_resource.assert_not_called()

    async def test_get_resource_empty_name_returns_none(self) -> None:
        client = _make_client()
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)

        assert await skill.get_resource("") is None
        assert await skill.get_resource("   ") is None

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

    async def test_session_provider_resolves_live_session(self) -> None:
        # A session_provider is resolved on every fetch, so a skill built against
        # one session follows a reconnect that swaps the session object.
        from agent_framework import SkillFrontmatter

        old_client = _make_client(**{"skill://unit-converter/SKILL.md": _make_text_result("# Old\nold body")})
        new_client = _make_client(**{"skill://unit-converter/SKILL.md": _make_text_result("# New\nnew body")})
        current = {"session": old_client}

        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        skill = MCPSkill(
            frontmatter=fm,
            skill_md_uri="skill://unit-converter/SKILL.md",
            session_provider=lambda: current["session"],
        )

        # Swap the session (as a reconnect would) before the first fetch.
        current["session"] = new_client
        content = await skill.get_content()

        assert "new body" in content
        old_client.read_resource.assert_not_called()
        new_client.read_resource.assert_called_once()

    def test_requires_exactly_one_of_client_or_session_provider(self) -> None:
        from agent_framework import SkillFrontmatter

        fm = SkillFrontmatter(name="unit-converter", description="Convert between common units.")
        client = _make_client()

        with pytest.raises(ValueError, match="exactly one"):
            MCPSkill(frontmatter=fm, skill_md_uri="skill://x/SKILL.md")
        with pytest.raises(ValueError, match="exactly one"):
            MCPSkill(
                frontmatter=fm,
                skill_md_uri="skill://x/SKILL.md",
                client=client,
                session_provider=lambda: client,
            )


# ---------------------------------------------------------------------------
# MCPSkillsSource tests
# ---------------------------------------------------------------------------


class TestMCPSkillsSource:
    """Tests for MCPSkillsSource."""

    @pytest.mark.parametrize(
        "uri",
        [
            "https://example.com/skills/SKILL.md",
            "file:///skills/SKILL.md",
            "custom:skills/SKILL.md",
        ],
    )
    async def test_index_preserves_mcp_resource_schemes(self, uri: str) -> None:
        index = json.loads(SAMPLE_SKILL_INDEX)
        index["skills"][0]["url"] = uri
        client = _make_client(**{
            "skill://index.json": _make_text_result(json.dumps(index)),
            uri: _make_text_result(SAMPLE_SKILL_MD),
        })
        source = MCPSkillsSource(client=client)

        skills = await source.get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        assert await skills[0].get_content() == SAMPLE_SKILL_MD
        assert str(client.read_resource.call_args.args[0]) == uri

    async def test_index_based_discovery_returns_skill(self) -> None:
        client = _make_client(**{
            "skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json"),
            "skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD),
        })
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        assert skills[0].frontmatter.name == "unit-converter"
        assert skills[0].frontmatter.description == "Convert between common units."

        # Content is fetched on demand, not during discovery
        content = await skills[0].get_content()
        assert "Body content here." in content

    async def test_no_index_returns_empty(self) -> None:
        client = _make_client()  # No resources at all
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_does_not_read_skill_md_during_discovery(self) -> None:
        # Index points to a skill, but SKILL.md is not registered on the server.
        # Discovery should succeed because it only reads the index.
        client = _make_client(**{"skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        assert skills[0].frontmatter.name == "unit-converter"

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
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

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
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_archive_missing_resource_is_skipped(self) -> None:
        # An archive entry whose archive resource is not available on the server
        # is skipped (the index is read, but the archive download fails).
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
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

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
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_empty_index_returns_empty(self) -> None:
        client = _make_client(**{"skill://index.json": _make_text_result('{"skills": []}', uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_malformed_index_json_returns_empty(self) -> None:
        client = _make_client(**{"skill://index.json": _make_text_result("not valid json", uri="skill://index.json")})
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_sibling_text_resource(self) -> None:
        client = _make_client(**{
            "skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json"),
            "skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD),
            "skill://unit-converter/references/checklist.md": _make_text_result("- check thing 1\n- check thing 2"),
        })
        source = MCPSkillsSource(client=client)
        skill = (await source.get_skills(_SOURCE_CTX))[0]
        resource = await skill.get_resource("references/checklist.md")
        assert resource is not None
        content = await resource.read()
        assert content == "- check thing 1\n- check thing 2"

    async def test_sibling_binary_resource(self) -> None:
        data = bytes([0x01, 0x02, 0x03, 0x04])
        client = _make_client(**{
            "skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json"),
            "skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD),
            "skill://unit-converter/assets/icon.bin": _make_blob_result(data),
        })
        source = MCPSkillsSource(client=client)
        skill = (await source.get_skills(_SOURCE_CTX))[0]
        resource = await skill.get_resource("assets/icon.bin")
        assert resource is not None
        content = await resource.read()
        assert content == data

    async def test_session_provider_resolves_live_session(self) -> None:
        # Discovery and the resulting skills' on-demand fetches both resolve the
        # provider, so a source built before a reconnect follows the swapped session.
        old_client = _make_client(**{
            "skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json"),
            "skill://unit-converter/SKILL.md": _make_text_result("# Old\nold body"),
        })
        new_client = _make_client(**{
            "skill://index.json": _make_text_result(SAMPLE_SKILL_INDEX, uri="skill://index.json"),
            "skill://unit-converter/SKILL.md": _make_text_result("# New\nnew body"),
        })
        current = {"session": old_client}

        source = MCPSkillsSource(session_provider=lambda: current["session"])
        skills = await source.get_skills(_SOURCE_CTX)
        assert len(skills) == 1

        # A reconnect swaps the session; the already-discovered skill must fetch
        # its content from the new session, not the closed one.
        current["session"] = new_client
        content = await skills[0].get_content()
        assert "new body" in content

    def test_requires_exactly_one_of_client_or_session_provider(self) -> None:
        client = _make_client()
        with pytest.raises(ValueError, match="exactly one"):
            MCPSkillsSource()
        with pytest.raises(ValueError, match="exactly one"):
            MCPSkillsSource(client=client, session_provider=lambda: client)


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

    async def test_index_method_not_found_returns_empty(self) -> None:
        """METHOD_NOT_FOUND (-32601) -> server doesn't support resources/read."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=-32601, message="Method not found")))
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_index_resource_not_found_returns_empty(self) -> None:
        """MCP-spec "Resource not found" (-32002) -> server has no index."""
        client = AsyncMock()
        client.read_resource = AsyncMock(
            side_effect=McpError(error=ErrorData(code=-32002, message="Resource not found"))
        )
        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_index_invalid_params_propagates(self) -> None:
        """INVALID_PARAMS (-32602) is a real bug, must propagate (not "not found")."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=-32602, message="Invalid params")))
        source = MCPSkillsSource(client=client)
        with pytest.raises(McpError):
            await source.get_skills(_SOURCE_CTX)

    async def test_index_internal_error_propagates(self) -> None:
        """INTERNAL_ERROR (-32603) must propagate, not silently return empty."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=-32603, message="Internal error")))
        source = MCPSkillsSource(client=client)
        with pytest.raises(McpError):
            await source.get_skills(_SOURCE_CTX)

    async def test_index_connection_closed_propagates(self) -> None:
        """CONNECTION_CLOSED (-32000) must propagate."""
        client = AsyncMock()
        client.read_resource = AsyncMock(
            side_effect=McpError(error=ErrorData(code=-32000, message="Connection closed"))
        )
        source = MCPSkillsSource(client=client)
        with pytest.raises(McpError):
            await source.get_skills(_SOURCE_CTX)

    async def test_index_generic_error_code_propagates(self) -> None:
        """Generic handler error (code 0) must propagate."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=0, message="Some handler error")))
        source = MCPSkillsSource(client=client)
        with pytest.raises(McpError):
            await source.get_skills(_SOURCE_CTX)

    async def test_index_non_mcp_error_propagates(self) -> None:
        """Non-McpError exceptions (connection drop, timeout) must propagate."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=ConnectionError("connection lost"))
        source = MCPSkillsSource(client=client)
        with pytest.raises(ConnectionError):
            await source.get_skills(_SOURCE_CTX)

    async def test_get_resource_internal_error_propagates(self) -> None:
        """McpError with INTERNAL_ERROR on get_resource must propagate."""
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=-32603, message="Server crashed")))
        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)
        with pytest.raises(McpError):
            await skill.get_resource("references/file.md")

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

    async def test_get_resource_connection_error_propagates(self) -> None:
        """A plain ConnectionError on get_resource must propagate, not return None."""
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=ConnectionError("connection lost"))
        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)
        with pytest.raises(ConnectionError):
            await skill.get_resource("references/file.md")

    async def test_get_resource_timeout_error_propagates(self) -> None:
        """A TimeoutError on get_resource must propagate, not return None."""
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=TimeoutError("read timed out"))
        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)
        with pytest.raises(TimeoutError):
            await skill.get_resource("references/file.md")

    async def test_get_resource_generic_mcp_error_propagates(self) -> None:
        """McpError with a generic code (0) on get_resource must propagate."""
        from agent_framework import SkillFrontmatter

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=McpError(error=ErrorData(code=0, message="Handler error")))
        fm = SkillFrontmatter(name="test-skill", description="Test.")
        skill = MCPSkill(frontmatter=fm, skill_md_uri="skill://test/SKILL.md", client=client)
        with pytest.raises(McpError):
            await skill.get_resource("references/file.md")

    async def test_index_timeout_error_propagates(self) -> None:
        """A TimeoutError reading skill://index.json must propagate."""
        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=TimeoutError("read timed out"))
        source = MCPSkillsSource(client=client)
        with pytest.raises(TimeoutError):
            await source.get_skills(_SOURCE_CTX)


# ---------------------------------------------------------------------------
# Archive skill helpers
# ---------------------------------------------------------------------------


def _make_zip(files: dict[str, bytes]) -> bytes:
    """Build an in-memory ZIP archive from a ``{path: content}`` mapping."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


ARCHIVE_SKILL_MD = """\
---
name: packaged-skill
description: A skill delivered as an archive.
---
# Packaged Skill

Instructions from an archive.
"""


def _make_archive_index(name: str, url: str, entry_type: str = "archive", *, digest: object = None) -> str:
    """Build a skill index JSON document with a single archive entry."""
    return json.dumps({
        "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
        "skills": [
            {
                "name": name,
                "type": entry_type,
                "description": "A skill delivered as an archive.",
                "url": url,
                **({"digest": digest} if digest is not None else {}),
            }
        ],
    })


def _archive_client(index_json: str, archive_url: str, archive_bytes: bytes, mime_type: str) -> AsyncMock:
    """Build a mock client that serves the index and a single archive blob resource."""
    return _make_client(**{
        "skill://index.json": _make_text_result(index_json, uri="skill://index.json"),
        str(AnyUrl(archive_url)): _make_blob_result(archive_bytes, uri=archive_url, mime_type=mime_type),
    })


# ---------------------------------------------------------------------------
# Archive skill discovery tests (through MCPSkillsSource)
# ---------------------------------------------------------------------------


class TestMCPSkillsSourceArchive:
    """Tests for archive-type skill discovery via MCPSkillsSource (in-memory)."""

    @pytest.mark.parametrize("newline", ("\n", "\r\n"))
    @pytest.mark.parametrize(
        "fields",
        (
            "description: First\ndescription: >-\n  Second",
            "description: |-\n  First\nDescription: Second",
            "description: Valid\nmetadata:\n  author: First\nmetadata:\n  author: Second",
            "description: Valid\nAllowed-Tools: read",
            'description: Valid\nallowed-tools: read\n"allowed-tools": other',
            "description: Valid\n'allowed-tools': other\nallowed-tools: read",
            'description: Valid\n"description": Other text',
            "'description': Other text\ndescription: Valid",
            'description: Valid\n"Allowed-Tools": other',
            'description: Valid\nmetadata:\n  author: First\n"metadata":\n  author: Second',
            "description: Valid\nlicense: MIT\n'license':",
            'description: Valid\ncompatibility: Any runtime\n"compatibility": Other runtime',
            'description: Valid\n"name": packaged-skill',
            'description: First\n"descrip\\u0074ion": Second',
            'description: First\n"\\x44escription": Second',
            "description: Valid\nmetadata: [unterminated",
            'description: "\\U00110000"',
            'description: "\\UFFFFFFFF"',
            'description: "\\uD800"',
            'description: "\\uDFFF"',
        ),
    )
    async def test_ambiguous_archive_frontmatter_is_skipped(self, fields: str, newline: str) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        content = f"---\nname: packaged-skill\n{fields}\n---\nBody."
        archive = _make_zip({"SKILL.md": content.replace("\n", newline).encode()})
        client = _archive_client(index, url, archive, "application/zip")

        skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert skills == []

    @pytest.mark.parametrize("newline", ("\n", "\r\n"))
    async def test_archive_yaml_escapes_and_invalid_metadata(
        self, newline: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        content = (
            '---\nname: packaged-skill\n"\\x64escription": "Read\\nfiles"\n'
            '"\\u006detadata": {author: First, "\\u0061uthor": Second, invalid: [value]}\n---\nBody.'
        )
        archive = _make_zip({"SKILL.md": content.replace("\n", newline).encode()})
        client = _archive_client(index, url, archive, "application/zip")

        skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        assert skills[0].frontmatter.description == "Read\nfiles"
        assert skills[0].frontmatter.metadata == {"author": "First"}
        assert len(caplog.records) == 2
        assert all(record.levelname == "WARNING" for record in caplog.records)

    @pytest.mark.parametrize("newline", ("\n", "\r\n"))
    async def test_archive_value_on_indented_next_line_is_preserved(self, newline: str) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        content = "---\nname: packaged-skill\ndescription:\n  'Read files'\nlicense: MIT\n---\nBody."
        archive = _make_zip({"SKILL.md": content.replace("\n", newline).encode()})
        client = _archive_client(index, url, archive, "application/zip")

        skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        assert skills[0].frontmatter.description == "Read files"
        assert skills[0].frontmatter.license == "MIT"

    @pytest.mark.parametrize("newline", ("\n", "\r\n"))
    @pytest.mark.parametrize("field", ("license", "compatibility", "allowed-tools"))
    async def test_archive_empty_optional_scalar_remains_none(self, field: str, newline: str) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        content = f"---\nname: packaged-skill\ndescription: Read files\n{field}:  \n---\nBody."
        archive = _make_zip({"SKILL.md": content.replace("\n", newline).encode()})
        client = _archive_client(index, url, archive, "application/zip")

        skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        assert skills[0].frontmatter.description == "Read files"
        assert skills[0].frontmatter.license is None
        assert skills[0].frontmatter.compatibility is None
        assert skills[0].frontmatter.allowed_tools is None

    @pytest.mark.parametrize("newline", ("\n", "\r\n"))
    @pytest.mark.parametrize("second_key", ("author", "Author"))
    @pytest.mark.parametrize("quote", ("", "'", '"'))
    async def test_archive_duplicate_metadata_keeps_first_value_and_warns(
        self, newline: str, second_key: str, quote: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        content = (
            f"---\n{quote}name{quote}: packaged-skill\n{quote}description{quote}: >-\n  Read\n  files\n"
            f"{quote}compatibility{quote}:\n  Any runtime\n{quote}allowed-tools{quote}: 'read'\n"
            f"{quote}metadata{quote}:\n"
            f"  author:\n    'First'\n  {second_key}: Second\n  author: Third\n  version: '1.0'\n"
            f"{quote}license{quote}: |-\n  MIT\n  License\n---\nBody."
        )
        archive = _make_zip({"SKILL.md": content.replace("\n", newline).encode()})
        client = _archive_client(index, url, archive, "application/zip")

        skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        expected = {"author": "First", "version": "1.0"}
        if second_key == "Author":
            expected["Author"] = "Second"
        assert skills[0].frontmatter.metadata == expected
        assert skills[0].frontmatter.description == "Read files"
        assert skills[0].frontmatter.license == "MIT\nLicense"
        assert skills[0].frontmatter.compatibility == "Any runtime"
        assert skills[0].frontmatter.allowed_tools == "read"
        assert "Body." in await skills[0].get_content()
        assert len(caplog.records) == (2 if second_key == "author" else 1)
        assert all(record.levelname == "WARNING" for record in caplog.records)
        assert all(
            "duplicate metadata key 'author'; keeping the first value" in record.getMessage()
            for record in caplog.records
        )

    @pytest.mark.parametrize("newline", ("\n", "\r\n"))
    @pytest.mark.parametrize(
        ("value", "expected"),
        (
            ("First", "First"),
            ("\n    'First'", "First"),
            ("|-\n    First\n    Second", "First\nSecond"),
            (">-\n    First\n    Second", "First Second"),
        ),
    )
    async def test_archive_yaml_metadata_scalar_formats(
        self, newline: str, value: str, expected: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        content = (
            "---\nname: packaged-skill\ndescription: Read files\n"
            f"metadata:\n  author: {value}\n  version: '1.0'\n---\nBody."
        )
        archive = _make_zip({"SKILL.md": content.replace("\n", newline).encode()})
        client = _archive_client(index, url, archive, "application/zip")

        skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        assert skills[0].frontmatter.metadata == {"author": expected, "version": "1.0"}
        assert "Body." in await skills[0].get_content()
        assert not caplog.records

    async def test_zip_archive_discovered_as_file_skill(self) -> None:
        from agent_framework import FileSkill

        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        archive = _make_zip({"SKILL.md": ARCHIVE_SKILL_MD.encode()})
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        skill = skills[0]
        assert isinstance(skill, FileSkill)
        assert skill.frontmatter.name == "packaged-skill"
        content = await skill.get_content()
        assert "Instructions from an archive." in content

    async def test_targz_archive_is_rejected(self) -> None:
        url = "skill://archives/packaged-skill.tar.gz"
        index = _make_archive_index("packaged-skill", url)
        archive = b"\x1f\x8b"
        client = _archive_client(index, url, archive, "application/gzip")

        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)

        assert skills == []

    async def test_tar_archive_is_rejected(self) -> None:
        url = "skill://archives/packaged-skill.tar"
        index = _make_archive_index("packaged-skill", url)
        archive = b"tar"
        client = _archive_client(index, url, archive, "application/x-tar")

        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)

        assert skills == []

    async def test_archive_reference_resource_is_readable(self) -> None:
        # A bundled reference file is served as an in-memory resource, read on demand.
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        archive = _make_zip({
            "SKILL.md": ARCHIVE_SKILL_MD.encode(),
            "references/refund-matrix.md": b"# Refund Matrix\nREF-CANARY-9001\n",
        })
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client)
        skill = (await source.get_skills(_SOURCE_CTX))[0]

        resource = await skill.get_resource("references/refund-matrix.md")
        assert resource is not None
        assert "REF-CANARY-9001" in await resource.read()

    async def test_wrapped_archive_root_is_discovered(self) -> None:
        # An archive whose SKILL.md sits under a top-level folder is still discovered,
        # and resources are resolved relative to the SKILL.md's directory.
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        archive = _make_zip({
            "packaged-skill/SKILL.md": ARCHIVE_SKILL_MD.encode(),
            "packaged-skill/references/doc.md": b"REF-CANARY-42\n",
        })
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client)
        skill = (await source.get_skills(_SOURCE_CTX))[0]

        assert skill.frontmatter.name == "packaged-skill"
        resource = await skill.get_resource("references/doc.md")
        assert resource is not None
        assert "REF-CANARY-42" in await resource.read()

    async def test_bundled_script_is_never_runnable(self) -> None:
        # An archive that bundles a .py script must not expose it as a runnable script,
        # nor (with default resource extensions) as a resource.
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        archive = _make_zip({
            "SKILL.md": ARCHIVE_SKILL_MD.encode(),
            "run.py": b"print('malicious')\n",
        })
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client)
        skill = (await source.get_skills(_SOURCE_CTX))[0]

        assert await skill.get_script("run.py") is None
        assert await skill.get_resource("run.py") is None
        content = await skill.get_content()
        assert "<available_scripts />" in content

    async def test_oversized_archive_download_is_skipped(self) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        archive = _make_zip({"SKILL.md": ARCHIVE_SKILL_MD.encode()})
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client, archive_max_size_bytes=8)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_archive_exceeding_file_count_is_skipped(self) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        archive = _make_zip({
            "SKILL.md": ARCHIVE_SKILL_MD.encode(),
            "a.md": b"a",
            "b.md": b"b",
        })
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client, archive_max_file_count=1)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_frontmatter_name_mismatch_is_skipped(self) -> None:
        # The SKILL.md frontmatter name must match the advertised entry name.
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        mismatched = ARCHIVE_SKILL_MD.replace("name: packaged-skill", "name: different-name")
        archive = _make_zip({"SKILL.md": mismatched.encode()})
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_frontmatter_name_mismatch_is_logged_as_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        mismatched = ARCHIVE_SKILL_MD.replace("name: packaged-skill", "name: different-name")
        archive = _make_zip({"SKILL.md": mismatched.encode()})
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client)
        with caplog.at_level("WARNING", logger="agent_framework._skills"):
            skills = await source.get_skills(_SOURCE_CTX)

        assert skills == []
        assert any(
            record.levelname == "WARNING" and "does not match the advertised entry name" in record.message
            for record in caplog.records
        )

    async def test_archive_without_skill_md_is_skipped(self) -> None:
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        archive = _make_zip({"readme.md": b"# not a skill\n"})
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_unsupported_archive_format_is_skipped(self) -> None:
        url = "skill://archives/packaged-skill.bin"
        index = _make_archive_index("packaged-skill", url)
        client = _archive_client(index, url, b"not-an-archive", "application/octet-stream")

        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []

    async def test_archive_download_internal_error_propagates(self) -> None:
        # A non-"not found" MCP error while downloading an archive must propagate,
        # not silently drop the skill (which would corrupt a CachingSkillsSource refresh).
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)

        async def _read_resource(uri: AnyUrl) -> ReadResourceResult:
            uri_str = str(uri)
            if uri_str == "skill://index.json":
                return _make_text_result(index, uri="skill://index.json")
            raise McpError(error=ErrorData(code=-32603, message="Internal error"))

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=_read_resource)

        source = MCPSkillsSource(client=client)
        with pytest.raises(McpError):
            await source.get_skills(_SOURCE_CTX)

    async def test_archive_download_connection_error_propagates(self) -> None:
        # A plain ConnectionError while downloading an archive must propagate.
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)

        async def _read_resource(uri: AnyUrl) -> ReadResourceResult:
            uri_str = str(uri)
            if uri_str == "skill://index.json":
                return _make_text_result(index, uri="skill://index.json")
            raise ConnectionError("connection lost")

        client = AsyncMock()
        client.read_resource = AsyncMock(side_effect=_read_resource)

        source = MCPSkillsSource(client=client)
        with pytest.raises(ConnectionError):
            await source.get_skills(_SOURCE_CTX)

    async def test_mixed_skill_md_and_archive_entries(self) -> None:
        archive_url = "skill://archives/packaged-skill.zip"
        index = json.dumps({
            "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
            "skills": [
                {
                    "name": "unit-converter",
                    "type": "skill-md",
                    "description": "Convert between common units.",
                    "url": "skill://unit-converter/SKILL.md",
                },
                {
                    "name": "packaged-skill",
                    "type": "archive",
                    "description": "A skill delivered as an archive.",
                    "url": archive_url,
                },
            ],
        })
        archive = _make_zip({"SKILL.md": ARCHIVE_SKILL_MD.encode()})
        client = _make_client(**{
            "skill://index.json": _make_text_result(index, uri="skill://index.json"),
            "skill://unit-converter/SKILL.md": _make_text_result(SAMPLE_SKILL_MD),
            str(AnyUrl(archive_url)): _make_blob_result(archive, uri=archive_url, mime_type="application/zip"),
        })

        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)

        names = sorted(s.frontmatter.name for s in skills)
        assert names == ["packaged-skill", "unit-converter"]

    async def test_zip_slip_archive_skips_whole_skill(self) -> None:
        # An archive with a path-traversal member is treated as hostile: the whole
        # skill is dropped (extraction raises, and _build_skill skips it).
        url = "skill://archives/packaged-skill.zip"
        index = _make_archive_index("packaged-skill", url)
        archive = _make_zip({
            "SKILL.md": ARCHIVE_SKILL_MD.encode(),
            "../evil.md": b"pwned",
        })
        client = _archive_client(index, url, archive, "application/zip")

        source = MCPSkillsSource(client=client)
        skills = await source.get_skills(_SOURCE_CTX)
        assert skills == []


class TestMCPSkillsSourceArchiveDigest:
    """Tests for archive digest verification through the MCP discovery pipeline."""

    @pytest.mark.parametrize("digest_mode", ["omitted", "null", "matching"])
    async def test_valid_archive_loads(self, digest_mode: str) -> None:
        from agent_framework._skills import _ArchiveEntryLoader

        url = "skill://archives/packaged-skill.zip"
        archive = _make_zip({
            "SKILL.md": ARCHIVE_SKILL_MD.encode(),
            "references/guide.md": b"Verified resource.",
        })
        index_data = json.loads(_make_archive_index("packaged-skill", url))
        if digest_mode == "null":
            index_data["skills"][0]["digest"] = None
        elif digest_mode == "matching":
            index_data["skills"][0]["digest"] = f"sha256:{hashlib.sha256(archive).hexdigest()}"
        client = _archive_client(json.dumps(index_data), url, archive, "application/zip")

        with patch.object(
            _ArchiveEntryLoader, "_verify_digest", wraps=_ArchiveEntryLoader._verify_digest
        ) as verify_digest:
            skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        if digest_mode == "matching":
            verify_digest.assert_called_once()
        else:
            verify_digest.assert_not_called()
        assert "Instructions from an archive." in await skills[0].get_content()
        resource = await skills[0].get_resource("references/guide.md")
        assert resource is not None
        assert await resource.read() == "Verified resource."

    @pytest.mark.parametrize(
        "digest",
        [
            "",
            " ",
            "0" * 64,
            "sha256:" + "a" * 63,
            "sha256:" + "a" * 65,
            "sha256:" + "g" * 64,
            "sha256:" + "A" * 64,
            "SHA256:" + "a" * 64,
            " sha256:" + "a" * 64,
            "sha256:" + "a" * 64 + "\n",
            "sha512:" + "a" * 128,
            123,
            False,
            [],
            {"value": "untrusted"},
        ],
    )
    async def test_invalid_digest_skips_before_extraction(
        self, digest: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        url = "skill://archives/packaged-skill.zip"
        archive = _make_zip({"SKILL.md": ARCHIVE_SKILL_MD.encode()})
        index = _make_archive_index("packaged-skill", url, digest=digest)
        client = _archive_client(index, url, archive, "application/zip")

        with patch("agent_framework._skills._ArchiveEntryLoader._build_skill") as build_skill:
            skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert skills == []
        build_skill.assert_not_called()
        assert "Skipping skill 'packaged-skill': archive digest must be" in caplog.text
        assert url not in caplog.text
        assert ARCHIVE_SKILL_MD not in caplog.text

    @pytest.mark.parametrize("digest_source", ["wrong", "original", "base64", "skill-md"])
    async def test_mismatched_digest_skips_before_extraction(
        self, digest_source: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        url = "skill://archives/packaged-skill.zip"
        original = _make_zip({"SKILL.md": ARCHIVE_SKILL_MD.encode()})
        tampered_content = ARCHIVE_SKILL_MD.replace("Instructions from an archive.", "Substituted instructions.")
        archive = _make_zip({"SKILL.md": tampered_content.encode()})
        digest_inputs = {
            "original": original,
            "base64": base64.b64encode(archive),
            "skill-md": tampered_content.encode(),
        }
        expected = "0" * 64 if digest_source == "wrong" else hashlib.sha256(digest_inputs[digest_source]).hexdigest()
        index = _make_archive_index("packaged-skill", url, digest=f"sha256:{expected}")
        client = _archive_client(index, url, archive, "application/zip")

        with patch("agent_framework._skills._ArchiveEntryLoader._build_skill") as build_skill:
            skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert skills == []
        build_skill.assert_not_called()
        assert "Skipping skill 'packaged-skill': archive digest does not match downloaded content" in caplog.text
        assert expected not in caplog.text
        assert "Substituted instructions." not in caplog.text
        assert url not in caplog.text
        assert client.read_resource.await_count == 2

    @pytest.mark.parametrize("digest", ["sha256:" + "0" * 64, "", 123])
    async def test_rejected_entry_does_not_hide_valid_archive(self, digest: object) -> None:
        url = "skill://archives/packaged-skill.zip"
        rejected_url = "skill://archives/rejected-skill.zip"
        archive = _make_zip({"SKILL.md": ARCHIVE_SKILL_MD.encode()})
        rejected_archive = _make_zip({
            "SKILL.md": ARCHIVE_SKILL_MD.replace("name: packaged-skill", "name: rejected-skill").encode()
        })
        index_data = json.loads(_make_archive_index("rejected-skill", rejected_url, digest=digest))
        index_data["skills"].extend(
            json.loads(
                _make_archive_index("packaged-skill", url, digest=f"sha256:{hashlib.sha256(archive).hexdigest()}")
            )["skills"]
        )
        client = _make_client(**{
            "skill://index.json": _make_text_result(json.dumps(index_data)),
            url: _make_blob_result(archive, uri=url, mime_type="application/zip"),
            rejected_url: _make_blob_result(rejected_archive, uri=rejected_url, mime_type="application/zip"),
        })

        skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        assert skills[0].frontmatter.name == "packaged-skill"

    async def test_size_guard_runs_before_hashing(self) -> None:
        url = "skill://archives/packaged-skill.zip"
        archive = _make_zip({"SKILL.md": ARCHIVE_SKILL_MD.encode()})
        index = _make_archive_index("packaged-skill", url, digest=f"sha256:{hashlib.sha256(archive).hexdigest()}")
        client = _archive_client(index, url, archive, "application/zip")
        source = MCPSkillsSource(client=client, archive_max_size_bytes=len(archive) - 1)

        with patch("agent_framework._skills.hashlib.sha256") as sha256:
            skills = await source.get_skills(_SOURCE_CTX)

        assert skills == []
        sha256.assert_not_called()

    @pytest.mark.parametrize(
        "failure", ["invalid-zip", "gzip", "traversal", "file-count", "uncompressed-size", "name-mismatch"]
    )
    async def test_matching_digest_does_not_bypass_archive_guards(self, failure: str) -> None:
        url = "skill://archives/packaged-skill.zip"
        files = {"SKILL.md": ARCHIVE_SKILL_MD.encode()}
        if failure == "traversal":
            files["../escape.md"] = b"Outside skill."
        elif failure == "file-count":
            files["extra.md"] = b"Extra resource."
        elif failure == "name-mismatch":
            files["SKILL.md"] = ARCHIVE_SKILL_MD.replace("name: packaged-skill", "name: another-skill").encode()
        archive = _make_zip(files)
        if failure == "invalid-zip":
            archive = b"PK\x03\x04invalid"
        elif failure == "gzip":
            archive = b"\x1f\x8b"
        index = _make_archive_index("packaged-skill", url, digest=f"sha256:{hashlib.sha256(archive).hexdigest()}")
        client = _archive_client(index, url, archive, "application/zip")
        source = MCPSkillsSource(
            client=client,
            archive_max_file_count=1 if failure == "file-count" else 20,
            archive_max_uncompressed_size_bytes=1 if failure == "uncompressed-size" else 1_000_000,
        )

        assert await source.get_skills(_SOURCE_CTX) == []

    @pytest.mark.parametrize("entry_type", ["archive", "ARCHIVE", " Archive "])
    async def test_verification_applies_to_all_archive_type_spellings(self, entry_type: str) -> None:
        url = "skill://archives/packaged-skill.zip"
        archive = _make_zip({"SKILL.md": ARCHIVE_SKILL_MD.encode()})
        index = _make_archive_index("packaged-skill", url, entry_type, digest="sha256:" + "0" * 64)
        client = _archive_client(index, url, archive, "application/zip")

        assert await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX) == []

    @pytest.mark.parametrize("digest", ["sha256:" + "0" * 64, 123])
    async def test_skill_md_digest_does_not_change_lazy_discovery(self, digest: object) -> None:
        index_data = json.loads(SAMPLE_SKILL_INDEX)
        index_data["skills"][0]["digest"] = digest
        client = _make_client(**{"skill://index.json": _make_text_result(json.dumps(index_data))})

        skills = await MCPSkillsSource(client=client).get_skills(_SOURCE_CTX)

        assert len(skills) == 1
        assert isinstance(skills[0], MCPSkill)
        client.read_resource.assert_awaited_once_with(AnyUrl("skill://index.json"))

    @pytest.mark.parametrize("refresh_failure", ["digest", "transport"])
    async def test_cache_refresh_handles_verification_and_transport_failures(
        self, refresh_failure: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = {"now": 1000.0}
        monkeypatch.setattr("time.monotonic", lambda: clock["now"])
        url = "skill://archives/packaged-skill.zip"
        archive = _make_zip({"SKILL.md": ARCHIVE_SKILL_MD.encode()})
        index = _make_archive_index("packaged-skill", url, digest=f"sha256:{hashlib.sha256(archive).hexdigest()}")
        client = _archive_client(index, url, archive, "application/zip")
        source = CachingSkillsSource(MCPSkillsSource(client=client), refresh_interval=timedelta(seconds=60))

        first = await source.get_skills(_SOURCE_CTX)
        assert len(first) == 1
        assert await source.get_skills(_SOURCE_CTX) is first
        client.read_resource.assert_any_await(AnyUrl(url))
        assert client.read_resource.await_count == 2

        tampered = _make_zip({
            "SKILL.md": ARCHIVE_SKILL_MD.replace("Instructions", "Substituted instructions").encode()
        })
        client.read_resource.side_effect = [
            _make_text_result(index),
            ConnectionError("connection lost")
            if refresh_failure == "transport"
            else _make_blob_result(tampered, uri=url, mime_type="application/zip"),
        ]
        clock["now"] += 60
        if refresh_failure == "transport":
            with pytest.raises(ConnectionError, match="connection lost"):
                await source.get_skills(_SOURCE_CTX)
            assert list(source._cached_skills.values()) == [first]
            client.read_resource.side_effect = [_make_text_result(index), _make_blob_result(archive, uri=url)]
            recovered = await source.get_skills(_SOURCE_CTX)
            assert len(recovered) == 1
            assert recovered is not first
        else:
            refreshed = await source.get_skills(_SOURCE_CTX)
            assert refreshed == []
            assert await source.get_skills(_SOURCE_CTX) is refreshed
            assert client.read_resource.await_count == 4


# ---------------------------------------------------------------------------
# Archive extractor unit tests
# ---------------------------------------------------------------------------


class TestArchiveExtractor:
    """Tests for the archive format detection and hardened in-memory extraction helpers."""

    def test_detect_format_from_magic_bytes(self) -> None:
        from agent_framework._skills import _ArchiveFormat, _detect_archive_format

        assert _detect_archive_format(b"\x1f\x8b\x08\x00", None, None) is _ArchiveFormat.UNKNOWN
        assert _detect_archive_format(b"PK\x03\x04rest", None, None) is _ArchiveFormat.ZIP

    def test_detect_format_from_media_type(self) -> None:
        from agent_framework._skills import _ArchiveFormat, _detect_archive_format

        assert _detect_archive_format(b"xx", "application/zip", None) is _ArchiveFormat.ZIP
        assert _detect_archive_format(b"xx", "application/x-tar", None) is _ArchiveFormat.UNKNOWN
        assert _detect_archive_format(b"xx", "application/gzip", None) is _ArchiveFormat.UNKNOWN

    def test_detect_format_from_url_suffix(self) -> None:
        from agent_framework._skills import _ArchiveFormat, _detect_archive_format

        assert _detect_archive_format(b"xx", None, "skill://a.zip") is _ArchiveFormat.ZIP
        assert _detect_archive_format(b"xx", None, "skill://a.tgz") is _ArchiveFormat.UNKNOWN
        assert _detect_archive_format(b"xx", None, "skill://a.tar") is _ArchiveFormat.UNKNOWN

    def test_detect_format_unknown(self) -> None:
        from agent_framework._skills import _ArchiveFormat, _detect_archive_format

        assert _detect_archive_format(b"xx", "text/plain", "skill://a.bin") is _ArchiveFormat.UNKNOWN

    def test_normalize_member_name_rejects_traversal(self) -> None:
        from agent_framework._skills import _normalize_archive_member_name

        # Parent-traversal escapes raise (zip-slip is treated as a hostile archive).
        with pytest.raises(ValueError, match="escape"):
            _normalize_archive_member_name("../evil.md")
        with pytest.raises(ValueError, match="escape"):
            _normalize_archive_member_name("..\\evil.md")
        with pytest.raises(ValueError, match="escape"):
            _normalize_archive_member_name("a/../../evil.md")
        # Degenerate non-file entries that cannot escape are skipped (return None).
        assert _normalize_archive_member_name("") is None
        assert _normalize_archive_member_name("/") is None
        assert _normalize_archive_member_name(".") is None
        # A leading-slash path is neutralized to a relative path.
        assert _normalize_archive_member_name("/etc/passwd") == "etc/passwd"
        # Backslashes are normalized and redundant segments collapsed.
        assert _normalize_archive_member_name("refs\\./doc.md") == "refs/doc.md"
        assert _normalize_archive_member_name("ok/file.md") == "ok/file.md"

    def test_zip_slip_member_raises(self) -> None:
        from agent_framework._skills import _ArchiveFormat, _extract_archive_to_memory

        # A member attempting a path-traversal escape aborts the whole extraction.
        archive = _make_zip({"safe.md": b"ok", "../evil.md": b"pwned"})
        with pytest.raises(ValueError, match="escape"):
            _extract_archive_to_memory(archive, _ArchiveFormat.ZIP, 20, 1024 * 1024)

    def test_leading_slash_member_is_neutralized(self) -> None:
        from agent_framework._skills import _ArchiveFormat, _extract_archive_to_memory

        archive = _make_zip({"/abs/file.md": b"data"})
        files = _extract_archive_to_memory(archive, _ArchiveFormat.ZIP, 20, 1024 * 1024)

        assert files == {"abs/file.md": b"data"}

    def test_file_count_limit_is_enforced(self) -> None:
        from agent_framework._skills import _ArchiveFormat, _extract_archive_to_memory

        archive = _make_zip({"a.md": b"a", "b.md": b"b", "c.md": b"c"})
        with pytest.raises(ValueError, match="file count"):
            _extract_archive_to_memory(archive, _ArchiveFormat.ZIP, 2, 1024 * 1024)

    def test_uncompressed_size_limit_is_enforced(self) -> None:
        from agent_framework._skills import _ArchiveFormat, _extract_archive_to_memory

        archive = _make_zip({"big.md": b"x" * 100})
        with pytest.raises(ValueError, match="uncompressed size"):
            _extract_archive_to_memory(archive, _ArchiveFormat.ZIP, 20, 10)

    def test_unknown_format_is_rejected(self) -> None:
        from agent_framework._skills import _ArchiveFormat, _extract_archive_to_memory

        with pytest.raises(ValueError, match="Unsupported skill archive format"):
            _extract_archive_to_memory(b"", _ArchiveFormat.UNKNOWN, 20, 1024 * 1024)
