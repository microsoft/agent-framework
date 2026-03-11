# Copyright (c) Microsoft. All rights reserved.

"""Tests for Agent Skills provider (file-based and code-defined)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent_framework import SessionContext, Skill, SkillResource, SkillsProvider
from agent_framework._skills import (
    DEFAULT_RESOURCE_EXTENSIONS,
    DEFAULT_SCRIPT_EXTENSIONS,
    _create_instructions,
    _create_resource_element,
    _create_script_element,
    _discover_file_skills,
    _discover_resource_files,
    _discover_script_files,
    _discover_skill_directories,
    _extract_frontmatter,
    _has_symlink_in_path,
    _is_path_within_directory,
    _load_skills,
    _normalize_resource_path,
    _read_and_parse_skill_file,
    _read_file_skill_resource,
    _validate_skill_metadata,
)


async def _noop_script_runner(skill: Any, script: Any, args: Any = None) -> None:
    """No-op script runner for tests that need a SkillScriptRunner."""
    return


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


def _read_and_parse_skill_file_for_test(skill_dir: Path) -> Skill:
    """Parse a SKILL.md file from the given directory, raising if invalid."""
    result = _read_and_parse_skill_file(str(skill_dir))
    assert result is not None, f"Failed to parse skill at {skill_dir}"
    name, description, content = result
    return Skill(
        name=name,
        description=description,
        content=content,
        path=str(skill_dir),
    )


# ---------------------------------------------------------------------------
# Tests: module-level helper functions
# ---------------------------------------------------------------------------


class TestNormalizeResourcePath:
    """Tests for _normalize_resource_path."""

    def test_strips_dot_slash_prefix(self) -> None:
        assert _normalize_resource_path("./refs/doc.md") == "refs/doc.md"

    def test_replaces_backslashes(self) -> None:
        assert _normalize_resource_path("refs\\doc.md") == "refs/doc.md"

    def test_strips_dot_slash_and_replaces_backslashes(self) -> None:
        assert _normalize_resource_path(".\\refs\\doc.md") == "refs/doc.md"

    def test_no_change_for_clean_path(self) -> None:
        assert _normalize_resource_path("refs/doc.md") == "refs/doc.md"


class TestDiscoverResourceFiles:
    """Tests for _discover_resource_files (filesystem-based resource discovery)."""

    def test_discovers_md_files(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        refs = skill_dir / "refs"
        refs.mkdir()
        (refs / "FAQ.md").write_text("FAQ content", encoding="utf-8")
        resources = _discover_resource_files(str(skill_dir))
        assert "refs/FAQ.md" in resources

    def test_excludes_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content", encoding="utf-8")
        resources = _discover_resource_files(str(skill_dir))
        assert len(resources) == 0

    def test_discovers_multiple_extensions(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "data.json").write_text("{}", encoding="utf-8")
        (skill_dir / "config.yaml").write_text("key: val", encoding="utf-8")
        (skill_dir / "notes.txt").write_text("notes", encoding="utf-8")
        resources = _discover_resource_files(str(skill_dir))
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
        resources = _discover_resource_files(str(skill_dir))
        assert len(resources) == 0

    def test_custom_extensions(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "data.json").write_text("{}", encoding="utf-8")
        (skill_dir / "notes.txt").write_text("notes", encoding="utf-8")
        resources = _discover_resource_files(str(skill_dir), extensions=(".json",))
        assert resources == ["data.json"]

    def test_discovers_nested_files(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        sub = skill_dir / "refs" / "deep"
        sub.mkdir(parents=True)
        (sub / "doc.md").write_text("deep doc", encoding="utf-8")
        resources = _discover_resource_files(str(skill_dir))
        assert "refs/deep/doc.md" in resources

    def test_empty_directory(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        resources = _discover_resource_files(str(skill_dir))
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
        result = _extract_frontmatter(content, "test.md")
        assert result is not None
        name, description = result
        assert name == "test-skill"
        assert description == "A test skill."

    def test_quoted_values(self) -> None:
        content = "---\nname: \"test-skill\"\ndescription: 'A test skill.'\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[0] == "test-skill"
        assert result[1] == "A test skill."

    def test_utf8_bom(self) -> None:
        content = "\ufeff---\nname: test-skill\ndescription: A test skill.\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[0] == "test-skill"

    def test_missing_frontmatter(self) -> None:
        content = "# Just a markdown file\nNo frontmatter here."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_missing_name(self) -> None:
        content = "---\ndescription: A test skill.\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_missing_description(self) -> None:
        content = "---\nname: test-skill\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_invalid_name_uppercase(self) -> None:
        content = "---\nname: Test-Skill\ndescription: A test skill.\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_invalid_name_starts_with_hyphen(self) -> None:
        content = "---\nname: -test-skill\ndescription: A test skill.\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_invalid_name_ends_with_hyphen(self) -> None:
        content = "---\nname: test-skill-\ndescription: A test skill.\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_name_too_long(self) -> None:
        long_name = "a" * 65
        content = f"---\nname: {long_name}\ndescription: A test skill.\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_description_too_long(self) -> None:
        long_desc = "a" * 1025
        content = f"---\nname: test-skill\ndescription: {long_desc}\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_extra_metadata_ignored(self) -> None:
        content = "---\nname: test-skill\ndescription: A test skill.\nauthor: someone\nversion: 1.0\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[0] == "test-skill"


# ---------------------------------------------------------------------------
# Tests: skill discovery and loading
# ---------------------------------------------------------------------------


class TestDiscoverAndLoadSkills:
    """Tests for _discover_file_skills."""

    def test_discovers_valid_skill(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        skills = _discover_file_skills([str(tmp_path)])
        assert "my-skill" in skills
        assert skills["my-skill"].name == "my-skill"

    def test_discovers_nested_skills(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        _write_skill(skills_dir, "skill-a")
        _write_skill(skills_dir, "skill-b")
        skills = _discover_file_skills([str(skills_dir)])
        assert len(skills) == 2
        assert "skill-a" in skills
        assert "skill-b" in skills

    def test_skips_invalid_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("No frontmatter here.", encoding="utf-8")
        skills = _discover_file_skills([str(tmp_path)])
        assert len(skills) == 0

    def test_deduplicates_skill_names(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        _write_skill(dir1, "my-skill", body="First")
        _write_skill(dir2, "my-skill", body="Second")
        skills = _discover_file_skills([str(dir1), str(dir2)])
        assert len(skills) == 1
        assert "First" in skills["my-skill"].content

    def test_empty_directory(self, tmp_path: Path) -> None:
        skills = _discover_file_skills([str(tmp_path)])
        assert len(skills) == 0

    def test_nonexistent_directory(self) -> None:
        skills = _discover_file_skills(["/nonexistent/path"])
        assert len(skills) == 0

    def test_multiple_paths(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        _write_skill(dir1, "skill-a")
        _write_skill(dir2, "skill-b")
        skills = _discover_file_skills([str(dir1), str(dir2)])
        assert len(skills) == 2

    def test_depth_limit(self, tmp_path: Path) -> None:
        # Depth 0: tmp_path itself
        # Depth 1: tmp_path/level1
        # Depth 2: tmp_path/level1/level2 (should be found)
        # Depth 3: tmp_path/level1/level2/level3 (should NOT be found)
        deep = tmp_path / "level1" / "level2" / "level3"
        deep.mkdir(parents=True)
        (deep / "SKILL.md").write_text("---\nname: deep-skill\ndescription: Too deep.\n---\nBody.", encoding="utf-8")
        skills = _discover_file_skills([str(tmp_path)])
        assert "deep-skill" not in skills

    def test_skill_with_resources(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "my-skill",
            body="Instructions here.",
            resources={"refs/FAQ.md": "FAQ content"},
        )
        skills = _discover_file_skills([str(tmp_path)])
        assert "my-skill" in skills
        assert [r.name for r in skills["my-skill"].resources] == ["refs/FAQ.md"]

    def test_skill_discovers_all_resource_files(self, tmp_path: Path) -> None:
        """Resources are discovered by filesystem scan, not by markdown links."""
        _write_skill(
            tmp_path,
            "my-skill",
            body="No links here.",
            resources={"data.json": '{"key": "val"}', "refs/doc.md": "doc content"},
        )
        skills = _discover_file_skills([str(tmp_path)])
        assert "my-skill" in skills
        resource_names = sorted(r.name for r in skills["my-skill"].resources)
        assert "data.json" in resource_names
        assert "refs/doc.md" in resource_names


# ---------------------------------------------------------------------------
# Tests: read_skill_resource
# ---------------------------------------------------------------------------


class TestReadSkillResource:
    """Tests for _read_file_skill_resource."""

    def test_reads_valid_resource(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "my-skill",
            body="See [doc](refs/FAQ.md).",
            resources={"refs/FAQ.md": "FAQ content here"},
        )
        file_skill = _read_and_parse_skill_file_for_test(tmp_path / "my-skill")
        content = _read_file_skill_resource(file_skill, "refs/FAQ.md")
        assert content == "FAQ content here"

    def test_normalizes_dot_slash(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "my-skill",
            body="See [doc](refs/FAQ.md).",
            resources={"refs/FAQ.md": "FAQ content"},
        )
        file_skill = _read_and_parse_skill_file_for_test(tmp_path / "my-skill")
        content = _read_file_skill_resource(file_skill, "./refs/FAQ.md")
        assert content == "FAQ content"

    def test_unregistered_resource_raises(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        file_skill = _read_and_parse_skill_file_for_test(tmp_path / "my-skill")
        with pytest.raises(ValueError, match="not found in skill"):
            _read_file_skill_resource(file_skill, "nonexistent.md")

    def test_reads_resource_with_exact_casing(self, tmp_path: Path) -> None:
        """Direct file read uses the given resource name for path resolution."""
        _write_skill(
            tmp_path,
            "my-skill",
            body="See [doc](refs/FAQ.md).",
            resources={"refs/FAQ.md": "FAQ content"},
        )
        file_skill = _read_and_parse_skill_file_for_test(tmp_path / "my-skill")
        content = _read_file_skill_resource(file_skill, "refs/FAQ.md")
        assert content == "FAQ content"

    def test_path_traversal_raises(self, tmp_path: Path) -> None:
        skill = Skill(
            name="test",
            description="Test skill",
            content="Body",
            path=str(tmp_path / "skill"),
        )
        (tmp_path / "secret.md").write_text("secret", encoding="utf-8")
        with pytest.raises(ValueError, match="outside the skill directory"):
            _read_file_skill_resource(skill, "../secret.md")

    def test_similar_prefix_directory_does_not_match(self, tmp_path: Path) -> None:
        """A skill directory named 'skill-a-evil' must not access resources from 'skill-a'."""
        skill = Skill(
            name="test",
            description="Test skill",
            content="Body",
            path=str(tmp_path / "skill-a"),
        )
        evil_dir = tmp_path / "skill-a-evil"
        evil_dir.mkdir()
        (evil_dir / "secret.md").write_text("evil", encoding="utf-8")
        with pytest.raises(ValueError, match="outside the skill directory"):
            _read_file_skill_resource(skill, "../skill-a-evil/secret.md")


# ---------------------------------------------------------------------------
# Tests: _create_instructions
# ---------------------------------------------------------------------------


class TestBuildSkillsInstructionPrompt:
    """Tests for _create_instructions."""

    def test_returns_none_for_empty_skills(self) -> None:
        assert _create_instructions(None, {}) is None

    def test_default_prompt_contains_skills(self) -> None:
        skills = {
            "my-skill": Skill(name="my-skill", description="Does stuff.", content="Body"),
        }
        prompt = _create_instructions(None, skills)
        assert prompt is not None
        assert "<name>my-skill</name>" in prompt
        assert "<description>Does stuff.</description>" in prompt
        assert "load_skill" in prompt

    def test_skills_sorted_alphabetically(self) -> None:
        skills = {
            "zebra": Skill(name="zebra", description="Z skill.", content="Body"),
            "alpha": Skill(name="alpha", description="A skill.", content="Body"),
        }
        prompt = _create_instructions(None, skills)
        assert prompt is not None
        alpha_pos = prompt.index("alpha")
        zebra_pos = prompt.index("zebra")
        assert alpha_pos < zebra_pos

    def test_xml_escapes_metadata(self) -> None:
        skills = {
            "my-skill": Skill(name="my-skill", description='Uses <tags> & "quotes"', content="Body"),
        }
        prompt = _create_instructions(None, skills)
        assert prompt is not None
        assert "&lt;tags&gt;" in prompt
        assert "&amp;" in prompt

    def test_custom_prompt_template(self) -> None:
        skills = {
            "my-skill": Skill(name="my-skill", description="Does stuff.", content="Body"),
        }
        custom = "Custom header:\n{skills}\nCustom footer."
        prompt = _create_instructions(custom, skills)
        assert prompt is not None
        assert prompt.startswith("Custom header:")
        assert prompt.endswith("Custom footer.")

    def test_invalid_prompt_template_raises(self) -> None:
        skills = {
            "my-skill": Skill(name="my-skill", description="Does stuff.", content="Body"),
        }
        with pytest.raises(ValueError, match="valid format string"):
            _create_instructions("{invalid}", skills)

    def test_positional_placeholder_raises(self) -> None:
        skills = {
            "my-skill": Skill(name="my-skill", description="Does stuff.", content="Body"),
        }
        with pytest.raises(ValueError, match="valid format string"):
            _create_instructions("Header {0} footer", skills)


# ---------------------------------------------------------------------------
# Tests: SkillsProvider (file-based)
# ---------------------------------------------------------------------------


class TestSkillsProvider:
    """Tests for file-based usage of SkillsProvider."""

    def test_default_source_id(self, tmp_path: Path) -> None:
        provider = SkillsProvider(str(tmp_path))
        assert provider.source_id == "agent_skills"

    def test_custom_source_id(self, tmp_path: Path) -> None:
        provider = SkillsProvider(str(tmp_path), source_id="custom")
        assert provider.source_id == "custom"

    def test_accepts_single_path_string(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider(str(tmp_path))
        assert len(provider._skills) == 1

    def test_accepts_sequence_of_paths(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        _write_skill(dir1, "skill-a")
        _write_skill(dir2, "skill-b")
        provider = SkillsProvider([str(dir1), str(dir2)])
        assert len(provider._skills) == 2

    async def test_before_run_with_skills(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider(str(tmp_path))
        context = SessionContext(input_messages=[])

        await provider.before_run(
            agent=AsyncMock(),
            session=AsyncMock(),
            context=context,
            state={},
        )

        assert len(context.instructions) == 1
        assert "my-skill" in context.instructions[0]
        assert len(context.tools) == 2
        tool_names = {t.name for t in context.tools}
        assert tool_names == {"load_skill", "read_skill_resource"}

    async def test_before_run_without_skills(self, tmp_path: Path) -> None:
        provider = SkillsProvider(str(tmp_path))
        context = SessionContext(input_messages=[])

        await provider.before_run(
            agent=AsyncMock(),
            session=AsyncMock(),
            context=context,
            state={},
        )

        assert len(context.instructions) == 0
        assert len(context.tools) == 0

    def test_load_skill_returns_body(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill", body="Skill body content.")
        provider = SkillsProvider(str(tmp_path))
        result = provider._load_skill("my-skill")
        assert "Skill body content." in result

    def test_load_skill_preserves_file_skill_content(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "my-skill",
            body="See [doc](refs/FAQ.md).",
            resources={"refs/FAQ.md": "FAQ content"},
        )
        provider = SkillsProvider(str(tmp_path))
        result = provider._load_skill("my-skill")
        assert "See [doc](refs/FAQ.md)." in result

    def test_load_skill_unknown_returns_error(self, tmp_path: Path) -> None:
        provider = SkillsProvider(str(tmp_path))
        result = provider._load_skill("nonexistent")
        assert result.startswith("Error:")

    def test_load_skill_empty_name_returns_error(self, tmp_path: Path) -> None:
        provider = SkillsProvider(str(tmp_path))
        result = provider._load_skill("")
        assert result.startswith("Error:")

    async def test_read_skill_resource_returns_content(self, tmp_path: Path) -> None:
        _write_skill(
            tmp_path,
            "my-skill",
            body="See [doc](refs/FAQ.md).",
            resources={"refs/FAQ.md": "FAQ content"},
        )
        provider = SkillsProvider(str(tmp_path))
        result = await provider._read_skill_resource("my-skill", "refs/FAQ.md")
        assert result == "FAQ content"

    async def test_read_skill_resource_unknown_skill_returns_error(self, tmp_path: Path) -> None:
        provider = SkillsProvider(str(tmp_path))
        result = await provider._read_skill_resource("nonexistent", "file.md")
        assert result.startswith("Error:")

    async def test_read_skill_resource_empty_name_returns_error(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider(str(tmp_path))
        result = await provider._read_skill_resource("my-skill", "")
        assert result.startswith("Error:")

    async def test_read_skill_resource_unknown_resource_returns_error(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider(str(tmp_path))
        result = await provider._read_skill_resource("my-skill", "nonexistent.md")
        assert result.startswith("Error:")

    async def test_skills_sorted_in_prompt(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        _write_skill(skills_dir, "zebra", description="Z skill.")
        _write_skill(skills_dir, "alpha", description="A skill.")
        provider = SkillsProvider(str(skills_dir))
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
        provider = SkillsProvider(str(tmp_path))
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
        assert _has_symlink_in_path(full_path, directory_path) is True

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
        assert _has_symlink_in_path(full_path, directory_path) is True

    def test_returns_false_for_regular_files(self, tmp_path: Path) -> None:
        """Regular (non-symlinked) files should not be flagged."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        regular_file = skill_dir / "doc.txt"
        regular_file.write_text("content", encoding="utf-8")

        full_path = str(regular_file)
        directory_path = str(skill_dir) + os.sep
        assert _has_symlink_in_path(full_path, directory_path) is False

    def test_discover_skips_symlinked_resource(self, tmp_path: Path) -> None:
        """_discover_file_skills should skip a symlinked resource but keep the skill."""
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

        skills = _discover_file_skills([str(tmp_path)])
        assert "my-skill" in skills
        resource_names = [r.name for r in skills["my-skill"].resources]
        assert "refs/leak.md" not in resource_names
        assert "refs/safe.md" in resource_names

    def test_read_skill_resource_rejects_symlinked_resource(self, tmp_path: Path) -> None:
        """_read_skill_resource should raise ValueError for a symlinked resource."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()

        outside_file = tmp_path / "secret.md"
        outside_file.write_text("secret content", encoding="utf-8")

        refs_dir = skill_dir / "refs"
        refs_dir.mkdir()
        (refs_dir / "leak.md").symlink_to(outside_file)

        skill = Skill(
            name="test",
            description="Test skill",
            content="See [doc](refs/leak.md).",
            path=str(skill_dir),
        )
        with pytest.raises(ValueError, match="symlink"):
            _read_file_skill_resource(skill, "refs/leak.md")

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

        discovered = _discover_script_files(str(skill_dir))
        discovered_names = [p for p in discovered]
        assert "scripts/safe.py" in discovered_names
        assert "scripts/leak.py" not in discovered_names


# ---------------------------------------------------------------------------
# Tests: SkillResource
# ---------------------------------------------------------------------------


class TestSkillResource:
    """Tests for SkillResource dataclass."""

    def test_static_content(self) -> None:
        resource = SkillResource(name="ref", content="static content")
        assert resource.name == "ref"
        assert resource.content == "static content"
        assert resource.function is None

    def test_callable_function(self) -> None:
        def my_func() -> str:
            return "dynamic"

        resource = SkillResource(name="func", function=my_func)
        assert resource.name == "func"
        assert resource.content is None
        assert resource.function is my_func

    def test_with_description(self) -> None:
        resource = SkillResource(name="ref", description="A reference doc.", content="data")
        assert resource.description == "A reference doc."

    def test_requires_content_or_function(self) -> None:
        with pytest.raises(ValueError, match="must have either content or function"):
            SkillResource(name="empty")

    def test_content_and_function_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="must have either content or function, not both"):
            SkillResource(name="both", content="static", function=lambda: "dynamic")

    def test_accepts_kwargs_true_for_kwargs_function(self) -> None:
        def func_with_kwargs(**kwargs: Any) -> str:
            return "dynamic"

        resource = SkillResource(name="res", function=func_with_kwargs)
        assert resource._accepts_kwargs is True

    def test_accepts_kwargs_false_for_regular_function(self) -> None:
        def func_no_kwargs() -> str:
            return "dynamic"

        resource = SkillResource(name="res", function=func_no_kwargs)
        assert resource._accepts_kwargs is False


# ---------------------------------------------------------------------------
# Tests: Skill
# ---------------------------------------------------------------------------


class TestSkill:
    """Tests for Skill dataclass and .resource decorator."""

    def test_basic_construction(self) -> None:
        skill = Skill(name="my-skill", description="A test skill.", content="Instructions.")
        assert skill.name == "my-skill"
        assert skill.description == "A test skill."
        assert skill.content == "Instructions."
        assert skill.resources == []

    def test_construction_with_static_resources(self) -> None:
        skill = Skill(
            name="my-skill",
            description="A test skill.",
            content="Instructions.",
            resources=[
                SkillResource(name="ref", content="Reference content"),
            ],
        )
        assert len(skill.resources) == 1
        assert skill.resources[0].name == "ref"

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            Skill(name="", description="A skill.", content="Body")

    def test_invalid_name_skipped(self) -> None:
        invalid_skill = Skill(name="Invalid-Name", description="A skill.", content="Body")
        provider = SkillsProvider(skills=[invalid_skill])
        assert len(provider._skills) == 0

    def test_name_starts_with_hyphen_skipped(self) -> None:
        invalid_skill = Skill(name="-bad-name", description="A skill.", content="Body")
        provider = SkillsProvider(skills=[invalid_skill])
        assert len(provider._skills) == 0

    def test_name_too_long_skipped(self) -> None:
        invalid_skill = Skill(name="a" * 65, description="A skill.", content="Body")
        provider = SkillsProvider(skills=[invalid_skill])
        assert len(provider._skills) == 0

    def test_empty_description_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            Skill(name="my-skill", description="", content="Body")

    def test_description_too_long_skipped(self) -> None:
        invalid_skill = Skill(name="my-skill", description="a" * 1025, content="Body")
        provider = SkillsProvider(skills=[invalid_skill])
        assert len(provider._skills) == 0

    def test_resource_decorator_bare(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")

        @skill.resource
        def get_schema() -> Any:
            """Get the database schema."""
            return "CREATE TABLE users (id INT)"

        assert len(skill.resources) == 1
        assert skill.resources[0].name == "get_schema"
        assert skill.resources[0].description == "Get the database schema."
        assert skill.resources[0].function is get_schema

    def test_resource_decorator_with_args(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")

        @skill.resource(name="custom-name", description="Custom description")
        def my_resource() -> Any:
            return "data"

        assert len(skill.resources) == 1
        assert skill.resources[0].name == "custom-name"
        assert skill.resources[0].description == "Custom description"

    def test_resource_decorator_returns_function(self) -> None:
        """Decorator should return the original function unchanged."""
        skill = Skill(name="my-skill", description="A skill.", content="Body")

        @skill.resource
        def get_data() -> Any:
            return "data"

        assert callable(get_data)
        assert get_data() == "data"

    def test_multiple_resources(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")

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
        skill = Skill(name="my-skill", description="A skill.", content="Body")

        @skill.resource
        async def get_async_data() -> Any:
            return "async data"

        assert len(skill.resources) == 1
        assert skill.resources[0].function is get_async_data


# ---------------------------------------------------------------------------
# Tests: SkillsProvider with code-defined skills
# ---------------------------------------------------------------------------


class TestSkillsProviderCodeSkill:
    """Tests for SkillsProvider with code-defined skills."""

    def test_code_skill_only(self) -> None:
        skill = Skill(name="prog-skill", description="A code-defined skill.", content="Do the thing.")
        provider = SkillsProvider(skills=[skill])
        assert "prog-skill" in provider._skills

    def test_load_skill_returns_content(self) -> None:
        skill = Skill(name="prog-skill", description="A skill.", content="Code-defined instructions.")
        provider = SkillsProvider(skills=[skill])
        result = provider._load_skill("prog-skill")
        assert "<name>prog-skill</name>" in result
        assert "<description>A skill.</description>" in result
        assert "<instructions>\nCode-defined instructions.\n</instructions>" in result
        assert "<resources>" not in result

    def test_load_skill_appends_resource_listing(self) -> None:
        skill = Skill(
            name="prog-skill",
            description="A skill.",
            content="Do things.",
            resources=[
                SkillResource(name="ref-a", content="a", description="First resource"),
                SkillResource(name="ref-b", content="b"),
            ],
        )
        provider = SkillsProvider(skills=[skill])
        result = provider._load_skill("prog-skill")
        assert "<name>prog-skill</name>" in result
        assert "<description>A skill.</description>" in result
        assert "Do things." in result
        assert "<resources>" in result
        assert '<resource name="ref-a" description="First resource"/>' in result
        assert '<resource name="ref-b"/>' in result

    def test_load_skill_no_resources_no_listing(self) -> None:
        skill = Skill(name="prog-skill", description="A skill.", content="Body only.")
        provider = SkillsProvider(skills=[skill])
        result = provider._load_skill("prog-skill")
        assert "Body only." in result
        assert "<resources>" not in result

    async def test_read_static_resource(self) -> None:
        skill = Skill(
            name="prog-skill",
            description="A skill.",
            content="Body",
            resources=[SkillResource(name="ref", content="static content")],
        )
        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "ref")
        assert result == "static content"

    async def test_read_callable_resource_sync(self) -> None:
        skill = Skill(name="prog-skill", description="A skill.", content="Body")

        @skill.resource
        def get_schema() -> Any:
            return "CREATE TABLE users"

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "get_schema")
        assert result == "CREATE TABLE users"

    async def test_read_callable_resource_async(self) -> None:
        skill = Skill(name="prog-skill", description="A skill.", content="Body")

        @skill.resource
        async def get_data() -> Any:
            return "async data"

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "get_data")
        assert result == "async data"

    async def test_read_resource_case_insensitive(self) -> None:
        skill = Skill(
            name="prog-skill",
            description="A skill.",
            content="Body",
            resources=[SkillResource(name="MyRef", content="content")],
        )
        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "myref")
        assert result == "content"

    async def test_read_unknown_resource_returns_error(self) -> None:
        skill = Skill(name="prog-skill", description="A skill.", content="Body")
        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "nonexistent")
        assert result.startswith("Error:")

    async def test_read_callable_resource_sync_with_kwargs(self) -> None:
        skill = Skill(name="prog-skill", description="A skill.", content="Body")

        @skill.resource
        def get_user_config(**kwargs: Any) -> Any:
            user_id = kwargs.get("user_id", "unknown")
            return f"config for {user_id}"

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "get_user_config", user_id="user_123")
        assert result == "config for user_123"

    async def test_read_callable_resource_async_with_kwargs(self) -> None:
        skill = Skill(name="prog-skill", description="A skill.", content="Body")

        @skill.resource
        async def get_user_data(**kwargs: Any) -> Any:
            token = kwargs.get("auth_token", "none")
            return f"data with token={token}"

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "get_user_data", auth_token="abc")
        assert result == "data with token=abc"

    async def test_read_callable_resource_without_kwargs_ignores_extra_args(self) -> None:
        """Resource functions without **kwargs should still work when kwargs are passed."""
        skill = Skill(name="prog-skill", description="A skill.", content="Body")

        @skill.resource
        def static_resource() -> Any:
            return "static content"

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "static_resource", user_id="ignored")
        assert result == "static content"

    async def test_read_callable_resource_returns_dict(self) -> None:
        """Resource functions may return non-string types, passed through as-is."""
        skill = Skill(name="prog-skill", description="A skill.", content="Body")

        @skill.resource
        def get_config() -> Any:
            return {"max_retries": 3, "timeout": 30}

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "get_config")
        assert result == {"max_retries": 3, "timeout": 30}

    async def test_read_callable_resource_returns_list(self) -> None:
        """Resource functions may return lists, passed through as-is."""
        skill = Skill(name="prog-skill", description="A skill.", content="Body")

        @skill.resource
        def get_items() -> Any:
            return [1, 2, 3]

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "get_items")
        assert result == [1, 2, 3]

    async def test_read_callable_resource_returns_none(self) -> None:
        """Resource functions may return None."""
        skill = Skill(name="prog-skill", description="A skill.", content="Body")

        @skill.resource
        def get_nothing() -> Any:
            return None

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("prog-skill", "get_nothing")
        assert result is None

    async def test_before_run_injects_code_skills(self) -> None:
        skill = Skill(name="prog-skill", description="A code-defined skill.", content="Body")
        provider = SkillsProvider(skills=[skill])
        context = SessionContext(input_messages=[])

        await provider.before_run(agent=AsyncMock(), session=AsyncMock(), context=context, state={})

        assert len(context.instructions) == 1
        assert "prog-skill" in context.instructions[0]
        assert len(context.tools) == 2

    async def test_before_run_empty_provider(self) -> None:
        provider = SkillsProvider()
        context = SessionContext(input_messages=[])

        await provider.before_run(agent=AsyncMock(), session=AsyncMock(), context=context, state={})

        assert len(context.instructions) == 0
        assert len(context.tools) == 0

    def test_combined_file_and_code_skill(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "file-skill")
        prog_skill = Skill(name="prog-skill", description="Code-defined.", content="Body")
        provider = SkillsProvider(skill_paths=str(tmp_path), skills=[prog_skill])
        assert "file-skill" in provider._skills
        assert "prog-skill" in provider._skills

    def test_duplicate_name_file_wins(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill", body="File version")
        prog_skill = Skill(name="my-skill", description="Code-defined.", content="Prog version")
        provider = SkillsProvider(skill_paths=str(tmp_path), skills=[prog_skill])
        # File-based is loaded first, so it wins
        assert "File version" in provider._skills["my-skill"].content

    async def test_combined_prompt_includes_both(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "file-skill")
        prog_skill = Skill(name="prog-skill", description="A code-defined skill.", content="Body")
        provider = SkillsProvider(skill_paths=str(tmp_path), skills=[prog_skill])
        context = SessionContext(input_messages=[])

        await provider.before_run(agent=AsyncMock(), session=AsyncMock(), context=context, state={})

        prompt = context.instructions[0]
        assert "file-skill" in prompt
        assert "prog-skill" in prompt

    def test_custom_resource_extensions(self, tmp_path: Path) -> None:
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
        provider = SkillsProvider(str(tmp_path), resource_extensions=(".json",))
        skill = provider._skills["my-skill"]
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

    def test_resources_populated(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill", resources={"refs/doc.md": "content"})
        skills = _discover_file_skills([str(tmp_path)])
        assert "my-skill" in skills
        resource_names = [r.name for r in skills["my-skill"].resources]
        assert "refs/doc.md" in resource_names


# ---------------------------------------------------------------------------
# Tests: _load_skill formatting
# ---------------------------------------------------------------------------


class TestLoadSkillFormatting:
    """Tests for _load_skill output formatting differences between file-based and code-defined skills."""

    def test_file_skill_returns_raw_content(self, tmp_path: Path) -> None:
        """File-based skills return raw SKILL.md content without XML wrapping."""
        _write_skill(tmp_path, "my-skill", body="Do the thing.")
        provider = SkillsProvider(str(tmp_path))
        result = provider._load_skill("my-skill")
        assert "Do the thing." in result
        assert "<name>" not in result
        assert "<instructions>" not in result

    def test_code_skill_wraps_in_xml(self) -> None:
        """Code-defined skills are wrapped with name, description, and instructions tags."""
        skill = Skill(name="prog-skill", description="A skill.", content="Do stuff.")
        provider = SkillsProvider(skills=[skill])
        result = provider._load_skill("prog-skill")
        assert "<name>prog-skill</name>" in result
        assert "<description>A skill.</description>" in result
        assert "<instructions>\nDo stuff.\n</instructions>" in result

    def test_code_skill_single_resource_no_description(self) -> None:
        """Resource without description omits the description attribute."""
        skill = Skill(
            name="prog-skill",
            description="A skill.",
            content="Body.",
            resources=[SkillResource(name="data", content="val")],
        )
        provider = SkillsProvider(skills=[skill])
        result = provider._load_skill("prog-skill")
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
        resources = _discover_resource_files(str(skill_dir))
        names = [r.lower() for r in resources]
        assert "skill.md" not in names
        assert "other.md" in resources

    def test_skips_directories(self, tmp_path: Path) -> None:
        """Directories are not included as resources even if their name matches an extension."""
        skill_dir = tmp_path / "my-skill"
        subdir = skill_dir / "data.json"
        subdir.mkdir(parents=True)
        resources = _discover_resource_files(str(skill_dir))
        assert resources == []

    def test_extension_matching_is_case_insensitive(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "NOTES.TXT").write_text("caps", encoding="utf-8")
        resources = _discover_resource_files(str(skill_dir))
        assert len(resources) == 1


# ---------------------------------------------------------------------------
# Tests: _is_path_within_directory
# ---------------------------------------------------------------------------


class TestIsPathWithinDirectory:
    """Tests for _is_path_within_directory."""

    def test_path_inside_directory(self, tmp_path: Path) -> None:
        child = str(tmp_path / "sub" / "file.txt")
        assert _is_path_within_directory(child, str(tmp_path)) is True

    def test_path_outside_directory(self, tmp_path: Path) -> None:
        outside = str(tmp_path.parent / "other" / "file.txt")
        assert _is_path_within_directory(outside, str(tmp_path)) is False

    def test_path_is_directory_itself(self, tmp_path: Path) -> None:
        assert _is_path_within_directory(str(tmp_path), str(tmp_path)) is True

    def test_similar_prefix_not_matched(self, tmp_path: Path) -> None:
        """'skill-a-evil' is not inside 'skill-a'."""
        dir_a = str(tmp_path / "skill-a")
        evil = str(tmp_path / "skill-a-evil" / "file.txt")
        assert _is_path_within_directory(evil, dir_a) is False


# ---------------------------------------------------------------------------
# Tests: _has_symlink_in_path edge cases
# ---------------------------------------------------------------------------


class TestHasSymlinkInPathEdgeCases:
    """Edge-case tests for _has_symlink_in_path."""

    def test_raises_when_path_not_relative(self, tmp_path: Path) -> None:
        unrelated = str(tmp_path.parent / "other" / "file.txt")
        with pytest.raises(ValueError, match="does not start with directory"):
            _has_symlink_in_path(unrelated, str(tmp_path))

    def test_returns_false_for_empty_relative(self, tmp_path: Path) -> None:
        """When path equals directory, relative is empty so no symlinks."""
        assert _has_symlink_in_path(str(tmp_path), str(tmp_path)) is False


# ---------------------------------------------------------------------------
# Tests: _validate_skill_metadata
# ---------------------------------------------------------------------------


class TestValidateSkillMetadata:
    """Tests for _validate_skill_metadata."""

    def test_valid_metadata(self) -> None:
        assert _validate_skill_metadata("my-skill", "A description.", "source") is None

    def test_none_name(self) -> None:
        result = _validate_skill_metadata(None, "desc", "source")
        assert result is not None
        assert "missing a name" in result

    def test_empty_name(self) -> None:
        result = _validate_skill_metadata("", "desc", "source")
        assert result is not None
        assert "missing a name" in result

    def test_whitespace_only_name(self) -> None:
        result = _validate_skill_metadata("   ", "desc", "source")
        assert result is not None
        assert "missing a name" in result

    def test_name_at_max_length(self) -> None:
        name = "a" * 64
        assert _validate_skill_metadata(name, "desc", "source") is None

    def test_name_exceeds_max_length(self) -> None:
        name = "a" * 65
        result = _validate_skill_metadata(name, "desc", "source")
        assert result is not None
        assert "invalid name" in result

    def test_name_with_uppercase(self) -> None:
        result = _validate_skill_metadata("BadName", "desc", "source")
        assert result is not None
        assert "invalid name" in result

    def test_name_starts_with_hyphen(self) -> None:
        result = _validate_skill_metadata("-bad", "desc", "source")
        assert result is not None
        assert "invalid name" in result

    def test_name_ends_with_hyphen(self) -> None:
        result = _validate_skill_metadata("bad-", "desc", "source")
        assert result is not None
        assert "invalid name" in result

    def test_single_char_name(self) -> None:
        assert _validate_skill_metadata("a", "desc", "source") is None

    def test_none_description(self) -> None:
        result = _validate_skill_metadata("my-skill", None, "source")
        assert result is not None
        assert "missing a description" in result

    def test_empty_description(self) -> None:
        result = _validate_skill_metadata("my-skill", "", "source")
        assert result is not None
        assert "missing a description" in result

    def test_whitespace_only_description(self) -> None:
        result = _validate_skill_metadata("my-skill", "   ", "source")
        assert result is not None
        assert "missing a description" in result

    def test_description_at_max_length(self) -> None:
        desc = "a" * 1024
        assert _validate_skill_metadata("my-skill", desc, "source") is None

    def test_description_exceeds_max_length(self) -> None:
        desc = "a" * 1025
        result = _validate_skill_metadata("my-skill", desc, "source")
        assert result is not None
        assert "invalid description" in result


# ---------------------------------------------------------------------------
# Tests: _discover_skill_directories
# ---------------------------------------------------------------------------


class TestDiscoverSkillDirectories:
    """Tests for _discover_skill_directories."""

    def test_finds_skill_at_root(self, tmp_path: Path) -> None:
        (tmp_path / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        dirs = _discover_skill_directories([str(tmp_path)])
        assert len(dirs) == 1

    def test_finds_nested_skill(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        dirs = _discover_skill_directories([str(tmp_path)])
        assert len(dirs) == 1
        assert str(sub.absolute()) in dirs[0]

    def test_skips_empty_path_string(self) -> None:
        dirs = _discover_skill_directories(["", "   "])
        assert dirs == []

    def test_skips_nonexistent_path(self) -> None:
        dirs = _discover_skill_directories(["/nonexistent/does/not/exist"])
        assert dirs == []

    def test_depth_limit_excludes_deep_skill(self, tmp_path: Path) -> None:
        deep = tmp_path / "l1" / "l2" / "l3"
        deep.mkdir(parents=True)
        (deep / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        dirs = _discover_skill_directories([str(tmp_path)])
        assert len(dirs) == 0

    def test_depth_limit_includes_at_boundary(self, tmp_path: Path) -> None:
        at_boundary = tmp_path / "l1" / "l2"
        at_boundary.mkdir(parents=True)
        (at_boundary / "SKILL.md").write_text("---\nname: s\ndescription: d\n---\n", encoding="utf-8")
        dirs = _discover_skill_directories([str(tmp_path)])
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
        result = _read_and_parse_skill_file(str(skill_dir))
        assert result is not None
        name, desc, content = result
        assert name == "my-skill"
        assert desc == "A skill."
        assert "Body." in content

    def test_missing_skill_md_returns_none(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "no-skill"
        skill_dir.mkdir()
        result = _read_and_parse_skill_file(str(skill_dir))
        assert result is None

    def test_invalid_frontmatter_returns_none(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("No frontmatter at all.", encoding="utf-8")
        result = _read_and_parse_skill_file(str(skill_dir))
        assert result is None


# ---------------------------------------------------------------------------
# Tests: _create_resource_element
# ---------------------------------------------------------------------------


class TestCreateResourceElement:
    """Tests for _create_resource_element."""

    def test_name_only(self) -> None:
        r = SkillResource(name="my-ref", content="data")
        elem = _create_resource_element(r)
        assert elem == '  <resource name="my-ref"/>'

    def test_with_description(self) -> None:
        r = SkillResource(name="my-ref", description="A reference.", content="data")
        elem = _create_resource_element(r)
        assert elem == '  <resource name="my-ref" description="A reference."/>'

    def test_xml_escapes_name(self) -> None:
        r = SkillResource(name='ref"special', content="data")
        elem = _create_resource_element(r)
        assert "&quot;" in elem

    def test_xml_escapes_description(self) -> None:
        r = SkillResource(name="ref", description='Uses <tags> & "quotes"', content="data")
        elem = _create_resource_element(r)
        assert "&lt;tags&gt;" in elem
        assert "&amp;" in elem
        assert "&quot;" in elem


# ---------------------------------------------------------------------------
# Tests: _read_file_skill_resource edge cases
# ---------------------------------------------------------------------------


class TestReadFileSkillResourceEdgeCases:
    """Edge-case tests for _read_file_skill_resource."""

    def test_skill_with_no_path_raises(self) -> None:
        skill = Skill(name="no-path", description="No path.", content="Body")
        with pytest.raises(ValueError, match="has no path set"):
            _read_file_skill_resource(skill, "some-file.md")

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        skill = Skill(name="test", description="Test.", content="Body", path=str(skill_dir))
        with pytest.raises(ValueError, match="not found in skill"):
            _read_file_skill_resource(skill, "missing.md")


# ---------------------------------------------------------------------------
# Tests: _normalize_resource_path edge cases
# ---------------------------------------------------------------------------


class TestNormalizeResourcePathEdgeCases:
    """Additional edge-case tests for _normalize_resource_path."""

    def test_bare_filename(self) -> None:
        assert _normalize_resource_path("file.md") == "file.md"

    def test_deeply_nested_path(self) -> None:
        assert _normalize_resource_path("a/b/c/d.md") == "a/b/c/d.md"

    def test_mixed_separators(self) -> None:
        assert _normalize_resource_path("a\\b/c\\d.md") == "a/b/c/d.md"

    def test_dot_prefix_only(self) -> None:
        assert _normalize_resource_path("./file.md") == "file.md"


# ---------------------------------------------------------------------------
# Tests: _discover_file_skills edge cases
# ---------------------------------------------------------------------------


class TestDiscoverFileSkillsEdgeCases:
    """Edge-case tests for _discover_file_skills."""

    def test_none_path_returns_empty(self) -> None:
        assert _discover_file_skills(None) == {}

    def test_accepts_path_object(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        skills = _discover_file_skills(tmp_path)
        assert "my-skill" in skills

    def test_accepts_single_string_path(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        skills = _discover_file_skills(str(tmp_path))
        assert "my-skill" in skills


# ---------------------------------------------------------------------------
# Tests: _extract_frontmatter edge cases
# ---------------------------------------------------------------------------


class TestExtractFrontmatterEdgeCases:
    """Additional edge-case tests for _extract_frontmatter."""

    def test_whitespace_only_name(self) -> None:
        content = "---\nname: '   '\ndescription: A skill.\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_whitespace_only_description(self) -> None:
        content = "---\nname: test-skill\ndescription: '   '\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is None

    def test_name_exactly_max_length(self) -> None:
        name = "a" * 64
        content = f"---\nname: {name}\ndescription: A skill.\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[0] == name

    def test_description_exactly_max_length(self) -> None:
        desc = "a" * 1024
        content = f"---\nname: test-skill\ndescription: {desc}\n---\nBody."
        result = _extract_frontmatter(content, "test.md")
        assert result is not None
        assert result[1] == desc


# ---------------------------------------------------------------------------
# Tests: _create_instructions edge cases
# ---------------------------------------------------------------------------


class TestCreateInstructionsEdgeCases:
    """Additional edge-case tests for _create_instructions."""

    def test_custom_template_with_empty_skills_returns_none(self) -> None:
        result = _create_instructions("Custom: {skills}", {})
        assert result is None

    def test_custom_template_with_literal_braces(self) -> None:
        skills = {
            "my-skill": Skill(name="my-skill", description="Skill.", content="Body"),
        }
        template = "Header {{literal}} {skills} footer."
        result = _create_instructions(template, skills)
        assert result is not None
        assert "{literal}" in result
        assert "my-skill" in result

    def test_multiple_skills_generates_sorted_xml(self) -> None:
        skills = {
            "charlie": Skill(name="charlie", description="C.", content="Body"),
            "alpha": Skill(name="alpha", description="A.", content="Body"),
            "bravo": Skill(name="bravo", description="B.", content="Body"),
        }
        result = _create_instructions(None, skills)
        assert result is not None
        alpha_pos = result.index("alpha")
        bravo_pos = result.index("bravo")
        charlie_pos = result.index("charlie")
        assert alpha_pos < bravo_pos < charlie_pos

    def test_custom_template_missing_runner_instructions_raises(self) -> None:
        """Custom template without {runner_instructions} raises when scripts are enabled."""
        skills = {
            "my-skill": Skill(name="my-skill", description="Skill.", content="Body"),
        }
        template = "Skills: {skills}"
        with pytest.raises(ValueError, match="runner_instructions"):
            _create_instructions(template, skills, include_script_runner_instructions=True)

    def test_custom_template_with_unknown_placeholder_raises(self) -> None:
        """Template with an unknown placeholder raises ValueError."""
        skills = {
            "my-skill": Skill(name="my-skill", description="Skill.", content="Body"),
        }
        template = "Skills: {skills} {unknown_key}"
        with pytest.raises(ValueError, match="valid format string"):
            _create_instructions(template, skills)


# ---------------------------------------------------------------------------
# Tests: SkillsProvider edge cases
# ---------------------------------------------------------------------------


class TestSkillsProviderEdgeCases:
    """Additional edge-case tests for SkillsProvider."""

    def test_accepts_path_object(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider(tmp_path)
        assert "my-skill" in provider._skills

    def test_load_skill_whitespace_name_returns_error(self, tmp_path: Path) -> None:
        _write_skill(tmp_path, "my-skill")
        provider = SkillsProvider(str(tmp_path))
        result = provider._load_skill("   ")
        assert result.startswith("Error:")
        assert "empty" in result

    async def test_read_skill_resource_whitespace_skill_name_returns_error(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")
        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("   ", "ref")
        assert result.startswith("Error:")
        assert "empty" in result

    async def test_read_skill_resource_whitespace_resource_name_returns_error(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")
        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("my-skill", "   ")
        assert result.startswith("Error:")
        assert "empty" in result

    async def test_read_callable_resource_exception_returns_error(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")

        @skill.resource
        def exploding_resource() -> Any:
            raise RuntimeError("boom")

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("my-skill", "exploding_resource")
        assert result.startswith("Error:")
        assert "Failed to read resource" in result

    async def test_read_async_callable_resource_exception_returns_error(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")

        @skill.resource
        async def async_exploding() -> Any:
            raise ValueError("async boom")

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("my-skill", "async_exploding")
        assert result.startswith("Error:")

    def test_load_code_skill_xml_escapes_metadata(self) -> None:
        skill = Skill(name="my-skill", description='Uses <tags> & "quotes"', content="Body")
        provider = SkillsProvider(skills=[skill])
        result = provider._load_skill("my-skill")
        assert "&lt;tags&gt;" in result
        assert "&amp;" in result

    def test_code_skill_deduplication(self) -> None:
        skill1 = Skill(name="my-skill", description="First.", content="Body 1")
        skill2 = Skill(name="my-skill", description="Second.", content="Body 2")
        provider = SkillsProvider(skills=[skill1, skill2])
        assert len(provider._skills) == 1
        assert "First." in provider._skills["my-skill"].description

    async def test_before_run_extends_tools_even_without_instructions(self) -> None:
        """If instructions are somehow None but skills exist, tools should still be added."""
        skill = Skill(name="my-skill", description="A skill.", content="Body")
        provider = SkillsProvider(skills=[skill])
        context = SessionContext(input_messages=[])

        await provider.before_run(agent=AsyncMock(), session=AsyncMock(), context=context, state={})

        assert len(context.tools) == 2
        tool_names = {t.name for t in context.tools}
        assert "load_skill" in tool_names
        assert "read_skill_resource" in tool_names


# ---------------------------------------------------------------------------
# Tests: SkillResource edge cases
# ---------------------------------------------------------------------------


class TestSkillResourceEdgeCases:
    """Additional edge-case tests for SkillResource."""

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            SkillResource(name="", content="data")

    def test_whitespace_only_name_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            SkillResource(name="   ", content="data")

    def test_description_defaults_to_none(self) -> None:
        r = SkillResource(name="ref", content="data")
        assert r.description is None


# ---------------------------------------------------------------------------
# Tests: Skill.resource decorator edge cases
# ---------------------------------------------------------------------------


class TestSkillResourceDecoratorEdgeCases:
    """Additional edge-case tests for the @skill.resource decorator."""

    def test_decorator_no_docstring_description_is_none(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")

        @skill.resource
        def no_docs() -> Any:
            return "data"

        assert skill.resources[0].description is None

    def test_decorator_with_name_only(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")

        @skill.resource(name="custom-name")
        def get_data() -> Any:
            """Some docs."""
            return "data"

        assert skill.resources[0].name == "custom-name"
        # description falls back to docstring
        assert skill.resources[0].description == "Some docs."

    def test_decorator_with_description_only(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")

        @skill.resource(description="Custom desc")
        def get_data() -> Any:
            return "data"

        assert skill.resources[0].name == "get_data"
        assert skill.resources[0].description == "Custom desc"

    def test_decorator_preserves_original_function_identity(self) -> None:
        skill = Skill(name="my-skill", description="A skill.", content="Body")

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
        from agent_framework import SkillScript

        with pytest.raises(ValueError, match="Script name cannot be empty"):
            SkillScript(name="")

    def test_whitespace_name_raises(self) -> None:
        from agent_framework import SkillScript

        with pytest.raises(ValueError, match="Script name cannot be empty"):
            SkillScript(name="   ")

    def test_path_default_none(self) -> None:
        from agent_framework import SkillScript

        script = SkillScript(name="test", function=lambda: None)
        assert script.path is None

    def test_path_set_explicitly(self) -> None:
        from agent_framework import SkillScript

        script = SkillScript(name="gen.py", path="/skills/my-skill/scripts/gen.py")
        assert script.path == "/skills/my-skill/scripts/gen.py"

    def test_create_with_function(self) -> None:
        from agent_framework import SkillScript

        script = SkillScript(name="analyze", description="Run analysis", function=lambda: "result")
        assert script.name == "analyze"
        assert script.description == "Run analysis"
        assert script.function is not None

    def test_accepts_kwargs_true_for_kwargs_function(self) -> None:
        from agent_framework import SkillScript

        def func_with_kwargs(**kwargs: Any) -> str:
            return "result"

        script = SkillScript(name="s1", function=func_with_kwargs)
        assert script._accepts_kwargs is True

    def test_accepts_kwargs_false_for_regular_function(self) -> None:
        from agent_framework import SkillScript

        def func_no_kwargs(x: int = 0) -> str:
            return "result"

        script = SkillScript(name="s1", function=func_no_kwargs)
        assert script._accepts_kwargs is False


# ---------------------------------------------------------------------------
# @skill.script decorator tests
# ---------------------------------------------------------------------------


class TestSkillScriptDecorator:
    """Tests for the @skill.script decorator."""

    def test_bare_decorator(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")

        @skill.script
        def analyze(query: str) -> str:
            """Run analysis."""
            return "result"

        assert len(skill.scripts) == 1
        assert skill.scripts[0].name == "analyze"
        assert skill.scripts[0].description == "Run analysis."
        assert skill.scripts[0].function is analyze

    def test_parameterized_decorator(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")

        @skill.script(name="custom-name", description="Custom desc")
        def my_func() -> str:
            return "data"

        assert len(skill.scripts) == 1
        assert skill.scripts[0].name == "custom-name"
        assert skill.scripts[0].description == "Custom desc"
        assert skill.scripts[0].function is my_func

    def test_multiple_scripts(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")

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
        skill = Skill(name="my-skill", description="test", content="body")

        @skill.script
        async def fetch_data() -> str:
            """Fetch remote data."""
            return "data"

        assert len(skill.scripts) == 1
        assert skill.scripts[0].name == "fetch_data"
        assert skill.scripts[0].function is fetch_data

    def test_decorator_returns_original_function(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")

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
        skill = Skill(name="my-skill", description="test", content="body")
        assert skill.scripts == []

    def test_scripts_at_construction(self) -> None:
        from agent_framework import SkillScript

        scripts = [SkillScript(name="s1", function=lambda: None)]
        skill = Skill(name="my-skill", description="test", content="body", scripts=scripts)
        assert len(skill.scripts) == 1
        assert skill.scripts[0].name == "s1"


# ---------------------------------------------------------------------------
# Runner tests
# ---------------------------------------------------------------------------


class TestSkillScriptRunnerProtocol:
    """Tests for the SkillScriptRunner protocol."""

    async def test_async_callable_satisfies_protocol(self) -> None:
        from agent_framework import SkillScript, SkillScriptRunner

        results: list[tuple] = []

        async def my_runner(skill, script, args=None):
            results.append((skill.name, script.name, args))
            return "executed"

        assert isinstance(my_runner, SkillScriptRunner)

        skill = Skill(name="test-skill", description="test", content="body")
        script = SkillScript(name="my-script", path="scripts/run.py")
        skill.scripts.append(script)

        result = await my_runner(skill, script, args={"key": "val"})

        assert result == "executed"
        assert len(results) == 1
        assert results[0] == ("test-skill", "my-script", {"key": "val"})

    async def test_callable_class_satisfies_protocol(self) -> None:
        from agent_framework import SkillScript, SkillScriptRunner

        class _CustomRunner:
            async def __call__(self, skill, script, args=None):
                return "custom result"

        runner = _CustomRunner()
        assert isinstance(runner, SkillScriptRunner)

        skill = Skill(name="test-skill", description="test", content="body")
        script = SkillScript(name="my-script", function=lambda: None)
        skill.scripts.append(script)

        result = await runner(skill, script, args={"key": "val"})
        assert result == "custom result"

    async def test_runner_returns_none(self) -> None:
        from agent_framework import SkillScript

        async def noop_runner(skill, script, args=None):
            return None

        skill = Skill(name="test-skill", description="test", content="body")
        script = SkillScript(name="s1", function=lambda: None)

        result = await noop_runner(skill, script)
        assert result is None

    async def test_runner_returns_object(self) -> None:
        from agent_framework import SkillScript

        async def dict_runner(skill, script, args=None):
            return {"exit_code": 0, "output": "ok"}

        skill = Skill(name="test-skill", description="test", content="body")
        script = SkillScript(name="s1", path="scripts/run.py")

        result = await dict_runner(skill, script)
        assert result == {"exit_code": 0, "output": "ok"}

    def test_sync_callable_satisfies_protocol(self) -> None:
        from agent_framework import SkillScript, SkillScriptRunner

        results: list[tuple] = []

        def my_runner(skill, script, args=None):
            results.append((skill.name, script.name, args))
            return "executed"

        assert isinstance(my_runner, SkillScriptRunner)

        skill = Skill(name="test-skill", description="test", content="body")
        script = SkillScript(name="my-script", path="scripts/run.py")
        skill.scripts.append(script)

        result = my_runner(skill, script, args={"key": "val"})

        assert result == "executed"
        assert len(results) == 1
        assert results[0] == ("test-skill", "my-script", {"key": "val"})

    def test_sync_callable_class_satisfies_protocol(self) -> None:
        from agent_framework import SkillScript, SkillScriptRunner

        class _SyncRunner:
            def __call__(self, skill, script, args=None):
                return "sync result"

        runner = _SyncRunner()
        assert isinstance(runner, SkillScriptRunner)

        skill = Skill(name="test-skill", description="test", content="body")
        script = SkillScript(name="my-script", function=lambda: None)
        skill.scripts.append(script)

        result = runner(skill, script, args={"key": "val"})
        assert result == "sync result"

    def test_sync_runner_returns_none(self) -> None:
        from agent_framework import SkillScript

        def noop_runner(skill, script, args=None):
            return None

        skill = Skill(name="test-skill", description="test", content="body")
        script = SkillScript(name="s1", function=lambda: None)

        result = noop_runner(skill, script)
        assert result is None

    def test_sync_runner_returns_object(self) -> None:
        from agent_framework import SkillScript

        def dict_runner(skill, script, args=None):
            return {"exit_code": 0, "output": "ok"}

        skill = Skill(name="test-skill", description="test", content="body")
        script = SkillScript(name="s1", path="scripts/run.py")

        result = dict_runner(skill, script)
        assert result == {"exit_code": 0, "output": "ok"}


# ---------------------------------------------------------------------------
# SkillsProvider static factory tests
# ---------------------------------------------------------------------------


class TestSkillsProviderFactories:
    """Tests for the SkillsProvider constructor auto-wiring behavior."""

    def test_code_skills_with_scripts_creates_provider(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill])
        assert len(provider._skills) == 1
        # Default runner auto-wired: base tools + run_skill_script
        assert any(hasattr(t, "name") and t.name == "run_skill_script" for t in provider._tools)

    def test_code_skills_no_scripts(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")
        provider = SkillsProvider(skills=[skill])
        # No scripts with functions, no runner — only base tools
        assert len(provider._tools) == 2
        assert not any(hasattr(t, "name") and t.name == "run_skill_script" for t in provider._tools)

    async def test_code_script_runs_directly(self) -> None:
        from agent_framework import SkillScript

        def my_function(key: str = "") -> str:
            return f"executed: {key}"

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=my_function))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="s1", args={"key": "hello"})

        assert result == "executed: hello"

    def test_no_scripts_no_tool(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")
        # No scripts at all — no run_skill_script tool
        provider = SkillsProvider(skills=[skill])
        assert not any(hasattr(t, "name") and t.name == "run_skill_script" for t in provider._tools)

    def test_file_skills_with_custom_runner(self, tmp_path: Path) -> None:
        from agent_framework import SkillScriptRunner

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

        provider = SkillsProvider(
            skill_paths=str(tmp_path),
            script_runner=_CustomRunner(),
        )
        assert any(hasattr(t, "name") and t.name == "run_skill_script" for t in provider._tools)

    def test_file_skills_with_sync_runner(self, tmp_path: Path) -> None:
        from agent_framework import SkillScriptRunner

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

        provider = SkillsProvider(
            skill_paths=str(tmp_path),
            script_runner=sync_runner,
        )
        assert any(hasattr(t, "name") and t.name == "run_skill_script" for t in provider._tools)

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

        provider = SkillsProvider(
            skill_paths=str(tmp_path),
            script_runner=sync_runner,
        )
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="run.py", args={"key": "val"})
        assert result == "sync: run.py args={'key': 'val'}"

    def test_file_skills_with_callback_runner(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

        provider = SkillsProvider(
            skill_paths=str(tmp_path),
            script_runner=_noop_script_runner,
        )
        assert any(hasattr(t, "name") and t.name == "run_skill_script" for t in provider._tools)

    def test_combined_skills(self, tmp_path: Path) -> None:
        from agent_framework import SkillScript

        skill_dir = tmp_path / "file-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: file-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )

        code_skill = Skill(name="code-skill", description="test", content="body")
        code_skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(
            skill_paths=str(tmp_path),
            skills=[code_skill],
            script_runner=_noop_script_runner,
        )
        assert "file-skill" in provider._skills
        assert "code-skill" in provider._skills

    def test_file_scripts_without_runner_raises(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "run.py").write_text("print('hi')", encoding="utf-8")

        with pytest.raises(ValueError, match="script_runner"):
            SkillsProvider(skill_paths=str(tmp_path))

    async def test_file_script_error_without_runner(self) -> None:
        from agent_framework import SkillScript

        # A skill with both a code script and a file-based script
        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="code-s", function=lambda: "ok"))
        skill.scripts.append(SkillScript(name="file-s", path="scripts/s1.py"))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")

        # Code script works
        result = await run_tool.func(skill_name="my-skill", script_name="code-s")
        assert result == "ok"

        # File script without runner returns error
        result = await run_tool.func(skill_name="my-skill", script_name="file-s")
        assert "Error" in result
        assert "script_runner" in result

    async def test_async_code_script_runs_directly(self) -> None:
        from agent_framework import SkillScript

        async def async_func(x: int = 0) -> str:
            return f"async: {x}"

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=async_func))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="s1", args={"x": 42})
        assert result == "async: 42"

    async def test_code_script_returns_object(self) -> None:
        """Code-defined scripts can return non-string objects."""
        from agent_framework import SkillScript

        def returns_dict() -> dict:
            return {"status": "ok", "value": 42}

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=returns_dict))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="s1")
        assert result == {"status": "ok", "value": 42}

    async def test_code_script_returns_none(self) -> None:
        """Code-defined scripts returning None pass through as None."""
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="s1")
        assert result is None

    async def test_script_with_path_and_function_raises_error(self) -> None:
        """A script cannot have both a path and a function."""
        from agent_framework import SkillScript

        with pytest.raises(ValueError, match="must have either function or path, not both"):
            SkillScript(name="s1", function=lambda: "direct", path="scripts/s1.py")

    async def test_script_with_path_errors_without_runner(self) -> None:
        """A file-based script without a runner should return an error."""
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="code-s", function=lambda: "ok"))
        skill.scripts.append(SkillScript(name="path-s", path="scripts/s1.py"))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")

        # Code-only script still works
        result = await run_tool.func(skill_name="my-skill", script_name="code-s")
        assert result == "ok"

        # Path+function script without runner returns error
        result = await run_tool.func(skill_name="my-skill", script_name="path-s")
        assert "Error" in result
        assert "script_runner" in result

    async def test_run_skill_script_error_on_missing_skill(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="nonexistent", script_name="s1")
        assert "Error" in result
        assert "nonexistent" in result

    async def test_run_skill_script_sync_with_kwargs(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")

        @skill.script
        def greet(name: str, **kwargs: Any) -> str:
            user_id = kwargs.get("user_id", "unknown")
            return f"Hello {name} (user={user_id})"

        provider = SkillsProvider(skills=[skill])
        result = await provider._run_skill_script("my-skill", "greet", args={"name": "Alice"}, user_id="u42")
        assert result == "Hello Alice (user=u42)"

    async def test_run_skill_script_async_with_kwargs(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")

        @skill.script
        async def fetch(url: str, **kwargs: Any) -> str:
            token = kwargs.get("auth_token", "none")
            return f"fetched {url} with token={token}"

        provider = SkillsProvider(skills=[skill])
        result = await provider._run_skill_script("my-skill", "fetch", args={"url": "http://x"}, auth_token="abc")
        assert result == "fetched http://x with token=abc"

    async def test_run_skill_script_without_kwargs_ignores_extra_args(self) -> None:
        """Script functions without **kwargs should still work when runtime kwargs are passed."""
        skill = Skill(name="my-skill", description="test", content="body")

        @skill.script
        def simple(query: str) -> str:
            return f"result: {query}"

        provider = SkillsProvider(skills=[skill])
        result = await provider._run_skill_script("my-skill", "simple", args={"query": "test"}, user_id="ignored")
        assert result == "result: test"

    async def test_run_skill_script_conflicting_args_and_kwargs_raises(self) -> None:
        """Conflicting keys in args and kwargs should raise TypeError."""
        skill = Skill(name="my-skill", description="test", content="body")

        @skill.script
        def process(**kwargs: Any) -> str:
            return f"mode={kwargs.get('mode', 'default')}"

        provider = SkillsProvider(skills=[skill])
        result = await provider._run_skill_script(
            "my-skill", "process", args={"mode": "llm-value"}, mode="runtime-value"
        )
        assert "Error" in result

    async def test_run_skill_script_error_on_missing_script(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="nonexistent")
        assert "Error" in result
        assert "nonexistent" in result

    async def test_run_skill_script_error_on_empty_names(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")

        result = await run_tool.func(skill_name="", script_name="s1")
        assert "Error" in result

        result = await run_tool.func(skill_name="my-skill", script_name="")
        assert "Error" in result

    def test_instructions_include_script_runner_hints(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill])
        assert "run_skill_script" in provider._instructions
        assert "not as top-level tool parameters" in provider._instructions

    def test_no_scripts_no_runner_no_script_instructions(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")
        provider = SkillsProvider(skills=[skill])
        # No scripts and no runner — instructions should not mention run_skill_script
        assert "run_skill_script" not in (provider._instructions or "")

    def test_tool_schema_args_description_mentions_key_format(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        args_desc = run_tool.parameters()["properties"]["args"]["description"]
        assert "without leading dashes" in args_desc
        assert "script implementation or configured runner" in args_desc

    def test_require_script_approval_sets_approval_mode(self) -> None:
        """When require_script_approval=True, the run_skill_script tool has approval_mode='always_require'."""
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill], require_script_approval=True)
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        assert run_tool.approval_mode == "always_require"

    def test_require_script_approval_false_by_default(self) -> None:
        """By default, the run_skill_script tool has approval_mode='never_require'."""
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        assert run_tool.approval_mode == "never_require"

    def test_require_script_approval_does_not_affect_other_tools(self) -> None:
        """The load_skill and read_skill_resource tools should never require approval."""
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        provider = SkillsProvider(skills=[skill], require_script_approval=True)
        other_tools = [t for t in provider._tools if hasattr(t, "name") and t.name != "run_skill_script"]
        assert len(other_tools) == 2
        for t in other_tools:
            assert t.approval_mode == "never_require"

    async def test_code_script_exception_returns_error(self) -> None:
        """A code script function that raises should return an error string."""
        from agent_framework import SkillScript

        def failing_script() -> str:
            raise RuntimeError("Something went wrong")

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="boom", function=failing_script))

        provider = SkillsProvider(skills=[skill])
        run_tool = next(t for t in provider._tools if hasattr(t, "name") and t.name == "run_skill_script")
        result = await run_tool.func(skill_name="my-skill", script_name="boom")
        assert "Error" in result
        assert "boom" in result
        assert "Something went wrong" not in result

    def test_custom_template_without_runner_placeholder_raises(self) -> None:
        """Provider with code scripts and custom template missing {runner_instructions} raises."""
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        with pytest.raises(ValueError, match="runner_instructions"):
            SkillsProvider(
                skills=[skill],
                instruction_template="Skills: {skills}",
            )


# ---------------------------------------------------------------------------
# File script discovery tests
# ---------------------------------------------------------------------------


class TestFileScriptDiscovery:
    """Tests for automatic .py script discovery in skill directories."""

    def test_discovers_py_files(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "analyze.py").write_text("print('hi')", encoding="utf-8")

        skills = _discover_file_skills(str(tmp_path))
        assert "my-skill" in skills
        assert len(skills["my-skill"].scripts) == 1
        assert skills["my-skill"].scripts[0].name == "analyze.py"

    def test_discovered_script_has_relative_path(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (scripts_dir / "generate.py").write_text("print('gen')", encoding="utf-8")

        skills = _discover_file_skills(str(tmp_path))
        script = skills["my-skill"].scripts[0]
        assert script.path is not None
        assert not os.path.isabs(script.path)
        assert script.path == "scripts/generate.py"

    def test_discovers_nested_scripts(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (scripts_dir / "generate.py").write_text("print('gen')", encoding="utf-8")

        skills = _discover_file_skills(str(tmp_path))
        assert len(skills["my-skill"].scripts) == 1
        assert skills["my-skill"].scripts[0].name == "scripts/generate.py"

    def test_no_scripts_when_no_py_files(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "readme.md").write_text("# Docs", encoding="utf-8")

        skills = _discover_file_skills(str(tmp_path))
        assert len(skills["my-skill"].scripts) == 0


class TestCustomScriptExtensions:
    """Tests for the script_extensions parameter (parity with resource_extensions)."""

    def test_custom_script_extensions_via_discover_file_skills(self, tmp_path: Path) -> None:
        """_discover_file_skills forwards script_extensions to _discover_script_files."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: test\n---\nBody",
            encoding="utf-8",
        )
        (skill_dir / "analyze.py").write_text("print('hi')", encoding="utf-8")
        (skill_dir / "run.sh").write_text("#!/bin/bash", encoding="utf-8")

        # Default: only .py discovered
        skills_default = _discover_file_skills(str(tmp_path))
        script_names_default = [s.name for s in skills_default["my-skill"].scripts]
        assert "analyze.py" in script_names_default
        assert "run.sh" not in script_names_default

        # Custom: only .sh discovered
        skills_custom = _discover_file_skills(str(tmp_path), script_extensions=(".sh",))
        script_names_custom = [s.name for s in skills_custom["my-skill"].scripts]
        assert "run.sh" in script_names_custom
        assert "analyze.py" not in script_names_custom

    def test_custom_script_extensions_via_provider(self, tmp_path: Path) -> None:
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
        provider = SkillsProvider(
            str(tmp_path),
            script_extensions=(".sh",),
            script_runner=_noop_script_runner,
        )
        skill = provider._skills["my-skill"]
        script_names = [s.name for s in skill.scripts]
        assert "run.sh" in script_names
        assert "analyze.py" not in script_names

    def test_multiple_script_extensions(self, tmp_path: Path) -> None:
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

        provider = SkillsProvider(
            str(tmp_path),
            script_extensions=(".py", ".sh"),
            script_runner=_noop_script_runner,
        )
        skill = provider._skills["my-skill"]
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
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="s1", function=lambda: None))

        result = _create_instructions(None, {"my-skill": skill})
        assert result is not None
        assert "<scripts>" not in result

    def test_no_scripts_element_when_empty(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")

        result = _create_instructions(None, {"my-skill": skill})
        assert result is not None
        assert "<scripts>" not in result


# ---------------------------------------------------------------------------
# _load_skill with scripts tests
# ---------------------------------------------------------------------------


class TestLoadSkillWithScripts:
    """Tests for script metadata in load_skill output."""

    def test_code_skill_includes_scripts_element(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="analyze", description="Run analysis", function=lambda: None))

        provider = SkillsProvider(skills=[skill])
        result = provider._load_skill("my-skill")

        assert "<scripts>" in result
        assert 'name="analyze"' in result
        assert 'description="Run analysis"' in result

    def test_code_skill_no_scripts_element(self) -> None:
        skill = Skill(name="my-skill", description="test", content="body")
        provider = SkillsProvider(skills=[skill])
        result = provider._load_skill("my-skill")
        assert "<scripts>" not in result

    def test_code_skill_scripts_element_contains_parameters(self) -> None:
        """Scripts XML includes parameters schema when the function has typed parameters."""
        from agent_framework import SkillScript

        def analyze(query: str, limit: int = 10) -> str:
            return "result"

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="analyze", description="Run analysis", function=analyze))

        provider = SkillsProvider(skills=[skill])
        result = provider._load_skill("my-skill")

        assert "<scripts>" in result
        assert 'name="analyze"' in result
        assert "<parameters_schema>" in result
        assert '"query"' in result


