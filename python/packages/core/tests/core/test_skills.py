# Copyright (c) Microsoft. All rights reserved.

"""Tests for Agent Skills provider (file-based and code-defined)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent_framework import (
    AggregatingSkillsSource,
    DeduplicatingSkillsSource,
    FileSkill,
    FileSkillScript,
    FileSkillsSource,
    InlineSkill,
    InMemorySkillsSource,
    SessionContext,
    Skill,
    SkillResource,
    SkillScript,
    SkillScriptRunner,
    SkillsProvider,
)
from agent_framework._skills import (
    DEFAULT_RESOURCE_EXTENSIONS,
    DEFAULT_SCRIPT_EXTENSIONS,
    InlineSkillResource,
    InlineSkillScript,
    _create_script_element,
    _FileSkillResource,
)

pytestmark = pytest.mark.filterwarnings(r"ignore:\[SKILLS\].*:FutureWarning")

# Cross-platform absolute path prefix for tests
_ABS = "C:\\skills" if os.name == "nt" else "/skills"


async def _noop_script_runner(skill: Any, script: Any, args: Any = None) -> None:
    """No-op script runner for tests that need a SkillScriptRunner."""
    return


async def _init_provider(provider: SkillsProvider) -> SkillsProvider:
    """Initialize a provider's lazy state for testing.

    Calls the internal ``_get_or_create_context()`` method so that tests can
    immediately inspect the cached context via ``_cached_context``.
    """
    await provider._get_or_create_context()  # pyright: ignore[reportPrivateUsage]
    return provider


def _ctx(provider: SkillsProvider) -> tuple[dict[str, Skill], str | None, list[Any]]:
    """Return the cached context, asserting it was initialized.

    Converts the skills sequence to a dict keyed by name for convenient
    test assertions.
    """
    ctx = provider._cached_context  # pyright: ignore[reportPrivateUsage]
    assert ctx is not None, "_init_provider() must be called before accessing context"
    skills, instructions, tools = ctx
    return {s.name: s for s in skills}, instructions, tools


def _raw_skills(provider: SkillsProvider) -> Sequence[Skill]:
    """Return the raw skills sequence from the cached context."""
    ctx = provider._cached_context  # pyright: ignore[reportPrivateUsage]
    assert ctx is not None, "_init_provider() must be called before accessing context"
    return ctx[0]


def _symlinks_supported(tmp: Path) -> bool:
    """Return True if the current platform/environment supports symlinks."""
    test_target = tmp / "_symlink_test_target"
    test_link = tmp / "_symlink_test_link"
    try:
        test_target.write_text("test", encoding="utf-8")
        test_link.symlink_to(test_target)
        return True
    except (OSError, NotImplementedError):
        return False
    finally:
        test_link.unlink(missing_ok=True)
        test_target.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_skill(
    base: Path,
    name: str,
    description: str = "A test skill.",
    body: str = "# Instructions\nDo the thing.",
    *,
    extra_frontmatter: str = "",
    resources: dict[str, str] | None = None,
) -> Path:
    """Create a skill directory with SKILL.md and optional resource files."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    frontmatter = f"---\nname: {name}\ndescription: {description}\n{extra_frontmatter}---\n"
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(frontmatter + body, encoding="utf-8")

    if resources:
        for rel_path, content in resources.items():
            res_file = skill_dir / rel_path
            res_file.parent.mkdir(parents=True, exist_ok=True)
            res_file.write_text(content, encoding="utf-8")

    return skill_dir


def _read_and_parse_skill_file_for_test(skill_dir: Path) -> FileSkill:
    """Parse a SKILL.md file from the given directory, raising if invalid."""
    result = FileSkillsSource._read_and_parse_skill_file(str(skill_dir))
    assert result is not None, f"Failed to parse skill at {skill_dir}"
    name, description, content = result
    return FileSkill(
        name=name,
        description=description,
        content=content,
        path=str(skill_dir),
    )


async def _discover_file_skills_for_test(
    skill_paths: str | Path | list[str],
    *,
    resource_extensions: tuple[str, ...] | None = None,
    script_extensions: tuple[str, ...] | None = None,
    script_runner: Any = None,
) -> dict[str, FileSkill]:
    """Test helper: discover file skills and return as a dict keyed by name.

    Wraps ``FileSkillsSource(...).get_skills()`` for easy test migration
    from the removed ``FileSkillsSource._discover_file_skills()`` static method.
    """
    kwargs: dict[str, Any] = {}
    if resource_extensions is not None:
        kwargs["resource_extensions"] = resource_extensions
    if script_extensions is not None:
        kwargs["script_extensions"] = script_extensions
    if script_runner is not None:
        kwargs["script_runner"] = script_runner

    source = FileSkillsSource(skill_paths, **kwargs)
    skills = await source.get_skills()
    result: dict[str, FileSkill] = {}
    for s in skills:
        assert isinstance(s, FileSkill), f"Expected FileSkill, got {type(s).__name__}"
        result[s.name] = s
    return result


# ---------------------------------------------------------------------------
# Tests: module-level helper functions
# ---------------------------------------------------------------------------


class TestNormalizeResourcePath:
    """Tests for _normalize_resource_path."""

    def test_strips_dot_slash_prefix(self) -> None:
        assert FileSkillsSource._normalize_resource_path("./refs/doc.md") == "refs/doc.md"

    def test_replaces_backslashes(self) -> None:
        assert FileSkillsSource._normalize_resource_path("refs\\doc.md") == "refs/doc.md"

    def test_strips_dot_slash_and_replaces_backslashes(self) -> None:
        assert FileSkillsSource._normalize_resource_path(".\\refs\\doc.md") == "refs/doc.md"

    def test_no_change_for_clean_path(self) -> None:
        assert FileSkillsSource._normalize_resource_path("refs/doc.md") == "refs/doc.md"