class TestReadSkillResourceWithScripts:
    """Tests for _read_skill_resource falling back to scripts."""

    async def test_reads_script_with_static_content(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="generate.py", function=lambda: "print('hello')"))

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("my-skill", "generate.py")
        # Scripts are not returned via _read_skill_resource
        assert "not found" in result

    async def test_script_not_accessible_via_read_resource(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="run.py", function=lambda: "script output"))

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("my-skill", "run.py")
        # Scripts are separate from resources
        assert "not found" in result

    async def test_async_script_not_accessible_via_read_resource(self) -> None:
        from agent_framework import SkillScript

        async def async_script() -> str:
            return "async output"

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="run.py", function=async_script))

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("my-skill", "run.py")
        assert "not found" in result

    async def test_script_case_insensitive_not_in_resources(self) -> None:
        from agent_framework import SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="Generate.py", function=lambda: "code"))

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("my-skill", "generate.py")
        assert "not found" in result

    async def test_resource_takes_priority_over_script(self) -> None:
        from agent_framework import SkillResource, SkillScript

        skill = Skill(name="my-skill", description="test", content="body")
        skill.resources.append(SkillResource(name="data.py", content="resource content"))
        skill.scripts.append(SkillScript(name="data.py", function=lambda: "script content"))

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("my-skill", "data.py")
        assert result == "resource content"

    async def test_script_function_error_not_exposed_via_resources(self) -> None:
        from agent_framework import SkillScript

        def failing_script() -> str:
            raise RuntimeError("boom")

        skill = Skill(name="my-skill", description="test", content="body")
        skill.scripts.append(SkillScript(name="bad.py", function=failing_script))

        provider = SkillsProvider(skills=[skill])
        result = await provider._read_skill_resource("my-skill", "bad.py")
        assert "not found" in result


# ---------------------------------------------------------------------------
# Tests: _generate_function_schema
# ---------------------------------------------------------------------------


class TestGenerateFunctionSchema:
    """Tests for SkillScript.parameters_schema lazy generation."""

    def test_simple_function(self) -> None:
        from agent_framework import SkillScript

        def analyze(query: str, limit: int) -> str:
            return ""

        script = SkillScript(name="analyze", function=analyze)
        schema = script.parameters_schema
        assert schema is not None
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "limit" in schema["properties"]
        assert "query" in schema["required"]
        assert "limit" in schema["required"]

    def test_optional_parameter(self) -> None:
        from agent_framework import SkillScript

        def fetch(url: str, timeout: int = 30) -> str:
            return ""

        script = SkillScript(name="fetch", function=fetch)
        schema = script.parameters_schema
        assert schema is not None
        assert "url" in schema["properties"]
        assert "timeout" in schema["properties"]
        assert "url" in schema["required"]
        # timeout has a default, so it should NOT be in required
        assert "timeout" not in schema.get("required", [])

    def test_no_parameters_returns_none(self) -> None:
        from agent_framework import SkillScript

        def noop() -> None:
            pass

        script = SkillScript(name="noop", function=noop)
        assert script.parameters_schema is None

    def test_skips_self_and_cls(self) -> None:
        from agent_framework import SkillScript

        def method(self, query: str) -> str:  # noqa: ANN001
            return ""

        script = SkillScript(name="method", function=method)
        schema = script.parameters_schema
        assert schema is not None
        assert "self" not in schema["properties"]
        assert "query" in schema["properties"]

    def test_skips_var_keyword(self) -> None:
        from agent_framework import SkillScript

        def func(name: str, **kwargs: Any) -> str:
            return ""

        script = SkillScript(name="func", function=func)
        schema = script.parameters_schema
        assert schema is not None
        assert "kwargs" not in schema["properties"]
        assert "name" in schema["properties"]

    def test_async_function(self) -> None:
        from agent_framework import SkillScript

        async def fetch_data(url: str) -> str:
            return ""

        script = SkillScript(name="fetch_data", function=fetch_data)
        schema = script.parameters_schema
        assert schema is not None
        assert "url" in schema["properties"]

    def test_bool_and_float_types(self) -> None:
        from agent_framework import SkillScript

        def process(verbose: bool, threshold: float) -> None:
            pass

        script = SkillScript(name="process", function=process)
        schema = script.parameters_schema
        assert schema is not None
        assert "verbose" in schema["properties"]
        assert "threshold" in schema["properties"]

    def test_lazy_generation_is_cached(self) -> None:
        from agent_framework import SkillScript

        def analyze(query: str) -> str:
            return ""

        script = SkillScript(name="analyze", function=analyze)
        first = script.parameters_schema
        second = script.parameters_schema
        assert first is second