class TestDiscoverResourceFiles:
    """Tests for _discover_resource_files (filesystem-based resource discovery)."""

    def test_discovers_md_files(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        refs = skill_dir / "refs"
        refs.mkdir()
        (refs / "FAQ.md").write_text("FAQ content", encoding="utf-8")
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert "refs/FAQ.md" in resources

    def test_excludes_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content", encoding="utf-8")
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert len(resources) == 0

    def test_discovers_multiple_extensions(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "data.json").write_text("{}", encoding="utf-8")
        (skill_dir / "config.yaml").write_text("key: val", encoding="utf-8")
        (skill_dir / "notes.txt").write_text("notes", encoding="utf-8")
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert len(resources) == 3
        names = set(resources)
        assert "data.json" in names
        assert "config.yaml" in names
        assert "notes.txt" in names

    def test_ignores_unsupported_extensions(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "image.png").write_bytes(b"\x89PNG")
        (skill_dir / "binary.exe").write_bytes(b"\x00")
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert len(resources) == 0

    def test_custom_extensions(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "data.json").write_text("{}", encoding="utf-8")
        (skill_dir / "notes.txt").write_text("notes", encoding="utf-8")
        resources = FileSkillsSource._discover_resource_files(str(skill_dir), extensions=(".json",))
        assert resources == ["data.json"]

    def test_discovers_nested_files(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        sub = skill_dir / "refs" / "deep"
        sub.mkdir(parents=True)
        (sub / "doc.md").write_text("deep doc", encoding="utf-8")
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert "refs/deep/doc.md" in resources

    def test_empty_directory(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert resources == []

    def test_default_extensions_match_constant(self) -> None:
        assert ".md" in DEFAULT_RESOURCE_EXTENSIONS
        assert ".json" in DEFAULT_RESOURCE_EXTENSIONS
        assert ".yaml" in DEFAULT_RESOURCE_EXTENSIONS
        assert ".yml" in DEFAULT_RESOURCE_EXTENSIONS
        assert ".csv" in DEFAULT_RESOURCE_EXTENSIONS
        assert ".xml" in DEFAULT_RESOURCE_EXTENSIONS
        assert ".txt" in DEFAULT_RESOURCE_EXTENSIONS


class TestTryParseSkillDocument:
    """Tests for _extract_frontmatter."""

    def test_valid_skill(self) -> None:
        content = "---\nname: test-skill\ndescription: A test skill.\n---\n# Body\nInstructions here."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is not None
        name, description = result
        assert name == "test-skill"
        assert description == "A test skill."

    def test_quoted_values(self) -> None:
        content = "---\nname: \"test-skill\"\ndescription: 'A test skill.'\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[0] == "test-skill"
        assert result[1] == "A test skill."

    def test_utf8_bom(self) -> None:
        content = "\ufeff---\nname: test-skill\ndescription: A test skill.\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[0] == "test-skill"

    def test_missing_frontmatter(self) -> None:
        content = "# Just a markdown file\nNo frontmatter here."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_missing_name(self) -> None:
        content = "---\ndescription: A test skill.\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_missing_description(self) -> None:
        content = "---\nname: test-skill\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_invalid_name_uppercase(self) -> None:
        content = "---\nname: Test-Skill\ndescription: A test skill.\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_invalid_name_starts_with_hyphen(self) -> None:
        content = "---\nname: -test-skill\ndescription: A test skill.\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_invalid_name_ends_with_hyphen(self) -> None:
        content = "---\nname: test-skill-\ndescription: A test skill.\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_name_too_long(self) -> None:
        long_name = "a" * 65
        content = f"---\nname: {long_name}\ndescription: A test skill.\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_description_too_long(self) -> None:
        long_desc = "a" * 1025
        content = f"---\nname: test-skill\ndescription: {long_desc}\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_extra_metadata_ignored(self) -> None:
        content = "---\nname: test-skill\ndescription: A test skill.\nauthor: someone\nversion: 1.0\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[0] == "test-skill"


# ---------------------------------------------------------------------------
# Tests: skill discovery and loading
# ---------------------------------------------------------------------------


class TestDiscoverAndLoadSkills:
    """Tests for file skill discovery via FileSkillsSource.get_skills()."""

    async def test_discovers_valid_skill(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        skills = await _discover_file_skills_for_test([str(tmp_path)])
        assert "my-skill" in skills
        assert skills["my-skill"].name == "my-skill"

    async def test_discovers_nested_skills(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        _write_skill(skills_dir, "skill-a")
        _write_skill(skills_dir, "skill-b")
        skills = await _discover_file_skills_for_test([str(skills_dir)])
        assert len(skills) == 2
        assert "skill-a" in skills
        assert "skill-b" in skills

    async def test_skips_invalid_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("No frontmatter here.", encoding="utf-8")
        skills = await _discover_file_skills_for_test([str(tmp_path)])
        assert len(skills) == 0

    async def test_skips_skill_with_name_directory_mismatch(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "wrong-dir-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: actual-skill-name\ndescription: A skill.\n---\nBody.", encoding="utf-8"
        )
        skills = await _discover_file_skills_for_test([str(tmp_path)])
        assert len(skills) == 0

    async def test_deduplicates_skill_names(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        _write_skill(dir1, "my-skill", body="First")
        _write_skill(dir2, "my-skill", body="Second")
        skills = await _discover_file_skills_for_test([str(dir1), str(dir2)])
        assert len(skills) == 1
        assert "First" in skills["my-skill"].content

    async def test_empty_directory(self, tmp_path: Path) -> None:
        skills = await _discover_file_skills_for_test([str(tmp_path)])
        assert len(skills) == 0

    async def test_nonexistent_directory(self) -> None:
        skills = await _discover_file_skills_for_test(["/nonexistent/path"])
        assert len(skills) == 0

    async def test_multiple_paths(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        _write_skill(dir1, "skill-a")
        _write_skill(dir2, "skill-b")
        skills = await _discover_file_skills_for_test([str(dir1), str(dir2)])
        assert len(skills) == 2

    async def test_depth_limit(self, tmp_path: Path) -> None:
        # Depth 0: tmp_path itself
        # Depth 1: tmp_path/level1
        # Depth 2: tmp_path/level1/level2 (should be found)
        # Depth 3: tmp_path/level1/level2/level3 (should NOT be found)
        deep = tmp_path / "level1" / "level2" / "level3"
        deep.mkdir(parents=True)
        (deep / "SKILL.md").write_text("---\nname: deep-skill\ndescription: Too deep.\n---\nBody.", encoding="utf-8")
        skills = await _discover_file_skills_for_test([str(tmp_path)])
        assert "deep-skill" not in skills

    async def test_skill_with_resources(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "my-skill",
            body="Instructions here.",
            resources={"refs/FAQ.md": "FAQ content"},
        )
        skills = await _discover_file_skills_for_test([str(tmp_path)])
        assert "my-skill" in skills
        assert [r.name for r in skills["my-skill"].resources] == ["refs/FAQ.md"]

    async def test_skill_discovers_all_resource_files(self, tmp_path: Path) -> None:
        """Resources are discovered by filesystem scan, not by markdown links."""
        _write_skill(
            tmp_path,
            "my-skill",
            body="No links here.",
            resources={"data.json": '{"key": "val"}', "refs/doc.md": "doc content"},
        )
        skills = await _discover_file_skills_for_test([str(tmp_path)])
        assert "my-skill" in skills
        resource_names = sorted(r.name for r in skills["my-skill"].resources)
        assert "data.json" in resource_names
        assert "refs/doc.md" in resource_names


# ---------------------------------------------------------------------------
# Tests: read_skill_resource
# ---------------------------------------------------------------------------


class TestReadSkillResource:
    """Tests for _FileSkillResource reading."""

    async def test_reads_valid_resource(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "my-skill",
            body="See [doc](refs/FAQ.md).",
            resources={"refs/FAQ.md": "FAQ content here"},
        )
        skill_dir = tmp_path / "my-skill"
        full_path = str(skill_dir / "refs" / "FAQ.md")
        resource = _FileSkillResource(name="refs/FAQ.md", full_path=full_path)
        content = await resource.read()
        assert content == "FAQ content here"

    async def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        full_path = str(skill_dir / "nonexistent.md")
        resource = _FileSkillResource(name="nonexistent.md", full_path=full_path)
        with pytest.raises(ValueError, match="not found"):
            await resource.read()

    async def test_reads_resource_with_exact_casing(self, tmp_path: Path) -> None:
        """Direct file read uses the resolved full path."""
        _write_skill(
            tmp_path,
            "my-skill",
            body="See [doc](refs/FAQ.md).",
            resources={"refs/FAQ.md": "FAQ content"},
        )
        skill_dir = tmp_path / "my-skill"
        full_path = str(skill_dir / "refs" / "FAQ.md")
        resource = _FileSkillResource(name="refs/FAQ.md", full_path=full_path)
        content = await resource.read()
        assert content == "FAQ content"

    def test_constructor_rejects_empty_full_path(self) -> None:
        with pytest.raises(ValueError, match="full_path cannot be empty"):
            _FileSkillResource(name="test.md", full_path="")

    def test_path_traversal_blocked_at_discovery(self, tmp_path: Path) -> None:
        """Path traversal is blocked by _discover_resource_files, not at read time."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (tmp_path / "secret.md").write_text("secret", encoding="utf-8")
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert not any("secret" in r for r in resources)


# ---------------------------------------------------------------------------
# Tests: _create_instructions
# ---------------------------------------------------------------------------


class TestBuildSkillsInstructionPrompt:
    """Tests for _create_instructions."""

    def test_returns_none_for_empty_skills(self) -> None:
        assert SkillsProvider._create_instructions(None, []) is None

    def test_default_prompt_contains_skills(self) -> None:
        skills = [
            InlineSkill(name="my-skill", description="Does stuff.", instructions="Body"),
        ]
        prompt = SkillsProvider._create_instructions(None, skills)
        assert prompt is not None
        assert "<name>my-skill</name>" in prompt
        assert "<description>Does stuff.</description>" in prompt
        assert "load_skill" in prompt

    def test_skills_sorted_alphabetically(self) -> None:
        skills = [
            InlineSkill(name="zebra", description="Z skill.", instructions="Body"),
            InlineSkill(name="alpha", description="A skill.", instructions="Body"),
        ]
        prompt = SkillsProvider._create_instructions(None, skills)
        assert prompt is not None
        alpha_pos = prompt.index("alpha")
        zebra_pos = prompt.index("zebra")
        assert alpha_pos < zebra_pos

    def test_xml_escapes_metadata(self) -> None:
        skills = [
            InlineSkill(name="my-skill", description='Uses <tags> & "quotes"', instructions="Body"),
        ]
        prompt = SkillsProvider._create_instructions(None, skills)
        assert prompt is not None
        assert "&lt;tags&gt;" in prompt
        assert "&amp;" in prompt

    def test_custom_prompt_template(self) -> None:
        skills = [
            InlineSkill(name="my-skill", description="Does stuff.", instructions="Body"),
        ]
        custom = "Custom header:\n{skills}\nCustom footer."
        prompt = SkillsProvider._create_instructions(custom, skills)
        assert prompt is not None
        assert prompt.startswith("Custom header:")
        assert prompt.endswith("Custom footer.")

    def test_invalid_prompt_template_raises(self) -> None:
        skills = [
            InlineSkill(name="my-skill", description="Does stuff.", instructions="Body"),
        ]
        with pytest.raises(ValueError, match="valid format string"):
            SkillsProvider._create_instructions("{invalid}", skills)

    def test_positional_placeholder_raises(self) -> None:
        skills = [
            InlineSkill(name="my-skill", description="Does stuff.", instructions="Body"),
        ]
        with pytest.raises(ValueError, match="valid format string"):
            SkillsProvider._create_instructions("Header {0} footer", skills)


# ---------------------------------------------------------------------------
# Tests: SkillsProvider (file-based)
# ---------------------------------------------------------------------------


class TestSkillsProvider:
    """Tests for file-based usage of SkillsProvider."""

    def test_default_source_id(self, tmp_path: Path) -> None:
        provider = SkillsProvider.from_paths(str(tmp_path))
        assert provider.source_id == "agent_skills"

    async def test_custom_source_id(self, tmp_path: Path) -> None:
        provider = SkillsProvider.from_paths(str(tmp_path), source_id="custom")
        assert provider.source_id == "custom"
        await _init_provider(provider)

    async def test_accepts_single_path_string(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        assert len(_ctx(provider)[0]) == 1

    async def test_accepts_sequence_of_paths(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        _write_skill(dir1, "skill-a")
        _write_skill(dir2, "skill-b")
        provider = SkillsProvider.from_paths([str(dir1), str(dir2)])
        await _init_provider(provider)
        assert len(_ctx(provider)[0]) == 2

    async def test_before_run_with_skills(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider.from_paths(str(tmp_path))
        context = SessionContext(input_messages=[])

        await provider.before_run(
            agent=AsyncMock(),
            session=AsyncMock(),
            context=context,
            state={},
        )

        assert len(context.instructions) == 1
        assert "my-skill" in context.instructions[0]
        assert len(context.tools) == 1
        tool_names = {t.name for t in context.tools}
        assert tool_names == {"load_skill"}

    async def test_before_run_without_skills(self, tmp_path: Path) -> None:
        provider = SkillsProvider.from_paths(str(tmp_path))
        context = SessionContext(input_messages=[])

        await provider.before_run(
            agent=AsyncMock(),
            session=AsyncMock(),
            context=context,
            state={},
        )

        assert len(context.instructions) == 0
        assert len(context.tools) == 0

    async def test_load_skill_returns_body(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill", body="Skill body content.")
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "my-skill")
        assert "Skill body content." in result

    async def test_load_skill_preserves_file_skill_content(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "my-skill",
            body="See [doc](refs/FAQ.md).",
            resources={"refs/FAQ.md": "FAQ content"},
        )
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "my-skill")
        assert "See [doc](refs/FAQ.md)." in result

    async def test_load_skill_unknown_returns_error(self, tmp_path: Path) -> None:
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "nonexistent")
        assert result.startswith("Error:")

    async def test_load_skill_empty_name_returns_error(self, tmp_path: Path) -> None:
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "")
        assert result.startswith("Error:")

    async def test_read_skill_resource_returns_content(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "my-skill",
            body="See [doc](refs/FAQ.md).",
            resources={"refs/FAQ.md": "FAQ content"},
        )
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "refs/FAQ.md")
        assert result == "FAQ content"

    async def test_read_skill_resource_unknown_skill_returns_error(self, tmp_path: Path) -> None:
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "nonexistent", "file.md")
        assert result.startswith("Error:")

    async def test_read_skill_resource_empty_name_returns_error(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "")
        assert result.startswith("Error:")

    async def test_read_skill_resource_unknown_resource_returns_error(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "nonexistent.md")
        assert result.startswith("Error:")

    async def test_skills_sorted_in_prompt(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        _write_skill(skills_dir, "zebra", description="Z skill.")
        _write_skill(skills_dir, "alpha", description="A skill.")
        provider = SkillsProvider.from_paths(str(skills_dir))
        context = SessionContext(input_messages=[])

        await provider.before_run(
            agent=AsyncMock(),
            session=AsyncMock(),
            context=context,
            state={},
        )

        prompt = context.instructions[0]
        assert prompt.index("alpha") < prompt.index("zebra")

    async def test_xml_escaping_in_prompt(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill", description="Uses <tags> & stuff")
        provider = SkillsProvider.from_paths(str(tmp_path))
        context = SessionContext(input_messages=[])

        await provider.before_run(
            agent=AsyncMock(),
            session=AsyncMock(),
            context=context,
            state={},
        )

        prompt = context.instructions[0]
        assert "&lt;tags&gt;" in prompt
        assert "&amp;" in prompt


# ---------------------------------------------------------------------------
# Tests: symlink detection (_has_symlink_in_path and end-to-end guards)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _requires_symlinks(tmp_path: Path) -> None:
    """Skip the test if the platform does not support symlinks."""
    if not _symlinks_supported(tmp_path):
        pytest.skip("Symlinks not supported on this platform/environment")


@pytest.mark.usefixtures("_requires_symlinks")
class TestSymlinkDetection:
    """Tests for _has_symlink_in_path and the symlink guards in validation/read."""

    def test_detects_symlinked_file(self, tmp_path: Path) -> None:
        """A symlink to a file outside the directory should be detected."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret", encoding="utf-8")

        symlink_path = skill_dir / "link.txt"
        symlink_path.symlink_to(outside_file)

        full_path = str(symlink_path)
        directory_path = str(skill_dir) + os.sep
        assert FileSkillsSource._has_symlink_in_path(full_path, directory_path) is True

    def test_detects_symlinked_directory(self, tmp_path: Path) -> None:
        """A symlink to a directory outside should be detected for paths through it."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        (outside_dir / "data.txt").write_text("data", encoding="utf-8")

        symlink_dir = skill_dir / "linked-dir"
        symlink_dir.symlink_to(outside_dir)

        full_path = str(skill_dir / "linked-dir" / "data.txt")
        directory_path = str(skill_dir) + os.sep
        assert FileSkillsSource._has_symlink_in_path(full_path, directory_path) is True

    def test_returns_false_for_regular_files(self, tmp_path: Path) -> None:
        """Regular (non-symlinked) files should not be flagged."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        regular_file = skill_dir / "doc.txt"
        regular_file.write_text("content", encoding="utf-8")

        full_path = str(regular_file)
        directory_path = str(skill_dir) + os.sep
        assert FileSkillsSource._has_symlink_in_path(full_path, directory_path) is False

    async def test_discover_skips_symlinked_resource(self, tmp_path: Path) -> None:
        """get_skills() should skip a symlinked resource but keep the skill."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()

        outside_file = tmp_path / "secret.md"
        outside_file.write_text("secret content", encoding="utf-8")

        # Create SKILL.md
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill.\n---\nInstructions.\n",
            encoding="utf-8",
        )
        refs_dir = skill_dir / "refs"
        refs_dir.mkdir()
        (refs_dir / "leak.md").symlink_to(outside_file)
        # Also add a safe resource
        (refs_dir / "safe.md").write_text("safe content", encoding="utf-8")

        skills = await _discover_file_skills_for_test([str(tmp_path)])
        assert "my-skill" in skills
        resource_names = [r.name for r in skills["my-skill"].resources]
        assert "refs/leak.md" not in resource_names
        assert "refs/safe.md" in resource_names

    def test_discover_resource_files_rejects_symlinked_resource(self, tmp_path: Path) -> None:
        """_discover_resource_files should exclude a symlinked resource file."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        outside_file = tmp_path / "secret.md"
        outside_file.write_text("secret content", encoding="utf-8")

        refs_dir = skill_dir / "refs"
        refs_dir.mkdir()
        (refs_dir / "leak.md").symlink_to(outside_file)

        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert "refs/leak.md" not in resources

    def test_discover_skips_symlinked_script(self, tmp_path: Path) -> None:
        """_discover_script_files should skip scripts with symlinks in their path."""
        if not _symlinks_supported(tmp_path):
            pytest.skip("Symlinks not supported on this platform/environment")

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()

        outside_script = tmp_path / "evil.py"
        outside_script.write_text("print('evil')", encoding="utf-8")

        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "safe.py").write_text("print('safe')", encoding="utf-8")
        (scripts_dir / "leak.py").symlink_to(outside_script)

        discovered = FileSkillsSource._discover_script_files(str(skill_dir))
        discovered_names = [p for p in discovered]
        assert "scripts/safe.py" in discovered_names
        assert "scripts/leak.py" not in discovered_names


# ---------------------------------------------------------------------------
# Tests: SkillResource
# ---------------------------------------------------------------------------


class TestSkillsExperimentalStage:
    """Tests for the experimental stage annotations applied to skills APIs."""

    def test_docstrings_include_experimental_warning(self) -> None:
        assert SkillResource.__doc__ is not None
        assert SkillScript.__doc__ is not None
        assert Skill.__doc__ is not None
        assert SkillScriptRunner.__doc__ is not None
        assert SkillsProvider.__doc__ is not None
        assert SkillScript.parameters_schema.__doc__ is not None

        assert ".. warning:: Experimental" in SkillResource.__doc__
        assert ".. warning:: Experimental" in SkillScript.__doc__
        assert ".. warning:: Experimental" in Skill.__doc__
        assert ".. warning:: Experimental" in SkillScriptRunner.__doc__
        assert ".. warning:: Experimental" in SkillsProvider.__doc__
        assert ".. warning:: Experimental" not in SkillScript.parameters_schema.__doc__

    def test_feature_metadata_is_set(self) -> None:
        assert getattr(SkillResource, "__feature_stage__", None) == "experimental"
        assert getattr(SkillScript, "__feature_stage__", None) == "experimental"
        assert getattr(Skill, "__feature_stage__", None) == "experimental"
        assert getattr(SkillsProvider, "__feature_stage__", None) == "experimental"
        feature_ids: list[str | None] = [
            getattr(SkillResource, "__feature_id__", None),
            getattr(SkillScript, "__feature_id__", None),
            getattr(Skill, "__feature_id__", None),
            getattr(SkillsProvider, "__feature_id__", None),
        ]
        assert all(isinstance(feature_id, str) and feature_id for feature_id in feature_ids)
        assert len(set(feature_ids)) == 1
        assert getattr(SkillScriptRunner, "__feature_stage__", None) is None
        assert getattr(SkillScriptRunner, "__feature_id__", None) is None
        assert SkillScript.parameters_schema.fget is not None
        assert not hasattr(SkillScript.parameters_schema.fget, "__feature_stage__")
        assert not hasattr(SkillScript.parameters_schema.fget, "__feature_id__")


class TestSkillResource:
    """Tests for SkillResource dataclass."""

    def test_static_content(self) -> None:
        resource = InlineSkillResource(name="ref", content="static content")
        assert resource.name == "ref"
        assert resource.content == "static content"
        assert resource.function is None

    def test_callable_function(self) -> None:
        def my_func() -> str:
            return "dynamic"

        resource = InlineSkillResource(name="func", function=my_func)
        assert resource.name == "func"
        assert resource.content is None
        assert resource.function is my_func

    def test_with_description(self) -> None:
        resource = InlineSkillResource(name="ref", description="A reference doc.", content="data")
        assert resource.description == "A reference doc."

    def test_requires_content_or_function(self) -> None:
        with pytest.raises(ValueError, match="must have either content or function"):
            InlineSkillResource(name="empty")

    def test_content_and_function_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="must have either content or function, not both"):
            InlineSkillResource(name="both", content="static", function=lambda: "dynamic")

    def test_accepts_kwargs_true_for_kwargs_function(self) -> None:
        def func_with_kwargs(**kwargs: Any) -> str:
            return "dynamic"

        resource = InlineSkillResource(name="res", function=func_with_kwargs)
        assert resource._accepts_kwargs is True

    def test_accepts_kwargs_false_for_regular_function(self) -> None:
        def func_no_kwargs() -> str:
            return "dynamic"

        resource = InlineSkillResource(name="res", function=func_no_kwargs)
        assert resource._accepts_kwargs is False


# ---------------------------------------------------------------------------
# Tests: InlineSkill
# ---------------------------------------------------------------------------


class TestInlineSkill:
    """Tests for InlineSkill and .resource decorator."""

    def test_skill_is_abstract(self) -> None:
        """Skill base class cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Skill()  # type: ignore[abstract]

    def test_inline_skill_is_skill(self) -> None:
        """InlineSkill is a subclass of Skill."""
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")
        assert isinstance(skill, Skill)

    def test_file_skill_is_skill(self) -> None:
        """FileSkill is a subclass of Skill."""
        skill = FileSkill(name="my-skill", description="A skill.", content="Body", path="/tmp/skill")
        assert isinstance(skill, Skill)

    def test_basic_construction(self) -> None:
        skill = InlineSkill(name="my-skill", description="A test skill.", instructions="Instructions.")
        assert skill.name == "my-skill"
        assert skill.description == "A test skill."
        assert skill.instructions == "Instructions."
        assert skill.resources == []

    def test_construction_with_static_resources(self) -> None:
        skill = InlineSkill(
            name="my-skill",
            description="A test skill.",
            instructions="Instructions.",
            resources=[
                InlineSkillResource(name="ref", content="Reference content"),
            ],
        )
        assert len(skill.resources) == 1
        assert skill.resources[0].name == "ref"

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            InlineSkill(name="", description="A skill.", instructions="Body")

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            InlineSkill(name="Invalid-Name", description="A skill.", instructions="Body")

    def test_name_starts_with_hyphen_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            InlineSkill(name="-bad-name", description="A skill.", instructions="Body")

    def test_name_with_consecutive_hyphens_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            InlineSkill(name="consecutive--hyphens", description="A skill.", instructions="Body")

    def test_name_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            InlineSkill(name="a" * 65, description="A skill.", instructions="Body")

    def test_empty_description_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            InlineSkill(name="my-skill", description="", instructions="Body")

    def test_description_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid description"):
            InlineSkill(name="my-skill", description="a" * 1025, instructions="Body")

    def test_resource_decorator_bare(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource
        def get_schema() -> Any:
            """Get the database schema."""
            return "CREATE TABLE users (id INT)"

        assert len(skill.resources) == 1
        assert skill.resources[0].name == "get_schema"
        assert skill.resources[0].description == "Get the database schema."
        assert isinstance(skill.resources[0], InlineSkillResource)
        assert skill.resources[0].function is get_schema

    def test_resource_decorator_with_args(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource(name="custom-name", description="Custom description")
        def my_resource() -> Any:
            return "data"

        assert len(skill.resources) == 1
        assert skill.resources[0].name == "custom-name"
        assert skill.resources[0].description == "Custom description"

    def test_resource_decorator_returns_function(self) -> None:
        """Decorator should return the original function unchanged."""
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource
        def get_data() -> Any:
            return "data"

        assert callable(get_data)
        assert get_data() == "data"

    def test_multiple_resources(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource
        def resource_a() -> Any:
            return "A"

        @skill.resource
        def resource_b() -> Any:
            return "B"

        assert len(skill.resources) == 2
        names = [r.name for r in skill.resources]
        assert "resource_a" in names
        assert "resource_b" in names

    def test_resource_decorator_async(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource
        async def get_async_data() -> Any:
            return "async data"

        assert len(skill.resources) == 1
        assert isinstance(skill.resources[0], InlineSkillResource)
        assert skill.resources[0].function is get_async_data


# ---------------------------------------------------------------------------
# Tests: SkillsProvider with code-defined skills
# ---------------------------------------------------------------------------


class TestSkillsProviderCodeSkill:
    """Tests for SkillsProvider with code-defined skills."""

    async def test_code_skill_only(self) -> None:
        skill = InlineSkill(name="prog-skill", description="A code-defined skill.", instructions="Do the thing.")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        assert "prog-skill" in _ctx(provider)[0]

    async def test_load_skill_returns_content(self) -> None:
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Code-defined instructions.")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "prog-skill")
        assert "<name>prog-skill</name>" in result
        assert "<description>A skill.</description>" in result
        assert "<instructions>\nCode-defined instructions.\n</instructions>" in result
        assert "<resources>" not in result

    async def test_load_skill_appends_resource_listing(self) -> None:
        skill = InlineSkill(
            name="prog-skill",
            description="A skill.",
            instructions="Do things.",
            resources=[
                InlineSkillResource(name="ref-a", content="a", description="First resource"),
                InlineSkillResource(name="ref-b", content="b"),
            ],
        )
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "prog-skill")
        assert "<name>prog-skill</name>" in result
        assert "<description>A skill.</description>" in result
        assert "Do things." in result
        assert "<resources>" in result
        assert '<resource name="ref-a" description="First resource"/>' in result
        assert '<resource name="ref-b"/>' in result

    async def test_load_skill_no_resources_no_listing(self) -> None:
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body only.")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "prog-skill")
        assert "Body only." in result
        assert "<resources>" not in result

    async def test_read_static_resource(self) -> None:
        skill = InlineSkill(
            name="prog-skill",
            description="A skill.",
            instructions="Body",
            resources=[InlineSkillResource(name="ref", content="static content")],
        )
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "prog-skill", "ref")
        assert result == "static content"

    async def test_read_callable_resource_sync(self) -> None:
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body")

        @skill.resource
        def get_schema() -> Any:
            return "CREATE TABLE users"

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "prog-skill", "get_schema")
        assert result == "CREATE TABLE users"

    async def test_read_callable_resource_async(self) -> None:
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body")

        @skill.resource
        async def get_data() -> Any:
            return "async data"

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "prog-skill", "get_data")
        assert result == "async data"

    async def test_read_resource_case_insensitive(self) -> None:
        skill = InlineSkill(
            name="prog-skill",
            description="A skill.",
            instructions="Body",
            resources=[InlineSkillResource(name="MyRef", content="content")],
        )
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "prog-skill", "myref")
        assert result == "content"

    async def test_read_unknown_resource_returns_error(self) -> None:
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "prog-skill", "nonexistent")
        assert result.startswith("Error:")

    async def test_read_callable_resource_sync_with_kwargs(self) -> None:
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body")

        @skill.resource
        def get_user_config(**kwargs: Any) -> Any:
            user_id = kwargs.get("user_id", "unknown")
            return f"config for {user_id}"

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(
            _raw_skills(provider), "prog-skill", "get_user_config", user_id="user_123"
        )
        assert result == "config for user_123"

    async def test_read_callable_resource_async_with_kwargs(self) -> None:
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body")

        @skill.resource
        async def get_user_data(**kwargs: Any) -> Any:
            token = kwargs.get("auth_token", "none")
            return f"data with token={token}"

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(
            _raw_skills(provider), "prog-skill", "get_user_data", auth_token="abc"
        )
        assert result == "data with token=abc"

    async def test_read_callable_resource_without_kwargs_ignores_extra_args(self) -> None:
        """Resource functions without **kwargs should still work when kwargs are passed."""
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body")

        @skill.resource
        def static_resource() -> Any:
            return "static content"

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(
            _raw_skills(provider), "prog-skill", "static_resource", user_id="ignored"
        )
        assert result == "static content"

    async def test_read_callable_resource_returns_dict(self) -> None:
        """Resource functions may return non-string types, passed through as-is."""
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body")

        @skill.resource
        def get_config() -> Any:
            return {"max_retries": 3, "timeout": 30}

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "prog-skill", "get_config")
        assert result == {"max_retries": 3, "timeout": 30}

    async def test_read_callable_resource_returns_list(self) -> None:
        """Resource functions may return lists, passed through as-is."""
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body")

        @skill.resource
        def get_items() -> Any:
            return [1, 2, 3]

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "prog-skill", "get_items")
        assert result == [1, 2, 3]

    async def test_read_callable_resource_returns_none(self) -> None:
        """Resource functions may return None."""
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Body")

        @skill.resource
        def get_nothing() -> Any:
            return None

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "prog-skill", "get_nothing")
        assert result is None

    async def test_before_run_injects_code_skills(self) -> None:
        skill = InlineSkill(name="prog-skill", description="A code-defined skill.", instructions="Body")
        provider = SkillsProvider([skill])
        context = SessionContext(input_messages=[])

        await provider.before_run(agent=AsyncMock(), session=AsyncMock(), context=context, state={})

        assert len(context.instructions) == 1
        assert "prog-skill" in context.instructions[0]
        assert len(context.tools) == 1

    async def test_before_run_empty_provider(self) -> None:
        provider = SkillsProvider([])
        context = SessionContext(input_messages=[])

        await provider.before_run(agent=AsyncMock(), session=AsyncMock(), context=context, state={})

        assert len(context.instructions) == 0
        assert len(context.tools) == 0

    async def test_combined_file_and_code_skill(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "file-skill")
        prog_skill = InlineSkill(name="prog-skill", description="Code-defined.", instructions="Body")
        provider = SkillsProvider(
            DeduplicatingSkillsSource(
                AggregatingSkillsSource([
                    FileSkillsSource(str(tmp_path)),
                    InMemorySkillsSource([prog_skill]),
                ])
            )
        )
        await _init_provider(provider)
        assert "file-skill" in _ctx(provider)[0]
        assert "prog-skill" in _ctx(provider)[0]

    async def test_duplicate_name_file_wins(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill", body="File version")
        prog_skill = InlineSkill(name="my-skill", description="Code-defined.", instructions="Prog version")
        provider = SkillsProvider(
            DeduplicatingSkillsSource(
                AggregatingSkillsSource([
                    FileSkillsSource(str(tmp_path)),
                    InMemorySkillsSource([prog_skill]),
                ])
            )
        )
        await _init_provider(provider)
        # File-based is loaded first, so it wins
        assert "File version" in _ctx(provider)[0]["my-skill"].content

    async def test_combined_prompt_includes_both(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "file-skill")
        prog_skill = InlineSkill(name="prog-skill", description="A code-defined skill.", instructions="Body")
        provider = SkillsProvider(
            DeduplicatingSkillsSource(
                AggregatingSkillsSource([
                    FileSkillsSource(str(tmp_path)),
                    InMemorySkillsSource([prog_skill]),
                ])
            )
        )
        context = SessionContext(input_messages=[])

        await provider.before_run(agent=AsyncMock(), session=AsyncMock(), context=context, state={})

        prompt = context.instructions[0]
        assert "file-skill" in prompt
        assert "prog-skill" in prompt

    async def test_custom_resource_extensions(self, tmp_path: Path) -> None:
        """SkillsProvider accepts custom resource_extensions."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A test skill.\n---\nBody.",
            encoding="utf-8",
        )
        (skill_dir / "data.json").write_text("{}", encoding="utf-8")
        (skill_dir / "notes.txt").write_text("notes", encoding="utf-8")

        # Only discover .json files
        provider = SkillsProvider.from_paths(str(tmp_path), resource_extensions=(".json",))
        await _init_provider(provider)
        skill = _ctx(provider)[0]["my-skill"]
        resource_names = [r.name for r in skill.resources]
        assert "data.json" in resource_names
        assert "notes.txt" not in resource_names


# ---------------------------------------------------------------------------
# Tests: File-based skill parsing and content
# ---------------------------------------------------------------------------


class TestFileBasedSkillParsing:
    """Tests for file-based skills parsed from SKILL.md."""

    def test_content_contains_full_raw_file(self, tmp_path: Path) -> None:
        """content stores the entire SKILL.md file including frontmatter."""
        _write_skill(tmp_path, "my-skill", description="A test skill.", body="Instructions here.")
        skill = _read_and_parse_skill_file_for_test(tmp_path / "my-skill")
        assert "---" in skill.content
        assert "name: my-skill" in skill.content
        assert "description: A test skill." in skill.content
        assert "Instructions here." in skill.content

    def test_name_and_description_from_frontmatter(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill", description="Skill desc.")
        skill = _read_and_parse_skill_file_for_test(tmp_path / "my-skill")
        assert skill.name == "my-skill"
        assert skill.description == "Skill desc."

    def test_path_set(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        skill = _read_and_parse_skill_file_for_test(tmp_path / "my-skill")
        assert skill.path == str(tmp_path / "my-skill")

    async def test_resources_populated(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill", resources={"refs/doc.md": "content"})
        skills = await _discover_file_skills_for_test([str(tmp_path)])
        assert "my-skill" in skills
        resource_names = [r.name for r in skills["my-skill"].resources]
        assert "refs/doc.md" in resource_names


# ---------------------------------------------------------------------------
# Tests: _load_skill formatting
# ---------------------------------------------------------------------------


class TestLoadSkillFormatting:
    """Tests for _load_skill output formatting differences between file-based and code-defined skills."""

    async def test_file_skill_returns_raw_content(self, tmp_path: Path) -> None:
        """File-based skills return raw SKILL.md content without XML wrapping."""
        _write_skill(tmp_path, "my-skill", body="Do the thing.")
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "my-skill")
        assert "Do the thing." in result
        assert "<name>" not in result
        assert "<instructions>" not in result

    async def test_code_skill_wraps_in_xml(self) -> None:
        """Code-defined skills are wrapped with name, description, and instructions tags."""
        skill = InlineSkill(name="prog-skill", description="A skill.", instructions="Do stuff.")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "prog-skill")
        assert "<name>prog-skill</name>" in result
        assert "<description>A skill.</description>" in result
        assert "<instructions>\nDo stuff.\n</instructions>" in result

    async def test_code_skill_single_resource_no_description(self) -> None:
        """Resource without description omits the description attribute."""
        skill = InlineSkill(
            name="prog-skill",
            description="A skill.",
            instructions="Body.",
            resources=[InlineSkillResource(name="data", content="val")],
        )
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "prog-skill")
        assert '<resource name="data"/>' in result
        assert "description=" not in result


# ---------------------------------------------------------------------------
# Tests: _discover_resource_files edge cases
# ---------------------------------------------------------------------------


class TestDiscoverResourceFilesEdgeCases:
    """Additional edge-case tests for filesystem resource discovery."""

    def test_excludes_skill_md_case_insensitive(self, tmp_path: Path) -> None:
        """SKILL.md in any casing is excluded."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.md").write_text("lowercase name", encoding="utf-8")
        (skill_dir / "other.md").write_text("keep me", encoding="utf-8")
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        names = [r.lower() for r in resources]
        assert "skill.md" not in names
        assert "other.md" in resources

    def test_skips_directories(self, tmp_path: Path) -> None:
        """Directories are not included as resources even if their name matches an extension."""
        skill_dir = tmp_path / "my-skill"
        subdir = skill_dir / "data.json"
        subdir.mkdir(parents=True)
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert resources == []

    def test_extension_matching_is_case_insensitive(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "NOTES.TXT").write_text("caps", encoding="utf-8")
        resources = FileSkillsSource._discover_resource_files(str(skill_dir))
        assert len(resources) == 1


# ---------------------------------------------------------------------------
# Tests: _is_path_within_directory
# ---------------------------------------------------------------------------


class TestIsPathWithinDirectory:
    """Tests for _is_path_within_directory."""

    def test_path_inside_directory(self, tmp_path: Path) -> None:
        child = str(tmp_path / "sub" / "file.txt")
        assert FileSkillsSource._is_path_within_directory(child, str(tmp_path)) is True

    def test_path_outside_directory(self, tmp_path: Path) -> None:
        outside = str(tmp_path.parent / "other" / "file.txt")
        assert FileSkillsSource._is_path_within_directory(outside, str(tmp_path)) is False

    def test_path_is_directory_itself(self, tmp_path: Path) -> None:
        assert FileSkillsSource._is_path_within_directory(str(tmp_path), str(tmp_path)) is True

    def test_similar_prefix_not_matched(self, tmp_path: Path) -> None:
        """'skill-a-evil' is not inside 'skill-a'."""
        dir_a = str(tmp_path / "skill-a")
        evil = str(tmp_path / "skill-a-evil" / "file.txt")
        assert FileSkillsSource._is_path_within_directory(evil, dir_a) is False


# ---------------------------------------------------------------------------
# Tests: _has_symlink_in_path edge cases
# ---------------------------------------------------------------------------


class TestHasSymlinkInPathEdgeCases:
    """Edge-case tests for _has_symlink_in_path."""

    def test_raises_when_path_not_relative(self, tmp_path: Path) -> None:
        unrelated = str(tmp_path.parent / "other" / "file.txt")
        with pytest.raises(ValueError, match="does not start with directory"):
            FileSkillsSource._has_symlink_in_path(unrelated, str(tmp_path))

    def test_returns_false_for_empty_relative(self, tmp_path: Path) -> None:
        """When path equals directory, relative is empty so no symlinks."""
        assert FileSkillsSource._has_symlink_in_path(str(tmp_path), str(tmp_path)) is False


# ---------------------------------------------------------------------------
# Tests: _validate_skill_metadata
# ---------------------------------------------------------------------------


class TestValidateSkillMetadata:
    """Tests for _validate_skill_metadata."""

    def test_valid_metadata(self) -> None:
        assert FileSkillsSource._validate_skill_metadata("my-skill", "A description.", "source") is None

    def test_none_name(self) -> None:
        result = FileSkillsSource._validate_skill_metadata(None, "desc", "source")
        assert result is not None
        assert "missing a name" in result

    def test_empty_name(self) -> None:
        result = FileSkillsSource._validate_skill_metadata("", "desc", "source")
        assert result is not None
        assert "missing a name" in result

    def test_whitespace_only_name(self) -> None:
        result = FileSkillsSource._validate_skill_metadata("   ", "desc", "source")
        assert result is not None
        assert "missing a name" in result

    def test_name_at_max_length(self) -> None:
        name = "a" * 64
        assert FileSkillsSource._validate_skill_metadata(name, "desc", "source") is None

    def test_name_exceeds_max_length(self) -> None:
        name = "a" * 65
        result = FileSkillsSource._validate_skill_metadata(name, "desc", "source")
        assert result is not None
        assert "invalid name" in result

    def test_name_with_uppercase(self) -> None:
        result = FileSkillsSource._validate_skill_metadata("BadName", "desc", "source")
        assert result is not None
        assert "invalid name" in result

    def test_name_starts_with_hyphen(self) -> None:
        result = FileSkillsSource._validate_skill_metadata("-bad", "desc", "source")
        assert result is not None
        assert "invalid name" in result

    def test_name_ends_with_hyphen(self) -> None:
        result = FileSkillsSource._validate_skill_metadata("bad-", "desc", "source")
        assert result is not None
        assert "invalid name" in result

    def test_name_with_consecutive_hyphens(self) -> None:
        result = FileSkillsSource._validate_skill_metadata("consecutive--hyphens", "desc", "source")
        assert result is not None
        assert "invalid name" in result

    def test_single_char_name(self) -> None:
        assert FileSkillsSource._validate_skill_metadata("a", "desc", "source") is None

    def test_none_description(self) -> None:
        result = FileSkillsSource._validate_skill_metadata("my-skill", None, "source")
        assert result is not None
        assert "missing a description" in result

    def test_empty_description(self) -> None:
        result = FileSkillsSource._validate_skill_metadata("my-skill", "", "source")
        assert result is not None
        assert "missing a description" in result

    def test_whitespace_only_description(self) -> None:
        result = FileSkillsSource._validate_skill_metadata("my-skill", "   ", "source")
        assert result is not None
        assert "missing a description" in result

    def test_description_at_max_length(self) -> None:
        desc = "a" * 1024
        assert FileSkillsSource._validate_skill_metadata("my-skill", desc, "source") is None

    def test_description_exceeds_max_length(self) -> None:
        desc = "a" * 1025
        result = FileSkillsSource._validate_skill_metadata("my-skill", desc, "source")
        assert result is not None
        assert "invalid description" in result


# ---------------------------------------------------------------------------
# Tests: _discover_skill_directories
# ---------------------------------------------------------------------------


class TestDiscoverSkillDirectories:
    """Tests for _discover_skill_directories."""

    def test_finds_skill_at_root(self, tmp_path: Path) -> None:
        (tmp_path / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        dirs = FileSkillsSource._discover_skill_directories([str(tmp_path)])
        assert len(dirs) == 1

    def test_finds_nested_skill(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        dirs = FileSkillsSource._discover_skill_directories([str(tmp_path)])
        assert len(dirs) == 1
        assert str(sub.absolute()) in dirs[0]

    def test_skips_empty_path_string(self) -> None:
        dirs = FileSkillsSource._discover_skill_directories(["", "   "])
        assert dirs == []

    def test_skips_nonexistent_path(self) -> None:
        dirs = FileSkillsSource._discover_skill_directories(["/nonexistent/does/not/exist"])
        assert dirs == []

    def test_depth_limit_excludes_deep_skill(self, tmp_path: Path) -> None:
        deep = tmp_path / "l1" / "l2" / "l3"
        deep.mkdir(parents=True)
        (deep / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        dirs = FileSkillsSource._discover_skill_directories([str(tmp_path)])
        assert len(dirs) == 0

    def test_depth_limit_includes_at_boundary(self, tmp_path: Path) -> None:
        at_boundary = tmp_path / "l1" / "l2"
        at_boundary.mkdir(parents=True)
        (at_boundary / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        dirs = FileSkillsSource._discover_skill_directories([str(tmp_path)])
        assert len(dirs) == 1


# ---------------------------------------------------------------------------
# Tests: _read_and_parse_skill_file edge cases
# ---------------------------------------------------------------------------


class TestReadAndParseSkillFile:
    """Tests for _read_and_parse_skill_file."""

    def test_valid_file(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: A skill.\n---\nBody.", encoding="utf-8")
        result = FileSkillsSource._read_and_parse_skill_file(str(skill_dir))
        assert result is not None
        name, desc, content = result
        assert name == "my-skill"
        assert desc == "A skill."
        assert "Body." in content

    def test_missing_skill_md_returns_none(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "no-skill"
        skill_dir.mkdir()
        result = FileSkillsSource._read_and_parse_skill_file(str(skill_dir))
        assert result is None

    def test_invalid_frontmatter_returns_none(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("No frontmatter at all.", encoding="utf-8")
        result = FileSkillsSource._read_and_parse_skill_file(str(skill_dir))
        assert result is None

    def test_name_directory_mismatch_returns_none(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "wrong-dir-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: actual-skill-name\ndescription: A skill.\n---\nBody.", encoding="utf-8"
        )
        result = FileSkillsSource._read_and_parse_skill_file(str(skill_dir))
        assert result is None


# ---------------------------------------------------------------------------
# Tests: _create_resource_element
# ---------------------------------------------------------------------------


class TestCreateResourceElement:
    """Tests for _create_resource_element."""

    def test_name_only(self) -> None:
        r = InlineSkillResource(name="my-ref", content="data")
        elem = InlineSkill._create_resource_element(r)
        assert elem == '  <resource name="my-ref"/>'

    def test_with_description(self) -> None:
        r = InlineSkillResource(name="my-ref", description="A reference.", content="data")
        elem = InlineSkill._create_resource_element(r)
        assert elem == '  <resource name="my-ref" description="A reference."/>'

    def test_xml_escapes_name(self) -> None:
        r = InlineSkillResource(name='ref"special', content="data")
        elem = InlineSkill._create_resource_element(r)
        assert "&quot;" in elem

    def test_xml_escapes_description(self) -> None:
        r = InlineSkillResource(name="ref", description='Uses <tags> & "quotes"', content="data")
        elem = InlineSkill._create_resource_element(r)
        assert "&lt;tags&gt;" in elem
        assert "&amp;" in elem
        assert "&quot;" in elem


# ---------------------------------------------------------------------------
# Tests: _FileSkillResource edge cases
# ---------------------------------------------------------------------------


class TestReadFileSkillResourceEdgeCases:
    """Edge-case tests for _FileSkillResource."""

    def test_constructor_validates_full_path(self) -> None:
        with pytest.raises(ValueError, match="full_path cannot be empty"):
            _FileSkillResource(name="some-file.md", full_path="")

    def test_constructor_rejects_whitespace_full_path(self) -> None:
        with pytest.raises(ValueError, match="full_path cannot be empty"):
            _FileSkillResource(name="some-file.md", full_path="   ")

    def test_full_path_attribute(self) -> None:
        resource = _FileSkillResource(name="doc.md", full_path=f"{_ABS}/doc.md")
        assert resource.full_path == f"{_ABS}/doc.md"

    async def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        full_path = str(skill_dir / "missing.md")
        resource = _FileSkillResource(name="missing.md", full_path=full_path)
        with pytest.raises(ValueError, match="not found"):
            await resource.read()


class TestGetValidatedResourcePath:
    """Tests for FileSkillsSource._get_validated_resource_path security validation."""

    def test_returns_valid_path(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "doc.md").write_text("hello")
        result = FileSkillsSource._get_validated_resource_path(str(skill_dir), "doc.md")
        assert Path(result).is_file()

    def test_rejects_relative_skill_dir(self) -> None:
        with pytest.raises(ValueError, match="skill_dir must be an absolute path"):
            FileSkillsSource._get_validated_resource_path("relative/path", "doc.md")

    def test_rejects_path_outside_skill_dir(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        outside_file = tmp_path / "secret.md"
        outside_file.write_text("secret")
        with pytest.raises(ValueError, match="outside the skill directory"):
            FileSkillsSource._get_validated_resource_path(str(skill_dir), "../secret.md")

    def test_rejects_nonexistent_file(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        with pytest.raises(ValueError, match="not found"):
            FileSkillsSource._get_validated_resource_path(str(skill_dir), "missing.md")

    @pytest.mark.skipif(os.name == "nt", reason="symlinks require elevated privileges on Windows")
    def test_rejects_symlink_in_path(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        real_subdir = tmp_path / "external"
        real_subdir.mkdir()
        (real_subdir / "data.md").write_text("external data")
        link = skill_dir / "linked"
        link.symlink_to(real_subdir)
        with pytest.raises(ValueError, match="symlink"):
            FileSkillsSource._get_validated_resource_path(str(skill_dir), "linked/data.md")


# ---------------------------------------------------------------------------
# Tests: _normalize_resource_path edge cases
# ---------------------------------------------------------------------------


class TestNormalizeResourcePathEdgeCases:
    """Additional edge-case tests for _normalize_resource_path."""

    def test_bare_filename(self) -> None:
        assert FileSkillsSource._normalize_resource_path("file.md") == "file.md"

    def test_deeply_nested_path(self) -> None:
        assert FileSkillsSource._normalize_resource_path("a/b/c/d.md") == "a/b/c/d.md"

    def test_mixed_separators(self) -> None:
        assert FileSkillsSource._normalize_resource_path("a\\b/c\\d.md") == "a/b/c/d.md"

    def test_dot_prefix_only(self) -> None:
        assert FileSkillsSource._normalize_resource_path("./file.md") == "file.md"


# ---------------------------------------------------------------------------
# Tests: file skill discovery edge cases
# ---------------------------------------------------------------------------


class TestDiscoverFileSkillsEdgeCases:
    """Edge-case tests for file skill discovery."""

    async def test_empty_paths_returns_empty(self) -> None:
        skills = await _discover_file_skills_for_test([])
        assert len(skills) == 0

    async def test_accepts_path_object(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        skills = await _discover_file_skills_for_test(tmp_path)
        assert "my-skill" in skills

    async def test_accepts_single_string_path(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        skills = await _discover_file_skills_for_test(str(tmp_path))
        assert "my-skill" in skills


# ---------------------------------------------------------------------------
# Tests: _extract_frontmatter edge cases
# ---------------------------------------------------------------------------


class TestExtractFrontmatterEdgeCases:
    """Additional edge-case tests for _extract_frontmatter."""

    def test_whitespace_only_name(self) -> None:
        content = "---\nname: '   '\ndescription: A skill.\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_whitespace_only_description(self) -> None:
        content = "---\nname: test-skill\ndescription: '   '\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is None

    def test_name_exactly_max_length(self) -> None:
        name = "a" * 64
        content = f"---\nname: {name}\ndescription: A skill.\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[0] == name

    def test_description_exactly_max_length(self) -> None:
        desc = "a" * 1024
        content = f"---\nname: test-skill\ndescription: {desc}\n---\nBody."
        result = FileSkillsSource._extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[1] == desc


# ---------------------------------------------------------------------------
# Tests: _create_instructions edge cases
# ---------------------------------------------------------------------------


class TestCreateInstructionsEdgeCases:
    """Additional edge-case tests for _create_instructions."""

    def test_custom_template_with_empty_skills_returns_none(self) -> None:
        result = SkillsProvider._create_instructions("Custom: {skills}", [])
        assert result is None

    def test_custom_template_with_literal_braces(self) -> None:
        skills = [
            InlineSkill(name="my-skill", description="Skill.", instructions="Body"),
        ]
        template = "Header {{literal}} {skills} footer."
        result = SkillsProvider._create_instructions(template, skills)
        assert result is not None
        assert "{literal}" in result
        assert "my-skill" in result

    def test_multiple_skills_generates_sorted_xml(self) -> None:
        skills = [
            InlineSkill(name="charlie", description="C.", instructions="Body"),
            InlineSkill(name="alpha", description="A.", instructions="Body"),
            InlineSkill(name="bravo", description="B.", instructions="Body"),
        ]
        result = SkillsProvider._create_instructions(None, skills)
        assert result is not None
        alpha_pos = result.index("alpha")
        bravo_pos = result.index("bravo")
        charlie_pos = result.index("charlie")
        assert alpha_pos < bravo_pos < charlie_pos

    def test_custom_template_missing_runner_instructions_raises(self) -> None:
        """Custom template without {runner_instructions} raises when scripts are enabled."""
        skills = [
            InlineSkill(name="my-skill", description="Skill.", instructions="Body"),
        ]
        template = "Skills: {skills}"
        with pytest.raises(ValueError, match="runner_instructions"):
            SkillsProvider._create_instructions(template, skills, include_script_runner_instructions=True)

    def test_custom_template_missing_resource_instructions_raises(self) -> None:
        """Custom template without {resource_instructions} raises when resources exist."""
        skills = [
            InlineSkill(name="my-skill", description="Skill.", instructions="Body"),
        ]
        template = "Skills: {skills}"
        with pytest.raises(ValueError, match="resource_instructions"):
            SkillsProvider._create_instructions(template, skills, include_resource_instructions=True)

    def test_include_resource_instructions_true_adds_resource_text(self) -> None:
        """When include_resource_instructions is True, resource instructions appear in the prompt."""
        skills = [
            InlineSkill(name="my-skill", description="Skill.", instructions="Body"),
        ]
        result = SkillsProvider._create_instructions(None, skills, include_resource_instructions=True)
        assert result is not None
        assert "read_skill_resource" in result

    def test_include_resource_instructions_false_omits_resource_text(self) -> None:
        """When include_resource_instructions is False, resource instructions do not appear."""
        skills = [
            InlineSkill(name="my-skill", description="Skill.", instructions="Body"),
        ]
        result = SkillsProvider._create_instructions(None, skills, include_resource_instructions=False)
        assert result is not None
        assert "read_skill_resource" not in result

    def test_custom_template_with_unknown_placeholder_raises(self) -> None:
        """Template with an unknown placeholder raises ValueError."""
        skills = [
            InlineSkill(name="my-skill", description="Skill.", instructions="Body"),
        ]
        template = "Skills: {skills} {unknown_key}"
        with pytest.raises(ValueError, match="valid format string"):
            SkillsProvider._create_instructions(template, skills)


# ---------------------------------------------------------------------------
# Tests: SkillsProvider edge cases
# ---------------------------------------------------------------------------


class TestSkillsProviderEdgeCases:
    """Additional edge-case tests for SkillsProvider."""

    async def test_accepts_path_object(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider.from_paths(tmp_path)
        await _init_provider(provider)
        assert "my-skill" in _ctx(provider)[0]

    async def test_load_skill_whitespace_name_returns_error(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "   ")
        assert result.startswith("Error:")
        assert "empty" in result

    async def test_read_skill_resource_whitespace_skill_name_returns_error(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "   ", "ref")
        assert result.startswith("Error:")
        assert "empty" in result

    async def test_read_skill_resource_whitespace_resource_name_returns_error(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "   ")
        assert result.startswith("Error:")
        assert "empty" in result

    async def test_read_callable_resource_exception_returns_error(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource
        def exploding_resource() -> Any:
            raise RuntimeError("boom")

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "exploding_resource")
        assert result.startswith("Error:")
        assert "Failed to read resource" in result

    async def test_read_async_callable_resource_exception_returns_error(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource
        async def async_exploding() -> Any:
            raise ValueError("async boom")

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "async_exploding")
        assert result.startswith("Error:")

    async def test_load_code_skill_xml_escapes_metadata(self) -> None:
        skill = InlineSkill(name="my-skill", description='Uses <tags> & "quotes"', instructions="Body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "my-skill")
        assert "&lt;tags&gt;" in result
        assert "&amp;" in result

    async def test_code_skill_deduplication(self) -> None:
        skill1 = InlineSkill(name="my-skill", description="First.", instructions="Body 1")
        skill2 = InlineSkill(name="my-skill", description="Second.", instructions="Body 2")
        provider = SkillsProvider([skill1, skill2])
        await _init_provider(provider)
        assert len(_ctx(provider)[0]) == 1
        assert "First." in _ctx(provider)[0]["my-skill"].description

    async def test_before_run_extends_tools_even_without_instructions(self) -> None:
        """If instructions are somehow None but skills exist, tools should still be added."""
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")
        provider = SkillsProvider([skill])
        context = SessionContext(input_messages=[])

        await provider.before_run(agent=AsyncMock(), session=AsyncMock(), context=context, state={})

        assert len(context.tools) == 1
        tool_names = {t.name for t in context.tools}
        assert "load_skill" in tool_names


# ---------------------------------------------------------------------------
# Tests: SkillResource edge cases
# ---------------------------------------------------------------------------


class TestSkillResourceEdgeCases:
    """Additional edge-case tests for SkillResource."""

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            InlineSkillResource(name="", content="data")

    def test_whitespace_only_name_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            InlineSkillResource(name="   ", content="data")

    def test_description_defaults_to_none(self) -> None:
        r = InlineSkillResource(name="ref", content="data")
        assert r.description is None


# ---------------------------------------------------------------------------
# Tests: SkillResource.read()
# ---------------------------------------------------------------------------


class TestSkillResourceRead:
    """Tests for SkillResource.read() method."""

    async def test_read_static_content(self) -> None:
        """read() returns static content directly."""
        r = InlineSkillResource(name="ref", content="hello")
        result = await r.read()
        assert result == "hello"

    async def test_read_sync_function(self) -> None:
        """read() invokes a sync function and returns its result."""
        r = InlineSkillResource(name="ref", function=lambda: "computed")
        result = await r.read()
        assert result == "computed"

    async def test_read_async_function(self) -> None:
        """read() awaits an async function and returns its result."""

        async def get_data() -> str:
            return "async result"

        r = InlineSkillResource(name="ref", function=get_data)
        result = await r.read()
        assert result == "async result"

    async def test_read_function_with_kwargs(self) -> None:
        """read() forwards kwargs to functions that accept them."""

        def get_config(**kwargs: Any) -> str:
            return f"user={kwargs.get('user_id')}"

        r = InlineSkillResource(name="ref", function=get_config)
        result = await r.read(user_id="u42")
        assert result == "user=u42"

    async def test_read_async_function_with_kwargs(self) -> None:
        """read() forwards kwargs to async functions that accept them."""

        async def get_config(**kwargs: Any) -> str:
            return f"user={kwargs.get('user_id')}"

        r = InlineSkillResource(name="ref", function=get_config)
        result = await r.read(user_id="u42")
        assert result == "user=u42"

    async def test_read_function_without_kwargs_ignores_extra(self) -> None:
        """read() does not pass kwargs to functions that don't accept them."""

        def simple() -> str:
            return "fixed"

        r = InlineSkillResource(name="ref", function=simple)
        result = await r.read(user_id="ignored")
        assert result == "fixed"

    async def test_read_function_raises_propagates(self) -> None:
        """read() propagates exceptions from the function."""

        def failing() -> str:
            raise RuntimeError("boom")

        r = InlineSkillResource(name="ref", function=failing)
        with pytest.raises(RuntimeError, match="boom"):
            await r.read()


# ---------------------------------------------------------------------------
# Tests: Skill.resource decorator edge cases
# ---------------------------------------------------------------------------


class TestSkillResourceDecoratorEdgeCases:
    """Additional edge-case tests for the @skill.resource decorator."""

    def test_decorator_no_docstring_description_is_none(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource
        def no_docs() -> Any:
            return "data"

        assert skill.resources[0].description is None

    def test_decorator_with_name_only(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource(name="custom-name")
        def get_data() -> Any:
            """Some docs."""
            return "data"

        assert skill.resources[0].name == "custom-name"
        # description falls back to docstring
        assert skill.resources[0].description == "Some docs."

    def test_decorator_with_description_only(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource(description="Custom desc")
        def get_data() -> Any:
            return "data"

        assert skill.resources[0].name == "get_data"
        assert skill.resources[0].description == "Custom desc"

    def test_decorator_preserves_original_function_identity(self) -> None:
        skill = InlineSkill(name="my-skill", description="A skill.", instructions="Body")

        @skill.resource
        def original() -> Any:
            return "original"

        @skill.resource(name="aliased")
        def aliased() -> Any:
            return "aliased"

        # Both decorated functions should still be callable
        assert original() == "original"
        assert aliased() == "aliased"


# ---------------------------------------------------------------------------
# SkillScript tests
# ---------------------------------------------------------------------------


class TestSkillScript:
    """Tests for the SkillScript data model."""

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Script name cannot be empty"):
            InlineSkillScript(name="", function=lambda: None)

    def test_whitespace_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Script name cannot be empty"):
            InlineSkillScript(name="   ", function=lambda: None)

    def test_inline_script_has_no_path(self) -> None:
        script = InlineSkillScript(name="test", function=lambda: None)
        assert not hasattr(script, "path")

    def test_full_path_set_explicitly(self) -> None:
        script = FileSkillScript(name="gen.py", full_path=f"{_ABS}/my-skill/scripts/gen.py")
        assert script.full_path == f"{_ABS}/my-skill/scripts/gen.py"

    def test_create_with_function(self) -> None:
        script = InlineSkillScript(name="analyze", description="Run analysis", function=lambda: "result")
        assert script.name == "analyze"
        assert script.description == "Run analysis"
        assert script.function is not None

    def test_accepts_kwargs_true_for_kwargs_function(self) -> None:
        def func_with_kwargs(**kwargs: Any) -> str:
            return "result"

        script = InlineSkillScript(name="s1", function=func_with_kwargs)
        assert script._accepts_kwargs is True

    def test_accepts_kwargs_false_for_regular_function(self) -> None:
        def func_no_kwargs(x: int = 0) -> str:
            return "result"

        script = InlineSkillScript(name="s1", function=func_no_kwargs)
        assert script._accepts_kwargs is False

    def test_runner_stored(self) -> None:
        runner = _noop_script_runner
        script = FileSkillScript(name="s1", full_path=f"{_ABS}/test/s1.py", runner=runner)
        assert script._runner is runner

    def test_runner_none_by_default(self) -> None:
        script = FileSkillScript(name="s1", full_path=f"{_ABS}/test/s1.py")
        assert script._runner is None


class TestSkillScriptRun:
    """Tests for SkillScript.run()."""

    async def test_run_code_defined_sync(self) -> None:
        def greet(name: str = "world") -> str:
            return f"hello {name}"

        script = InlineSkillScript(name="greet", function=greet)
        skill = InlineSkill(name="s", description="d", instructions="c")
        result = await script.run(skill, args={"name": "Alice"})
        assert result == "hello Alice"

    async def test_run_code_defined_async(self) -> None:
        async def greet(name: str = "world") -> str:
            return f"async {name}"

        script = InlineSkillScript(name="greet", function=greet)
        skill = InlineSkill(name="s", description="d", instructions="c")
        result = await script.run(skill, args={"name": "Bob"})
        assert result == "async Bob"

    async def test_run_code_defined_with_kwargs(self) -> None:
        def func(x: int = 0, **kwargs: Any) -> dict[str, Any]:
            return {"x": x, **kwargs}

        script = InlineSkillScript(name="f", function=func)
        skill = InlineSkill(name="s", description="d", instructions="c")
        result = await script.run(skill, args={"x": 1}, extra="val")
        assert result == {"x": 1, "extra": "val"}

    async def test_run_code_defined_no_args(self) -> None:
        script = InlineSkillScript(name="f", function=lambda: 42)
        skill = InlineSkill(name="s", description="d", instructions="c")
        result = await script.run(skill)
        assert result == 42

    async def test_run_file_based_with_runner(self) -> None:
        captured: dict[str, Any] = {}

        def runner(skill: Skill, script: SkillScript, args: dict[str, Any] | None = None) -> str:
            captured["skill"] = skill.name
            captured["script"] = script.name
            captured["args"] = args
            return "runner_result"

        script = FileSkillScript(name="run.py", full_path=f"{_ABS}/test/run.py", runner=runner)
        skill = FileSkill(name="my-skill", description="d", content="c", path=f"{_ABS}/test")
        result = await script.run(skill, args={"key": "val"})
        assert result == "runner_result"
        assert captured["skill"] == "my-skill"
        assert captured["script"] == "run.py"
        assert captured["args"] == {"key": "val"}

    async def test_run_file_based_with_async_runner(self) -> None:
        async def runner(skill: Skill, script: SkillScript, args: dict[str, Any] | None = None) -> str:
            return "async_runner"

        script = FileSkillScript(name="run.py", full_path=f"{_ABS}/test/run.py", runner=runner)
        skill = FileSkill(name="s", description="d", content="c", path=f"{_ABS}/test")
        result = await script.run(skill, args=None)
        assert result == "async_runner"

    async def test_run_file_based_without_runner_raises(self) -> None:
        script = FileSkillScript(name="run.py", full_path=f"{_ABS}/test/run.py")
        skill = FileSkill(name="s", description="d", content="c", path=f"{_ABS}/test")
        with pytest.raises(ValueError, match="requires a runner"):
            await script.run(skill)

    async def test_run_file_based_with_non_file_skill_raises_type_error(self) -> None:
        script = FileSkillScript(name="run.py", full_path=f"{_ABS}/test/run.py", runner=_noop_script_runner)
        skill = InlineSkill(name="s", description="d", instructions="c")
        with pytest.raises(TypeError, match="requires a FileSkill"):
            await script.run(skill)

    def test_full_path_rejects_relative(self) -> None:
        with pytest.raises(ValueError, match="absolute path"):
            FileSkillScript(name="run.py", full_path="scripts/run.py")

    def test_full_path_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            FileSkillScript(name="run.py", full_path="")


# ---------------------------------------------------------------------------
# @skill.script decorator tests
# ---------------------------------------------------------------------------


class TestSkillScriptDecorator:
    """Tests for the @skill.script decorator."""

    def test_bare_decorator(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        @skill.script
        def analyze(query: str) -> str:
            """Run analysis."""
            return "result"

        assert len(skill.scripts) == 1
        assert skill.scripts[0].name == "analyze"
        assert skill.scripts[0].description == "Run analysis."
        assert isinstance(skill.scripts[0], InlineSkillScript)
        assert skill.scripts[0].function is analyze

    def test_parameterized_decorator(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        @skill.script(name="custom-name", description="Custom desc")
        def my_func() -> str:
            return "data"

        assert len(skill.scripts) == 1
        assert skill.scripts[0].name == "custom-name"
        assert skill.scripts[0].description == "Custom desc"
        assert isinstance(skill.scripts[0], InlineSkillScript)
        assert skill.scripts[0].function is my_func

    def test_multiple_scripts(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        @skill.script
        def script_a() -> str:
            return "a"

        @skill.script
        def script_b() -> str:
            return "b"

        assert len(skill.scripts) == 2
        assert skill.scripts[0].name == "script_a"
        assert skill.scripts[1].name == "script_b"

    def test_async_script(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        @skill.script
        async def fetch_data() -> str:
            """Fetch remote data."""
            return "data"

        assert len(skill.scripts) == 1
        assert skill.scripts[0].name == "fetch_data"
        assert isinstance(skill.scripts[0], InlineSkillScript)
        assert skill.scripts[0].function is fetch_data

    def test_decorator_returns_original_function(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        @skill.script
        def original() -> str:
            return "original"

        @skill.script(name="aliased")
        def aliased() -> str:
            return "aliased"

        assert original() == "original"
        assert aliased() == "aliased"


# ---------------------------------------------------------------------------
# Skill with scripts attribute tests
# ---------------------------------------------------------------------------


class TestSkillWithScripts:
    """Tests for the Skill class with scripts attribute."""

    def test_default_empty_scripts(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        assert skill.scripts == []

    def test_scripts_at_construction(self) -> None:
        scripts = [InlineSkillScript(name="s1", function=lambda: None)]
        skill = InlineSkill(name="my-skill", description="test", instructions="body", scripts=scripts)
        assert len(skill.scripts) == 1
        assert skill.scripts[0].name == "s1"


# ---------------------------------------------------------------------------
# Runner tests
# ---------------------------------------------------------------------------


class TestSkillScriptRunnerProtocol:
    """Tests for the SkillScriptRunner protocol."""

    async def test_async_callable_satisfies_protocol(self) -> None:
        results: list[tuple] = []

        async def my_runner(skill, script, args=None):
            results.append((skill.name, script.name, args))
            return "executed"

        assert isinstance(my_runner, SkillScriptRunner)

        skill = InlineSkill(name="test-skill", description="test", instructions="body")
        script = FileSkillScript(name="my-script", full_path=f"{_ABS}/test/scripts/run.py")
        skill.scripts.append(script)

        result = await my_runner(skill, script, args={"key": "val"})

        assert result == "executed"
        assert len(results) == 1
        assert results[0] == ("test-skill", "my-script", {"key": "val"})

    async def test_callable_class_satisfies_protocol(self) -> None:
        class _CustomRunner:
            async def __call__(self, skill, script, args=None):
                return "custom result"

        runner = _CustomRunner()
        assert isinstance(runner, SkillScriptRunner)

        skill = InlineSkill(name="test-skill", description="test", instructions="body")
        script = InlineSkillScript(name="my-script", function=lambda: None)
        skill.scripts.append(script)

        result = await runner(skill, script, args={"key": "val"})
        assert result == "custom result"

    async def test_runner_returns_none(self) -> None:
        async def noop_runner(skill, script, args=None):
            return None

        skill = InlineSkill(name="test-skill", description="test", instructions="body")
        script = InlineSkillScript(name="s1", function=lambda: None)

        result = await noop_runner(skill, script)
        assert result is None

    async def test_runner_returns_object(self) -> None:
        async def dict_runner(skill, script, args=None):
            return {"exit_code": 0, "output": "ok"}

        skill = InlineSkill(name="test-skill", description="test", instructions="body")
        script = FileSkillScript(name="s1", full_path=f"{_ABS}/test/scripts/run.py")

        result = await dict_runner(skill, script)
        assert result == {"exit_code": 0, "output": "ok"}

    def test_sync_callable_satisfies_protocol(self) -> None:
        results: list[tuple] = []

        def my_runner(skill, script, args=None):
            results.append((skill.name, script.name, args))
            return "executed"

        assert isinstance(my_runner, SkillScriptRunner)

        skill = InlineSkill(name="test-skill", description="test", instructions="body")
        script = FileSkillScript(name="my-script", full_path=f"{_ABS}/test/scripts/run.py")
        skill.scripts.append(script)

        result = my_runner(skill, script, args={"key": "val"})

        assert result == "executed"
        assert len(results) == 1
        assert results[0] == ("test-skill", "my-script", {"key": "val"})

    def test_sync_callable_class_satisfies_protocol(self) -> None:
        class _SyncRunner:
            def __call__(self, skill, script, args=None):
                return "sync result"

        runner = _SyncRunner()
        assert isinstance(runner, SkillScriptRunner)

        skill = InlineSkill(name="test-skill", description="test", instructions="body")
        script = InlineSkillScript(name="my-script", function=lambda: None)
        skill.scripts.append(script)

        result = runner(skill, script, args={"key": "val"})
        assert result == "sync result"

    def test_sync_runner_returns_none(self) -> None:
        def noop_runner(skill, script, args=None):
            return None

        skill = InlineSkill(name="test-skill", description="test", instructions="body")
        script = InlineSkillScript(name="s1", function=lambda: None)

        result = noop_runner(skill, script)
        assert result is None

    def test_sync_runner_returns_object(self) -> None:
        def dict_runner(skill, script, args=None):
            return {"exit_code": 0, "output": "ok"}

        skill = InlineSkill(name="test-skill", description="test", instructions="body")
        script = FileSkillScript(name="s1", full_path=f"{_ABS}/test/scripts/run.py")

        result = dict_runner(skill, script)
        assert result == {"exit_code": 0, "output": "ok"}


# ---------------------------------------------------------------------------
# SkillsProvider static factory tests
# ---------------------------------------------------------------------------


class TestSkillsProviderFactories:
    """Tests for the SkillsProvider constructor auto-wiring behavior."""

    async def test_code_skills_with_scripts_creates_provider(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        assert len(_ctx(provider)[0]) == 1
        # Default runner auto-wired: base tools + run_skill_script
        assert any(hasattr(t, "name") and t.name == "run_skill_script" for t in _ctx(provider)[2])

    async def test_code_skills_no_scripts(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        # No scripts with functions, no runner, no resources — only load_skill
        assert len(_ctx(provider)[2]) == 1
        assert not any(hasattr(t, "name") and t.name == "run_skill_script" for t in _ctx(provider)[2])

    async def test_code_script_runs_directly(self) -> None:
        def my_function(key: str = "") -> str:
            return f"executed: {key}"

        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=my_function))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="s1", args={"key": "hello"})

        assert result == "executed: hello"

    async def test_no_scripts_no_tool(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        # No scripts at all — no run_skill_script tool
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        assert not any(hasattr(t, "name") and t.name == "run_skill_script" for t in _ctx(provider)[2])

    async def test_no_resources_no_read_skill_resource_tool(self) -> None:
        """When no skill has resources, read_skill_resource tool is not advertised."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        assert not any(hasattr(t, "name") and t.name == "read_skill_resource" for t in _ctx(provider)[2])

    async def test_resources_present_includes_read_skill_resource_tool(self) -> None:
        """When a skill has resources, read_skill_resource tool is advertised."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.resources.append(InlineSkillResource(name="ref", content="reference data"))
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        assert any(hasattr(t, "name") and t.name == "read_skill_resource" for t in _ctx(provider)[2])

    async def test_resources_present_includes_resource_instructions(self) -> None:
        """When a skill has resources, instructions mention read_skill_resource."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.resources.append(InlineSkillResource(name="ref", content="reference data"))
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        assert "read_skill_resource" in (_ctx(provider)[1] or "")

    async def test_no_resources_excludes_resource_instructions(self) -> None:
        """When no skill has resources, instructions do not mention read_skill_resource."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        assert "read_skill_resource" not in (_ctx(provider)[1] or "")

    async def test_read_skill_resource_tool_returns_content(self) -> None:
        """The read_skill_resource tool returns resource content when invoked."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.resources.append(InlineSkillResource(name="ref", content="reference data"))
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        read_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "read_skill_resource")
        result = await read_tool.func(skill_name="my-skill", resource_name="ref")
        assert result == "reference data"

    async def test_file_skills_with_custom_runner(self, tmp_path: Path) -> None:
        class _CustomRunner:
            async def __call__(self, skill, script, args=None):
                return "custom result"

        assert isinstance(_CustomRunner(), SkillScriptRunner)

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

        provider = SkillsProvider.from_paths(
            str(tmp_path),
            script_runner=_CustomRunner(),
        )
        await _init_provider(provider)
        assert any(hasattr(t, "name") and t.name == "run_skill_script" for t in _ctx(provider)[2])

    async def test_file_skills_with_sync_runner(self, tmp_path: Path) -> None:
        def sync_runner(skill, script, args=None):
            return "sync result"

        assert isinstance(sync_runner, SkillScriptRunner)

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

        provider = SkillsProvider.from_paths(
            str(tmp_path),
            script_runner=sync_runner,
        )
        await _init_provider(provider)
        assert any(hasattr(t, "name") and t.name == "run_skill_script" for t in _ctx(provider)[2])

    async def test_file_script_with_sync_runner_executes(self, tmp_path: Path) -> None:
        """A sync script_runner is awaitable through the provider's run_skill_script."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

        def sync_runner(skill, script, args=None):
            return f"sync: {script.name} args={args}"

        provider = SkillsProvider.from_paths(
            str(tmp_path),
            script_runner=sync_runner,
        )
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="run.py", args={"key": "val"})
        assert result == "sync: run.py args={'key': 'val'}"

    async def test_file_skills_with_callback_runner(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

        provider = SkillsProvider.from_paths(
            str(tmp_path),
            script_runner=_noop_script_runner,
        )
        await _init_provider(provider)
        assert any(hasattr(t, "name") and t.name == "run_skill_script" for t in _ctx(provider)[2])

    async def test_combined_skills(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "file-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: file-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )

        code_skill = InlineSkill(name="code-skill", description="test", instructions="body")
        code_skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(
            DeduplicatingSkillsSource(
                AggregatingSkillsSource([
                    FileSkillsSource(str(tmp_path), script_runner=_noop_script_runner),
                    InMemorySkillsSource([code_skill]),
                ])
            )
        )
        await _init_provider(provider)
        assert "file-skill" in _ctx(provider)[0]
        assert "code-skill" in _ctx(provider)[0]

    async def test_file_scripts_without_runner_no_error_at_init(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

        provider = SkillsProvider.from_paths(str(tmp_path))
        # Initialization succeeds; the error now surfaces at script.run() time
        await _init_provider(provider)

    async def test_file_script_error_without_runner(self) -> None:
        # A skill with both a code script and a file-based script
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="code-s", function=lambda: "ok"))
        skill.scripts.append(FileSkillScript(name="file-s", full_path=f"{_ABS}/test/scripts/s1.py"))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")

        # Code script works
        result = await run_tool.func(skill_name="my-skill", script_name="code-s")
        assert result == "ok"

        # File script without runner returns error
        result = await run_tool.func(skill_name="my-skill", script_name="file-s")
        assert "Error" in result
        assert "Failed to run" in result

    async def test_async_code_script_runs_directly(self) -> None:
        async def async_func(x: int = 0) -> str:
            return f"async: {x}"

        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=async_func))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="s1", args={"x": 42})
        assert result == "async: 42"

    async def test_code_script_returns_object(self) -> None:
        """Code-defined scripts can return non-string objects."""

        def returns_dict() -> dict:
            return {"status": "ok", "value": 42}

        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=returns_dict))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="s1")
        assert result == {"status": "ok", "value": 42}

    async def test_code_script_returns_none(self) -> None:
        """Code-defined scripts returning None pass through as None."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="s1")
        assert result is None

    async def test_script_with_path_errors_without_runner(self) -> None:
        """A file-based script without a runner should return an error."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="code-s", function=lambda: "ok"))
        skill.scripts.append(FileSkillScript(name="path-s", full_path=f"{_ABS}/test/scripts/s1.py"))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")

        # Code-only script still works
        result = await run_tool.func(skill_name="my-skill", script_name="code-s")
        assert result == "ok"

        # Path+function script without runner returns error
        result = await run_tool.func(skill_name="my-skill", script_name="path-s")
        assert "Error" in result
        assert "script_runner" in result or "Failed to run" in result

    async def test_run_skill_script_error_on_missing_skill(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="nonexistent", script_name="s1")
        assert "Error" in result
        assert "nonexistent" in result

    async def test_run_skill_script_sync_with_kwargs(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        @skill.script
        def greet(name: str, **kwargs: Any) -> str:
            user_id = kwargs.get("user_id", "unknown")
            return f"Hello {name} (user={user_id})"

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._run_skill_script(
            _raw_skills(provider), "my-skill", "greet", args={"name": "Alice"}, user_id="u42"
        )
        assert result == "Hello Alice (user=u42)"

    async def test_run_skill_script_async_with_kwargs(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        @skill.script
        async def fetch(url: str, **kwargs: Any) -> str:
            token = kwargs.get("auth_token", "none")
            return f"fetched {url} with token={token}"

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._run_skill_script(
            _raw_skills(provider), "my-skill", "fetch", args={"url": "http://x"}, auth_token="abc"
        )
        assert result == "fetched http://x with token=abc"

    async def test_run_skill_script_without_kwargs_ignores_extra_args(self) -> None:
        """Script functions without **kwargs should still work when runtime kwargs are passed."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        @skill.script
        def simple(query: str) -> str:
            return f"result: {query}"

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._run_skill_script(
            _raw_skills(provider), "my-skill", "simple", args={"query": "test"}, user_id="ignored"
        )
        assert result == "result: test"

    async def test_run_skill_script_conflicting_args_and_kwargs_raises(self) -> None:
        """Conflicting keys in args and kwargs should raise TypeError."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        @skill.script
        def process(**kwargs: Any) -> str:
            return f"mode={kwargs.get('mode', 'default')}"

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._run_skill_script(
            _raw_skills(provider), "my-skill", "process", args={"mode": "llm-value"}, mode="runtime-value"
        )
        assert "Error" in result

    async def test_run_skill_script_error_on_missing_script(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="nonexistent")
        assert "Error" in result
        assert "nonexistent" in result

    async def test_run_skill_script_error_on_empty_names(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")

        result = await run_tool.func(skill_name="", script_name="s1")
        assert "Error" in result

        result = await run_tool.func(skill_name="my-skill", script_name="")
        assert "Error" in result

    async def test_instructions_include_script_runner_hints(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        assert "run_skill_script" in _ctx(provider)[1]
        assert "not as top-level tool parameters" in _ctx(provider)[1]

    async def test_no_scripts_no_runner_no_script_instructions(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        # No scripts and no runner — instructions should not mention run_skill_script
        assert "run_skill_script" not in (_ctx(provider)[1] or "")

    async def test_tool_schema_args_description_mentions_key_format(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        args_desc = run_tool.parameters()["properties"]["args"]["description"]
        assert "without leading dashes" in args_desc
        assert "script implementation or configured runner" in args_desc

    async def test_require_script_approval_sets_approval_mode(self) -> None:
        """When require_script_approval=True, the run_skill_script tool has approval_mode='always_require'."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill], require_script_approval=True)
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        assert run_tool.approval_mode == "always_require"

    async def test_require_script_approval_false_by_default(self) -> None:
        """By default, the run_skill_script tool has approval_mode='never_require'."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        assert run_tool.approval_mode == "never_require"

    async def test_require_script_approval_does_not_affect_other_tools(self) -> None:
        """The load_skill tool should never require approval."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider([skill], require_script_approval=True)
        await _init_provider(provider)
        other_tools = [t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name != "run_skill_script"]
        assert len(other_tools) == 1
        for t in other_tools:
            assert t.approval_mode == "never_require"

    async def test_code_script_exception_returns_error(self) -> None:
        """A code script function that raises should return an error string."""

        def failing_script() -> str:
            raise RuntimeError("Something went wrong")

        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="boom", function=failing_script))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="boom")
        assert "Error" in result
        assert "boom" in result
        assert "Something went wrong" not in result

    async def test_custom_template_without_runner_placeholder_raises(self) -> None:
        """Provider with code scripts and custom template missing {runner_instructions} raises."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(
            [skill],
            instruction_template="Skills: {skills}",
        )
        with pytest.raises(ValueError, match="runner_instructions"):
            await _init_provider(provider)


# ---------------------------------------------------------------------------
# File script discovery tests
# ---------------------------------------------------------------------------


class TestFileScriptDiscovery:
    """Tests for automatic .py script discovery in skill directories."""

    async def test_discovers_py_files(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "analyze.py").write_text("print('hi')", encoding="utf-8")

        skills = await _discover_file_skills_for_test(str(tmp_path))
        assert "my-skill" in skills
        assert len(skills["my-skill"].scripts) == 1
        assert skills["my-skill"].scripts[0].name == "analyze.py"

    async def test_discovered_script_has_absolute_full_path(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (scripts_dir / "generate.py").write_text("print('gen')", encoding="utf-8")

        skills = await _discover_file_skills_for_test(str(tmp_path))
        script = skills["my-skill"].scripts[0]
        assert script.full_path is not None
        assert os.path.isabs(script.full_path)
        expected = str(Path(str(skill_dir), "scripts", "generate.py"))
        assert script.full_path == expected

    async def test_discovers_nested_scripts(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (scripts_dir / "generate.py").write_text("print('gen')", encoding="utf-8")

        skills = await _discover_file_skills_for_test(str(tmp_path))
        assert len(skills["my-skill"].scripts) == 1
        assert skills["my-skill"].scripts[0].name == "scripts/generate.py"

    async def test_no_scripts_when_no_py_files(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "readme.md").write_text("# Docs", encoding="utf-8")

        skills = await _discover_file_skills_for_test(str(tmp_path))
        assert len(skills["my-skill"].scripts) == 0


class TestCustomScriptExtensions:
    """Tests for the script_extensions parameter (parity with resource_extensions)."""

    async def test_custom_script_extensions_via_get_skills(self, tmp_path: Path) -> None:
        """get_skills() forwards script_extensions to _discover_script_files."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "analyze.py").write_text("print('hi')", encoding="utf-8")
        (skill_dir / "run.sh").write_text("#!/bin/bash", encoding="utf-8")

        # Default: only .py discovered
        skills_default = await _discover_file_skills_for_test(str(tmp_path))
        script_names_default = [s.name for s in skills_default["my-skill"].scripts]
        assert "analyze.py" in script_names_default
        assert "run.sh" not in script_names_default

        # Custom: only .sh discovered
        skills_custom = await _discover_file_skills_for_test(str(tmp_path), script_extensions=(".sh",))
        script_names_custom = [s.name for s in skills_custom["my-skill"].scripts]
        assert "run.sh" in script_names_custom
        assert "analyze.py" not in script_names_custom

    async def test_custom_script_extensions_via_provider(self, tmp_path: Path) -> None:
        """SkillsProvider accepts custom script_extensions."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "analyze.py").write_text("print('hi')", encoding="utf-8")
        (skill_dir / "run.sh").write_text("#!/bin/bash", encoding="utf-8")

        # Only discover .sh scripts
        provider = SkillsProvider.from_paths(
            str(tmp_path),
            script_extensions=(".sh",),
            script_runner=_noop_script_runner,
        )
        await _init_provider(provider)
        skill = _ctx(provider)[0]["my-skill"]
        script_names = [s.name for s in skill.scripts]
        assert "run.sh" in script_names
        assert "analyze.py" not in script_names

    async def test_multiple_script_extensions(self, tmp_path: Path) -> None:
        """Multiple script extensions can be specified."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "analyze.py").write_text("print('hi')", encoding="utf-8")
        (skill_dir / "run.sh").write_text("#!/bin/bash", encoding="utf-8")
        (skill_dir / "notes.txt").write_text("notes", encoding="utf-8")

        provider = SkillsProvider.from_paths(
            str(tmp_path),
            script_extensions=(".py", ".sh"),
            script_runner=_noop_script_runner,
        )
        await _init_provider(provider)
        skill = _ctx(provider)[0]["my-skill"]
        script_names = [s.name for s in skill.scripts]
        assert "analyze.py" in script_names
        assert "run.sh" in script_names
        assert "notes.txt" not in script_names

    def test_default_script_extensions_unchanged(self) -> None:
        """DEFAULT_SCRIPT_EXTENSIONS contains only .py."""
        assert DEFAULT_SCRIPT_EXTENSIONS == (".py",)


# ---------------------------------------------------------------------------
# _create_instructions with scripts tests
# ---------------------------------------------------------------------------


class TestCreateInstructionsWithScripts:
    """Tests for script metadata in skill advertisement."""

    def test_excludes_script_count(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        result = SkillsProvider._create_instructions(None, [skill])
        assert result is not None
        assert "<scripts>" not in result

    def test_no_scripts_element_when_empty(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")

        result = SkillsProvider._create_instructions(None, [skill])
        assert result is not None
        assert "<scripts>" not in result


# ---------------------------------------------------------------------------
# _load_skill with scripts tests
# ---------------------------------------------------------------------------


class TestLoadSkillWithScripts:
    """Tests for script metadata in load_skill output."""

    async def test_code_skill_includes_scripts_element(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="analyze", description="Run analysis", function=lambda: None))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "my-skill")

        assert "<scripts>" in result
        assert 'name="analyze"' in result
        assert 'description="Run analysis"' in result

    async def test_code_skill_no_scripts_element(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "my-skill")
        assert "<scripts>" not in result

    async def test_code_skill_scripts_element_contains_parameters(self) -> None:
        """Scripts XML includes parameters schema when the function has typed parameters."""

        def analyze(query: str, limit: int = 10) -> str:
            return "result"

        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="analyze", description="Run analysis", function=analyze))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = provider._load_skill(_raw_skills(provider), "my-skill")

        assert "<scripts>" in result
        assert 'name="analyze"' in result
        assert "<parameters_schema>" in result
        assert '"query"' in result


class TestReadSkillResourceWithScripts:
    """Tests for _read_skill_resource falling back to scripts."""

    async def test_reads_script_with_static_content(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="generate.py", function=lambda: "print('hello')"))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "generate.py")
        # Scripts are not returned via _read_skill_resource
        assert "not found" in result

    async def test_script_not_accessible_via_read_resource(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="run.py", function=lambda: "script output"))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "run.py")
        # Scripts are separate from resources
        assert "not found" in result

    async def test_async_script_not_accessible_via_read_resource(self) -> None:
        async def async_script() -> str:
            return "async output"

        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="run.py", function=async_script))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "run.py")
        assert "not found" in result

    async def test_script_case_insensitive_not_in_resources(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="Generate.py", function=lambda: "code"))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "generate.py")
        assert "not found" in result

    async def test_resource_takes_priority_over_script(self) -> None:
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.resources.append(InlineSkillResource(name="data.py", content="resource content"))
        skill.scripts.append(InlineSkillScript(name="data.py", function=lambda: "script content"))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "data.py")
        assert result == "resource content"

    async def test_script_function_error_not_exposed_via_resources(self) -> None:
        def failing_script() -> str:
            raise RuntimeError("boom")

        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="bad.py", function=failing_script))

        provider = SkillsProvider([skill])
        await _init_provider(provider)
        result = await provider._read_skill_resource(_raw_skills(provider), "my-skill", "bad.py")
        assert "not found" in result


# ---------------------------------------------------------------------------
# Tests: _generate_function_schema
# ---------------------------------------------------------------------------


class TestGenerateFunctionSchema:
    """Tests for SkillScript.parameters_schema lazy generation."""

    def test_simple_function(self) -> None:
        def analyze(query: str, limit: int) -> str:
            return ""

        script = InlineSkillScript(name="analyze", function=analyze)
        schema = script.parameters_schema
        assert schema is not None
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "limit" in schema["properties"]
        assert "query" in schema["required"]
        assert "limit" in schema["required"]

    def test_optional_parameter(self) -> None:
        def fetch(url: str, timeout: int = 30) -> str:
            return ""

        script = InlineSkillScript(name="fetch", function=fetch)
        schema = script.parameters_schema
        assert schema is not None
        assert "url" in schema["properties"]
        assert "timeout" in schema["properties"]
        assert "url" in schema["required"]
        # timeout has a default, so it should NOT be in required
        assert "timeout" not in schema.get("required", [])

    def test_no_parameters_returns_none(self) -> None:
        def noop() -> None:
            pass

        script = InlineSkillScript(name="noop", function=noop)
        assert script.parameters_schema is None

    def test_skips_self_and_cls(self) -> None:
        def method(self, query: str) -> str:  # noqa: ANN001
            return ""

        script = InlineSkillScript(name="method", function=method)
        schema = script.parameters_schema
        assert schema is not None
        assert "self" not in schema["properties"]
        assert "query" in schema["properties"]

    def test_skips_var_keyword(self) -> None:
        def func(name: str, **kwargs: Any) -> str:
            return ""

        script = InlineSkillScript(name="func", function=func)
        schema = script.parameters_schema
        assert schema is not None
        assert "kwargs" not in schema["properties"]
        assert "name" in schema["properties"]

    def test_async_function(self) -> None:
        async def fetch_data(url: str) -> str:
            return ""

        script = InlineSkillScript(name="fetch_data", function=fetch_data)
        schema = script.parameters_schema
        assert schema is not None
        assert "url" in schema["properties"]

    def test_bool_and_float_types(self) -> None:
        def process(verbose: bool, threshold: float) -> None:
            pass

        script = InlineSkillScript(name="process", function=process)
        schema = script.parameters_schema
        assert schema is not None
        assert "verbose" in schema["properties"]
        assert "threshold" in schema["properties"]

    def test_lazy_generation_is_cached(self) -> None:
        def analyze(query: str) -> str:
            return ""

        script = InlineSkillScript(name="analyze", function=analyze)
        first = script.parameters_schema
        second = script.parameters_schema
        assert first is second


# ---------------------------------------------------------------------------
# Tests: _create_script_element
# ---------------------------------------------------------------------------


class TestCreateScriptElement:
    """Tests for _create_script_element."""

    def test_name_only(self) -> None:
        s = FileSkillScript(name="run.py", full_path=f"{_ABS}/test/scripts/run.py")
        elem = _create_script_element(s)
        assert elem == '  <script name="run.py"/>'

    def test_with_description(self) -> None:
        s = FileSkillScript(name="run.py", description="Execute script.", full_path=f"{_ABS}/test/scripts/run.py")
        elem = _create_script_element(s)
        assert elem == '  <script name="run.py" description="Execute script."/>'

    def test_xml_escapes_name(self) -> None:
        s = FileSkillScript(name='script"special', full_path=f"{_ABS}/test/scripts/s.py")
        elem = _create_script_element(s)
        assert "&quot;" in elem

    def test_xml_escapes_description(self) -> None:
        s = FileSkillScript(
            name="run.py", description='Uses <tags> & "quotes"', full_path=f"{_ABS}/test/scripts/run.py"
        )
        elem = _create_script_element(s)
        assert "&lt;tags&gt;" in elem
        assert "&amp;" in elem
        assert "&quot;" in elem

    def test_includes_parameters_for_code_script(self) -> None:
        def analyze(query: str, limit: int = 10) -> str:
            return ""

        s = InlineSkillScript(name="analyze", description="Run analysis", function=analyze)
        elem = _create_script_element(s)
        assert "<parameters_schema>" in elem
        assert "</parameters_schema>" in elem
        assert "query" in elem
        assert "&quot;" not in elem

    def test_no_parameters_for_file_script(self) -> None:
        s = FileSkillScript(name="run.py", full_path=f"{_ABS}/test/scripts/run.py")
        elem = _create_script_element(s)
        assert "<parameters_schema>" not in elem


# ---------------------------------------------------------------------------
# Tests: SkillScript.parameters_schema
# ---------------------------------------------------------------------------


class TestSkillScriptParametersSchema:
    """Tests for parameters_schema auto-generation on SkillScript."""

    def test_auto_generated_from_function(self) -> None:
        def analyze(query: str) -> str:
            return ""

        script = InlineSkillScript(name="analyze", function=analyze)
        assert script.parameters_schema is not None
        assert "query" in script.parameters_schema["properties"]

    def test_none_for_file_based_script(self) -> None:
        script = FileSkillScript(name="run.py", full_path=f"{_ABS}/test/scripts/run.py")
        assert script.parameters_schema is None

    def test_no_params_function_returns_none(self) -> None:
        def noop() -> None:
            pass

        script = InlineSkillScript(name="noop", function=noop)
        assert script.parameters_schema is None

    def test_kwargs_only_function_returns_none(self) -> None:
        def func(**kwargs: Any) -> str:
            return ""

        script = InlineSkillScript(name="func", function=func)
        assert script.parameters_schema is None

    def test_no_params_caching_does_not_reinspect(self) -> None:
        """parameters_schema caches the None result and does not re-inspect."""
        from unittest.mock import patch

        def noop() -> None:
            pass

        script = InlineSkillScript(name="noop", function=noop)
        first = script.parameters_schema
        assert first is None
        # Second access should not create a new FunctionTool
        with patch("agent_framework._skills.FunctionTool", side_effect=RuntimeError("should not be called")):
            second = script.parameters_schema
        assert second is None


# ---------------------------------------------------------------------------
# Tests: Source-based merging behavior
# ---------------------------------------------------------------------------


class TestLoadSkillsMerging:
    """Tests for source-based merging of file-based and code-defined skills."""

    def test_code_skill_with_invalid_name_raises(self) -> None:
        """Code skills with invalid metadata (e.g. uppercase name) raise at construction."""
        with pytest.raises(ValueError, match="Invalid skill name"):
            InlineSkill(name="INVALID_NAME", description="valid", instructions="body")

    async def test_file_skill_takes_precedence_over_code_skill(self, tmp_path: Path) -> None:
        """When file-based and code-defined skills share a name, file-based wins."""
        from agent_framework._skills import (
            AggregatingSkillsSource,
            DeduplicatingSkillsSource,
            FileSkillsSource,
            InMemorySkillsSource,
        )

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: File skill.\n---\nFile body.",
            encoding="utf-8",
        )

        code_skill = InlineSkill(name="my-skill", description="Code skill.", instructions="Code body.")

        source = DeduplicatingSkillsSource(
            AggregatingSkillsSource([
                FileSkillsSource(str(tmp_path)),
                InMemorySkillsSource([code_skill]),
            ])
        )
        result = await source.get_skills()
        skills_by_name = {s.name: s for s in result}
        assert "my-skill" in skills_by_name
        assert skills_by_name["my-skill"].path is not None  # file-based skill has path set


# ---------------------------------------------------------------------------
# Tests: SkillsSource classes
# ---------------------------------------------------------------------------


class TestSkillsSource:
    """Tests for the abstract SkillsSource and concrete implementations."""

    async def test_file_skills_source_discovers_skills(self, tmp_path: Path) -> None:
        """FileSkillsSource discovers skills from SKILL.md files."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test skill.\n---\nBody.",
            encoding="utf-8",
        )

        source = FileSkillsSource(str(tmp_path))
        skills = await source.get_skills()
        assert len(skills) == 1
        assert skills[0].name == "my-skill"
        assert skills[0].path is not None

    async def test_file_skills_source_with_extensions(self, tmp_path: Path) -> None:
        """FileSkillsSource resource_extensions controls extension filtering."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test skill.\n---\nBody.",
            encoding="utf-8",
        )
        (skill_dir / "data.json").write_text("{}", encoding="utf-8")
        (skill_dir / "data.csv").write_text("a,b", encoding="utf-8")

        # Only allow .json resources
        source = FileSkillsSource(str(tmp_path), resource_extensions=(".json",))
        skills = await source.get_skills()
        assert len(skills) == 1
        resource_names = [r.name for r in skills[0].resources]
        assert "data.json" in resource_names
        assert "data.csv" not in resource_names

    async def test_in_memory_skills_source_returns_all_skills(self) -> None:
        """InMemorySkillsSource returns all provided skills."""
        from agent_framework import InMemorySkillsSource

        s1 = InlineSkill(name="skill-a", description="A", instructions="body")
        s2 = InlineSkill(name="skill-b", description="B", instructions="body")

        source = InMemorySkillsSource([s1, s2])
        skills = await source.get_skills()
        assert len(skills) == 2
        assert skills[0].name == "skill-a"
        assert skills[1].name == "skill-b"

    async def test_aggregating_source_combines_sources(self) -> None:
        """Aggregating source concatenates results from multiple sources."""
        from agent_framework import AggregatingSkillsSource, InMemorySkillsSource

        s1 = InlineSkill(name="skill-a", description="A", instructions="body")
        s2 = InlineSkill(name="skill-b", description="B", instructions="body")

        source = AggregatingSkillsSource([
            InMemorySkillsSource([s1]),
            InMemorySkillsSource([s2]),
        ])
        skills = await source.get_skills()
        names = [s.name for s in skills]
        assert names == ["skill-a", "skill-b"]

    async def test_filtering_source_filters_by_predicate(self) -> None:
        """FilteringSkillsSource only returns skills matching the predicate."""
        from agent_framework import FilteringSkillsSource, InMemorySkillsSource

        s1 = InlineSkill(name="keep-me", description="keep", instructions="body")
        s2 = InlineSkill(name="drop-me", description="drop", instructions="body")

        source = FilteringSkillsSource(
            InMemorySkillsSource([s1, s2]),
            predicate=lambda s: s.name.startswith("keep"),
        )
        skills = await source.get_skills()
        assert len(skills) == 1
        assert skills[0].name == "keep-me"

    async def test_deduplicating_source_removes_duplicates(self) -> None:
        """DeduplicatingSkillsSource keeps first skill with each name."""
        from agent_framework import DeduplicatingSkillsSource, InMemorySkillsSource

        s1 = InlineSkill(name="my-skill", description="first", instructions="body1")
        s2 = InlineSkill(name="my-skill", description="second", instructions="body2")
        s3 = InlineSkill(name="other", description="other", instructions="body3")

        source = DeduplicatingSkillsSource(InMemorySkillsSource([s1, s2, s3]))
        skills = await source.get_skills()
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"my-skill", "other"}
        # First one wins
        my_skill = next(s for s in skills if s.name == "my-skill")
        assert my_skill.description == "first"

    async def test_delegating_source_delegates(self) -> None:
        """DelegatingSkillsSource delegates to inner source by default."""
        from agent_framework import DelegatingSkillsSource, InMemorySkillsSource

        skill = InlineSkill(name="test-skill", description="test", instructions="body")
        inner = InMemorySkillsSource([skill])

        class PassthroughSource(DelegatingSkillsSource):
            pass

        source = PassthroughSource(inner)
        assert source.inner_source is inner
        skills = await source.get_skills()
        assert len(skills) == 1
        assert skills[0].name == "test-skill"

    async def test_provider_with_source_parameter(self, tmp_path: Path) -> None:
        """SkillsProvider works with the new source= parameter."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test skill.\n---\nBody.",
            encoding="utf-8",
        )

        source = FileSkillsSource(str(tmp_path))
        provider = SkillsProvider(source)
        await _init_provider(provider)
        assert "my-skill" in _ctx(provider)[0]

    async def test_provider_source_overrides_legacy_params(self, tmp_path: Path) -> None:
        """When source= is provided, skill_paths and skills are ignored."""
        from agent_framework import InMemorySkillsSource

        code_skill = InlineSkill(name="code-skill", description="test", instructions="body")
        source = InMemorySkillsSource([code_skill])

        # Pass skill_paths that would normally discover file skills — should be ignored
        provider = SkillsProvider(source)
        await _init_provider(provider)
        assert "code-skill" in _ctx(provider)[0]
        assert len(_ctx(provider)[0]) == 1

    async def test_composed_source_pipeline(self, tmp_path: Path) -> None:
        """Full source composition: file + code → aggregate → dedup → filter."""
        from agent_framework import (
            AggregatingSkillsSource,
            DeduplicatingSkillsSource,
            FileSkillsSource,
            FilteringSkillsSource,
            InMemorySkillsSource,
        )

        skill_dir = tmp_path / "file-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: file-skill\ndescription: File.\n---\nBody.",
            encoding="utf-8",
        )

        code_skill = InlineSkill(name="code-skill", description="Code.", instructions="Body.")
        internal = InlineSkill(name="internal", description="Internal.", instructions="Body.")

        source = FilteringSkillsSource(
            DeduplicatingSkillsSource(
                AggregatingSkillsSource([
                    FileSkillsSource(str(tmp_path)),
                    InMemorySkillsSource([code_skill, internal]),
                ])
            ),
            predicate=lambda s: s.name != "internal",
        )

        skills = await source.get_skills()
        names = {s.name for s in skills}
        assert names == {"file-skill", "code-skill"}
        assert "internal" not in names


# ---------------------------------------------------------------------------
# Tests: Source composition (replaces SkillsProviderBuilder)
# ---------------------------------------------------------------------------


class TestSourceComposition:
    """Tests for composing sources directly instead of using a builder."""

    async def test_file_skills_source_with_provider(self, tmp_path: Path) -> None:
        """FileSkillsSource with dedup creates a working provider."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test.\n---\nBody.",
            encoding="utf-8",
        )

        provider = SkillsProvider(DeduplicatingSkillsSource(FileSkillsSource(str(tmp_path))))
        await _init_provider(provider)
        assert "my-skill" in _ctx(provider)[0]

    async def test_code_skills_with_provider(self) -> None:
        """InMemorySkillsSource with code skills creates a working provider."""
        skill = InlineSkill(name="code-skill", description="test", instructions="body")
        provider = SkillsProvider(DeduplicatingSkillsSource(InMemorySkillsSource([skill])))
        await _init_provider(provider)
        assert "code-skill" in _ctx(provider)[0]

    async def test_multiple_code_skills(self) -> None:
        """InMemorySkillsSource with multiple skills registers them all."""
        s1 = InlineSkill(name="skill-a", description="A", instructions="body")
        s2 = InlineSkill(name="skill-b", description="B", instructions="body")
        provider = SkillsProvider(DeduplicatingSkillsSource(InMemorySkillsSource([s1, s2])))
        await _init_provider(provider)
        assert "skill-a" in _ctx(provider)[0]
        assert "skill-b" in _ctx(provider)[0]

    async def test_custom_source_with_provider(self) -> None:
        """Custom source passed to SkillsProvider works."""
        skill = InlineSkill(name="custom", description="test", instructions="body")
        source = InMemorySkillsSource([skill])
        provider = SkillsProvider(DeduplicatingSkillsSource(source))
        await _init_provider(provider)
        assert "custom" in _ctx(provider)[0]

    async def test_filtering_source_excludes_skills(self) -> None:
        """FilteringSkillsSource excludes matching skills."""
        from agent_framework import FilteringSkillsSource

        s1 = InlineSkill(name="keep-me", description="keep", instructions="body")
        s2 = InlineSkill(name="drop-me", description="drop", instructions="body")

        source = DeduplicatingSkillsSource(
            FilteringSkillsSource(
                InMemorySkillsSource([s1, s2]),
                predicate=lambda s: s.name.startswith("keep"),
            )
        )
        provider = SkillsProvider(source)
        await _init_provider(provider)
        assert "keep-me" in _ctx(provider)[0]
        assert "drop-me" not in _ctx(provider)[0]

    async def test_dedup_across_sources(self) -> None:
        """DeduplicatingSkillsSource deduplicates across aggregated sources."""
        s1 = InlineSkill(name="dup", description="first", instructions="body1")
        s2 = InlineSkill(name="dup", description="second", instructions="body2")

        source = DeduplicatingSkillsSource(
            AggregatingSkillsSource([
                InMemorySkillsSource([s1]),
                InMemorySkillsSource([s2]),
            ])
        )
        provider = SkillsProvider(source)
        await _init_provider(provider)
        assert len(_ctx(provider)[0]) == 1
        assert _ctx(provider)[0]["dup"].description == "first"

    async def test_file_source_with_script_runner(self, tmp_path: Path) -> None:
        """FileSkillsSource with script_runner enables script execution."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

        source = DeduplicatingSkillsSource(FileSkillsSource(str(tmp_path), script_runner=_noop_script_runner))
        provider = SkillsProvider(source)
        await _init_provider(provider)
        assert "my-skill" in _ctx(provider)[0]
        assert any(hasattr(t, "name") and t.name == "run_skill_script" for t in _ctx(provider)[2])

    async def test_script_approval_on_provider(self) -> None:
        """SkillsProvider with require_script_approval sets the approval mode."""
        skill = InlineSkill(name="my-skill", description="test", instructions="body")
        skill.scripts.append(InlineSkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(
            DeduplicatingSkillsSource(InMemorySkillsSource([skill])),
            require_script_approval=True,
        )
        await _init_provider(provider)
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        assert run_tool.approval_mode == "always_require"

    async def test_empty_source(self) -> None:
        """Empty InMemorySkillsSource creates an empty provider."""
        provider = SkillsProvider(InMemorySkillsSource([]))
        await _init_provider(provider)
        assert len(_ctx(provider)[0]) == 0

    async def test_per_source_runner(self, tmp_path: Path) -> None:
        """Per-source script runner is used when set on FileSkillsSource."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

        call_log: list[str] = []

        async def source_runner(skill: Any, script: Any, args: Any = None) -> str:
            call_log.append("source")
            return "source"

        source = DeduplicatingSkillsSource(FileSkillsSource(str(tmp_path), script_runner=source_runner))
        provider = SkillsProvider(source)
        await _init_provider(provider)

        # The source-level runner should be discovered and used
        run_tool = next(t for t in _ctx(provider)[2] if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="run.py")
        assert result == "source"
        assert call_log == ["source"]


# ---------------------------------------------------------------------------
# Tests: SkillsProvider factory methods
# ---------------------------------------------------------------------------


class TestSkillsProviderFactoryMethods:
    """Tests for the SkillsProvider factory class methods."""

    def test_from_paths_creates_provider(self, tmp_path: Path) -> None:
        """from_paths returns a SkillsProvider instance."""
        provider = SkillsProvider.from_paths(str(tmp_path))
        assert isinstance(provider, SkillsProvider)
        assert provider.source_id == "agent_skills"

    async def test_from_paths_discovers_skills(self, tmp_path: Path) -> None:
        """from_paths discovers file-based skills."""
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider.from_paths(str(tmp_path))
        await _init_provider(provider)
        assert "my-skill" in _ctx(provider)[0]

    async def test_from_paths_accepts_multiple_paths(self, tmp_path: Path) -> None:
        """from_paths accepts a sequence of paths."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        _write_skill(dir1, "skill-a")
        _write_skill(dir2, "skill-b")
        provider = SkillsProvider.from_paths([str(dir1), str(dir2)])
        await _init_provider(provider)
        assert len(_ctx(provider)[0]) == 2

    async def test_from_paths_custom_source_id(self, tmp_path: Path) -> None:
        """from_paths supports custom source_id."""
        provider = SkillsProvider.from_paths(str(tmp_path), source_id="custom")
        assert provider.source_id == "custom"

    async def test_from_paths_with_resource_extensions(self, tmp_path: Path) -> None:
        """from_paths respects resource_extensions."""
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider.from_paths(str(tmp_path), resource_extensions=(".json",))
        await _init_provider(provider)
        assert "my-skill" in _ctx(provider)[0]

    def test_init_with_skills_creates_provider(self) -> None:
        """Constructor with skill list returns a SkillsProvider instance."""
        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        provider = SkillsProvider([skill])
        assert isinstance(provider, SkillsProvider)

    async def test_init_with_skills_registers_skills(self) -> None:
        """Constructor with skill list registers code-defined skills."""
        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        assert "test-skill" in _ctx(provider)[0]

    async def test_init_with_empty_list(self) -> None:
        """Constructor with empty list creates provider with no skills."""
        provider = SkillsProvider([])
        await _init_provider(provider)
        assert len(_ctx(provider)[0]) == 0

    async def test_init_with_skills_and_options(self) -> None:
        """Constructor with skills passes through keyword options."""
        skill = InlineSkill(name="my-skill", description="Test", instructions="Body")
        provider = SkillsProvider(
            [skill],
            require_script_approval=True,
            source_id="custom",
        )
        assert provider.source_id == "custom"
        assert provider._require_script_approval is True

    def test_init_with_source_creates_provider(self) -> None:
        """Constructor with SkillsSource returns a SkillsProvider instance."""
        from agent_framework import InMemorySkillsSource

        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        source = InMemorySkillsSource([skill])
        provider = SkillsProvider(source)
        assert isinstance(provider, SkillsProvider)

    async def test_init_with_source_uses_provided_source(self) -> None:
        """Constructor with SkillsSource uses the exact source given."""
        from agent_framework import InMemorySkillsSource

        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        source = InMemorySkillsSource([skill])
        provider = SkillsProvider(source)
        await _init_provider(provider)
        assert "test-skill" in _ctx(provider)[0]


# ---------------------------------------------------------------------------
# Tests: disable_caching
# ---------------------------------------------------------------------------


class TestDisableCaching:
    """Tests for the disable_caching option."""

    async def test_default_caching_enabled(self) -> None:
        """By default, _get_or_create_context only builds once."""
        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        provider = SkillsProvider([skill])
        await _init_provider(provider)
        first_ctx = provider._cached_context  # pyright: ignore[reportPrivateUsage]
        assert first_ctx is not None

        # Calling _get_or_create_context again should return cached result
        skills, _, _ = await provider._get_or_create_context()
        assert skills is first_ctx[0]  # Same object reference

    async def test_disable_caching_rebuilds_on_every_call(self) -> None:
        """With disable_caching=True, _create_context rebuilds every time."""
        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        provider = SkillsProvider([skill], disable_caching=True)
        await _init_provider(provider)
        first_ctx = provider._cached_context  # pyright: ignore[reportPrivateUsage]
        assert first_ctx is not None

        # Calling _create_context again should rebuild
        skills, _, _ = await provider._create_context()
        assert skills is not first_ctx[0]  # Different object

    async def test_disable_caching_via_constructor(self) -> None:
        """disable_caching works via the primary constructor."""
        from agent_framework import InMemorySkillsSource

        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        source = InMemorySkillsSource([skill])
        provider = SkillsProvider(source, disable_caching=True)
        assert provider._disable_caching is True

    async def test_caching_enabled_by_default(self) -> None:
        """SkillsProvider defaults to caching enabled."""
        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        provider = SkillsProvider([skill])
        assert provider._disable_caching is False

    async def test_disable_caching_before_run_rebuilds(self) -> None:
        """before_run with disable_caching=True calls _create_context each time."""
        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        provider = SkillsProvider([skill], disable_caching=True)
        context = SessionContext(input_messages=[])
        await provider.before_run(agent=AsyncMock(), session=AsyncMock(), context=context, state={})
        assert context.instructions  # Skills instructions were added


# ---------------------------------------------------------------------------
# Tests: SkillsProvider constructor edge cases
# ---------------------------------------------------------------------------


class TestSkillsProviderConstructorEdgeCases:
    """Tests for SkillsProvider constructor source coercion."""

    async def test_single_skill_accepted(self) -> None:
        """A single Skill (not a list) is accepted and wrapped."""
        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        provider = SkillsProvider(skill)
        await _init_provider(provider)
        skills = _ctx(provider)[0]
        assert len(skills) == 1
        assert "test-skill" in skills

    async def test_template_missing_skills_placeholder_raises(self) -> None:
        """Instruction template without {skills} raises ValueError."""
        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        provider = SkillsProvider([skill], instruction_template="No placeholder here.")
        with pytest.raises(ValueError, match="skills"):
            await _init_provider(provider)

    def test_string_source_rejected_with_helpful_error(self) -> None:
        """Passing a string (path) to SkillsProvider raises TypeError."""
        with pytest.raises(TypeError, match="from_paths"):
            SkillsProvider("./skills")  # type: ignore[arg-type]

    def test_path_source_rejected_with_helpful_error(self) -> None:
        """Passing a Path to SkillsProvider raises TypeError."""
        with pytest.raises(TypeError, match="from_paths"):
            SkillsProvider(Path("./skills"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: InlineSkill content caching
# ---------------------------------------------------------------------------


class TestInlineSkillContentCaching:
    """Tests for InlineSkill.content caching."""

    def test_content_cached_after_first_access(self) -> None:
        """InlineSkill.content returns the same object on subsequent accesses."""
        skill = InlineSkill(name="test-skill", description="Test", instructions="Body")
        first = skill.content
        second = skill.content
        assert first is second  # Same object (cached)
        assert "<name>test-skill</name>" in first