# ---------------------------------------------------------------------------
# Tests: _create_script_element
# ---------------------------------------------------------------------------


class TestCreateScriptElement:
    """Tests for _create_script_element."""

    def test_name_only(self) -> None:
        from agent_framework import SkillScript

        s = SkillScript(name="run.py", path="scripts/run.py")
        elem = _create_script_element(s)
        assert elem == '  <script name="run.py"/>'

    def test_with_description(self) -> None:
        from agent_framework import SkillScript

        s = SkillScript(name="run.py", description="Execute script.", path="scripts/run.py")
        elem = _create_script_element(s)
        assert elem == '  <script name="run.py" description="Execute script."/>'

    def test_xml_escapes_name(self) -> None:
        from agent_framework import SkillScript

        s = SkillScript(name='script"special', path="scripts/s.py")
        elem = _create_script_element(s)
        assert "&quot;" in elem

    def test_xml_escapes_description(self) -> None:
        from agent_framework import SkillScript

        s = SkillScript(name="run.py", description='Uses <tags> & "quotes"', path="scripts/run.py")
        elem = _create_script_element(s)
        assert "&lt;tags&gt;" in elem
        assert "&amp;" in elem
        assert "&quot;" in elem

    def test_includes_parameters_for_code_script(self) -> None:
        from agent_framework import SkillScript

        def analyze(query: str, limit: int = 10) -> str:
            return ""

        s = SkillScript(name="analyze", description="Run analysis", function=analyze)
        elem = _create_script_element(s)
        assert "<parameters_schema>" in elem
        assert "</parameters_schema>" in elem
        assert "query" in elem
        assert "&quot;" not in elem

    def test_no_parameters_for_file_script(self) -> None:
        from agent_framework import SkillScript

        s = SkillScript(name="run.py", path="scripts/run.py")
        elem = _create_script_element(s)
        assert "<parameters_schema>" not in elem


# ---------------------------------------------------------------------------
# Tests: SkillScript.parameters_schema
# ---------------------------------------------------------------------------


class TestSkillScriptParametersSchema:
    """Tests for parameters_schema auto-generation on SkillScript."""

    def test_auto_generated_from_function(self) -> None:
        from agent_framework import SkillScript

        def analyze(query: str) -> str:
            return ""

        script = SkillScript(name="analyze", function=analyze)
        assert script.parameters_schema is not None
        assert "query" in script.parameters_schema["properties"]

    def test_none_for_file_based_script(self) -> None:
        from agent_framework import SkillScript

        script = SkillScript(name="run.py", path="scripts/run.py")
        assert script.parameters_schema is None

    def test_no_params_function_returns_none(self) -> None:
        from agent_framework import SkillScript

        def noop() -> None:
            pass

        script = SkillScript(name="noop", function=noop)
        assert script.parameters_schema is None

    def test_kwargs_only_function_returns_none(self) -> None:
        from agent_framework import SkillScript

        def func(**kwargs: Any) -> str:
            return ""

        script = SkillScript(name="func", function=func)
        assert script.parameters_schema is None

    def test_no_params_caching_does_not_reinspect(self) -> None:
        """parameters_schema caches the None result and does not re-inspect."""
        from unittest.mock import patch

        from agent_framework import SkillScript

        def noop() -> None:
            pass

        script = SkillScript(name="noop", function=noop)
        first = script.parameters_schema
        assert first is None
        # Second access should not create a new FunctionTool
        with patch("agent_framework._skills.FunctionTool", side_effect=RuntimeError("should not be called")):
            second = script.parameters_schema
        assert second is None


# ---------------------------------------------------------------------------
# Tests: _load_skills merging behavior
# ---------------------------------------------------------------------------


class TestLoadSkillsMerging:
    """Tests for _load_skills merging file-based and code-defined skills."""

    def test_code_skill_with_invalid_name_is_skipped(self) -> None:
        """Code skills with invalid metadata (e.g. uppercase name) are skipped without raising."""
        invalid_skill = Skill(name="my-skill", description="valid", content="body")
        # Bypass Skill.__init__ validation by setting the name after construction
        invalid_skill.name = "INVALID_NAME"

        valid_skill = Skill(name="good-skill", description="valid", content="body")

        result = _load_skills(
            skill_paths=None,
            skills=[invalid_skill, valid_skill],
            resource_extensions=DEFAULT_RESOURCE_EXTENSIONS,
            script_extensions=DEFAULT_SCRIPT_EXTENSIONS,
        )
        assert "good-skill" in result
        assert "INVALID_NAME" not in result

    def test_file_skill_takes_precedence_over_code_skill(self, tmp_path: Path) -> None:
        """When file-based and code-defined skills share a name, file-based wins."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: File skill.\n---\nFile body.",
            encoding="utf-8",
        )

        code_skill = Skill(name="my-skill", description="Code skill.", content="Code body.")

        result = _load_skills(
            skill_paths=str(tmp_path),
            skills=[code_skill],
            resource_extensions=DEFAULT_RESOURCE_EXTENSIONS,
            script_extensions=DEFAULT_SCRIPT_EXTENSIONS,
        )
        assert "my-skill" in result
        assert result["my-skill"].path is not None  # file-based skill has path set
