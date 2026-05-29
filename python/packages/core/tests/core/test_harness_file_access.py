# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

from agent_framework import (
    Agent,
    AgentFileStore,
    AgentSession,
    ExperimentalFeature,
    FileAccessProvider,
    FileSearchMatch,
    FileSearchResult,
    FileSystemAgentFileStore,
    InMemoryAgentFileStore,
    Message,
    SupportsChatGetResponse,
)
from agent_framework._harness import _file_access as _file_access_module
from agent_framework._harness._file_access import (
    DEFAULT_FILE_ACCESS_INSTRUCTIONS,
    DEFAULT_FILE_ACCESS_SOURCE_ID,
    _matches_glob,
    _normalize_relative_path,
    _run_search_with_timeout,
)


def _tool_by_name(tools: list[object], name: str) -> object:
    """Return the tool with the requested name from a prepared tool list."""
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool
    raise AssertionError(f"Tool {name!r} was not found.")


def test_normalize_relative_path_collapses_and_validates() -> None:
    """The path normalizer should accept relative forward/backslash paths and reject unsafe ones."""
    assert _normalize_relative_path("foo/bar.txt") == "foo/bar.txt"
    assert _normalize_relative_path("foo\\bar.txt") == "foo/bar.txt"
    assert _normalize_relative_path("foo//bar.txt") == "foo/bar.txt"
    assert _normalize_relative_path("  foo/bar.txt  ") == "foo/bar.txt"
    assert _normalize_relative_path("", is_directory=True) == ""
    assert _normalize_relative_path("   ", is_directory=True) == ""
    assert _normalize_relative_path("sub/", is_directory=True) == "sub"
    assert _normalize_relative_path("sub\\", is_directory=True) == "sub"

    with pytest.raises(ValueError, match="must not be empty"):
        _normalize_relative_path("")
    with pytest.raises(ValueError, match="must not be empty"):
        _normalize_relative_path("   ")
    with pytest.raises(ValueError, match="must not end with a path separator"):
        _normalize_relative_path("foo/")
    with pytest.raises(ValueError, match="must not end with a path separator"):
        _normalize_relative_path("foo\\")
    with pytest.raises(ValueError, match="'..' segments"):
        _normalize_relative_path("foo/../bar.txt")
    with pytest.raises(ValueError, match="'..' segments"):
        _normalize_relative_path("./bar.txt")
    with pytest.raises(ValueError, match="must be relative"):
        _normalize_relative_path("C:/abs/path")
    with pytest.raises(ValueError, match="must be relative"):
        _normalize_relative_path("\\rooted")
    with pytest.raises(ValueError, match="must be relative"):
        _normalize_relative_path("/foo/bar.txt")


def test_matches_glob_is_case_insensitive_and_optional() -> None:
    """The glob matcher should be case-insensitive and treat missing patterns as match-all."""
    assert _matches_glob("notes.MD", "*.md")
    assert _matches_glob("research_one.txt", "research*")
    assert not _matches_glob("plan.txt", "*.md")
    assert _matches_glob("anything", None)
    assert _matches_glob("anything", "")
    assert _matches_glob("anything", "   ")


def test_file_search_match_round_trips() -> None:
    """File search match values should serialize and validate cleanly."""
    raw_match = {"line_number": 3, "line": "error: boom"}

    match = FileSearchMatch.from_dict(raw_match)
    assert match == FileSearchMatch(line_number=3, line="error: boom")
    assert match.to_dict() == raw_match
    assert "FileSearchMatch(" in repr(match)

    with pytest.raises(ValueError, match="positive integer"):
        FileSearchMatch(line_number=0, line="oops")
    with pytest.raises(ValueError, match="must be an integer"):
        FileSearchMatch.from_dict({"line_number": "1", "line": "oops"})
    with pytest.raises(ValueError, match="must be a string"):
        FileSearchMatch.from_dict({"line_number": 1, "line": 42})


def test_file_search_result_round_trips() -> None:
    """File search result values should serialize the matching-line list correctly."""
    raw_result = {
        "file_name": "notes.md",
        "snippet": "hello error world",
        "matching_lines": [{"line_number": 2, "line": "error one"}],
    }

    result = FileSearchResult.from_dict(raw_result)
    assert result.file_name == "notes.md"
    assert result.snippet == "hello error world"
    assert result.matching_lines == [FileSearchMatch(line_number=2, line="error one")]
    assert result.to_dict() == raw_result
    assert json.loads(result.to_json()) == raw_result

    with pytest.raises(ValueError, match="matching_lines must be a list"):
        FileSearchResult.from_dict({"file_name": "x", "snippet": "", "matching_lines": {}})

    with pytest.raises(ValueError, match="elements must be mappings"):
        FileSearchResult.from_dict({"file_name": "x", "snippet": "", "matching_lines": ["not-a-dict"]})


async def test_in_memory_store_round_trips_files() -> None:
    """The in-memory store should support write/read/exists/delete/list operations."""
    store = InMemoryAgentFileStore()

    await store.write_file("a.txt", "alpha")
    await store.write_file("sub/b.txt", "beta")

    assert await store.file_exists("a.txt")
    assert not await store.file_exists("missing.txt")
    assert await store.read_file("a.txt") == "alpha"
    assert await store.read_file("missing.txt") is None

    assert sorted(await store.list_files()) == ["a.txt"]  # subdirs are not direct children
    assert sorted(await store.list_files("sub")) == ["b.txt"]

    assert await store.delete_file("a.txt") is True
    assert await store.delete_file("a.txt") is False
    assert sorted(await store.list_files()) == []


async def test_in_memory_store_search_returns_matches_with_snippets() -> None:
    """The in-memory store should search file content case-insensitively and respect glob filters."""
    store = InMemoryAgentFileStore()
    await store.write_file("a.md", "line one\nThis line has ERROR inside\nline three\r")
    await store.write_file("b.md", "no match here")
    await store.write_file("notes.txt", "ERROR but wrong extension")

    results = await store.search_files("", "error", "*.md")
    assert [result.file_name for result in results] == ["a.md"]
    matching_lines = results[0].matching_lines
    assert matching_lines == [FileSearchMatch(line_number=2, line="This line has ERROR inside")]
    assert "ERROR" in results[0].snippet

    # No glob -> searches every file.
    results_all = await store.search_files("", "error")
    assert {result.file_name for result in results_all} == {"a.md", "notes.txt"}


async def test_in_memory_store_search_rejects_invalid_and_oversize_regex() -> None:
    """``search_files`` should surface clean errors for bad regex input."""
    store = InMemoryAgentFileStore()
    await store.write_file("a.md", "hello")

    with pytest.raises(re.error):
        await store.search_files("", "[unclosed")

    with pytest.raises(ValueError, match="too long"):
        await store.search_files("", "a" * 257)


async def test_in_memory_store_normalizes_paths() -> None:
    """Path normalization should reject traversal in the in-memory store too."""
    store = InMemoryAgentFileStore()
    for bad in ("../escape.txt", "/abs/path.txt", "."):
        with pytest.raises(ValueError):
            await store.write_file(bad, "boom")


async def test_filesystem_store_round_trips_files(tmp_path: Path) -> None:
    """The filesystem store should round-trip files on disk and create parents on write."""
    store = FileSystemAgentFileStore(tmp_path)

    await store.write_file("nested/a.txt", "alpha")
    assert (tmp_path / "nested" / "a.txt").read_text(encoding="utf-8") == "alpha"

    assert await store.read_file("nested/a.txt") == "alpha"
    assert await store.read_file("missing.txt") is None
    assert await store.file_exists("nested/a.txt")
    assert not await store.file_exists("missing.txt")
    assert sorted(await store.list_files("nested")) == ["a.txt"]
    assert sorted(await store.list_files()) == []  # root only contains the directory

    assert await store.delete_file("nested/a.txt") is True
    assert await store.delete_file("nested/a.txt") is False


async def test_filesystem_store_rejects_traversal_and_rooted_paths(tmp_path: Path) -> None:
    """The filesystem store should refuse paths that escape the configured root."""
    store = FileSystemAgentFileStore(tmp_path)

    for bad in ("../escape.txt", "/etc/passwd", "C:/Windows/System32/notepad.exe", ".", ".."):
        with pytest.raises(ValueError):
            await store.write_file(bad, "boom")


async def test_filesystem_store_rejects_symlinks_into_root(tmp_path: Path) -> None:
    """The filesystem store should refuse to read through a symlink target."""
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    link = root / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symbolic links are not supported in this environment: {exc!r}")

    store = FileSystemAgentFileStore(root)
    with pytest.raises(ValueError, match="symbolic link"):
        await store.read_file("link.txt")
    with pytest.raises(ValueError, match="symbolic link"):
        await store.write_file("link.txt", "stomp")

    # List operations should silently skip the symlink entry rather than raise.
    assert await store.list_files() == []


async def test_filesystem_store_rejects_in_root_symlinks(tmp_path: Path) -> None:
    """Symlinks whose target lives under the root must still be rejected.

    ``Path.resolve`` collapses the symlink, so a naive resolved-path check
    would silently follow it. The symlink probe must operate on the
    unresolved candidate for this case to fail closed.
    """
    root = tmp_path / "root"
    root.mkdir()
    real = root / "real.txt"
    real.write_text("payload", encoding="utf-8")
    link = root / "alias.txt"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symbolic links are not supported in this environment: {exc!r}")

    store = FileSystemAgentFileStore(root)
    with pytest.raises(ValueError, match="symbolic link"):
        await store.read_file("alias.txt")
    # The non-symlinked sibling must still be readable.
    assert await store.read_file("real.txt") == "payload"


async def test_filesystem_store_search_matches_lines_and_filters_globs(tmp_path: Path) -> None:
    """The filesystem store should search files on disk and apply glob filters by file name."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write_file("a.md", "hello\nERROR happens\nbye\r")
    await store.write_file("b.txt", "ERROR happens too")
    await store.write_file("c.md", "nothing here")

    results = await store.search_files("", "error", "*.md")
    assert [result.file_name for result in results] == ["a.md"]
    assert results[0].matching_lines == [FileSearchMatch(line_number=2, line="ERROR happens")]
    assert "ERROR" in results[0].snippet

    results_all = await store.search_files("", "error")
    assert {result.file_name for result in results_all} == {"a.md", "b.txt"}


async def test_filesystem_store_search_skips_non_utf8_files(tmp_path: Path) -> None:
    """The filesystem store should silently skip non-UTF-8 files instead of aborting the search."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write_file("notes.md", "ERROR happens here")
    (tmp_path / "blob.bin").write_bytes(b"\x80\x81\x82\x83")

    results = await store.search_files("", "error")
    assert [result.file_name for result in results] == ["notes.md"]


async def test_filesystem_store_create_directory(tmp_path: Path) -> None:
    """The filesystem store should create directories under the configured root."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.create_directory("nested/inner")
    assert (tmp_path / "nested" / "inner").is_dir()


async def test_filesystem_store_list_files_accepts_blank_directory(tmp_path: Path) -> None:
    """Whitespace-only directory inputs should resolve to the root, matching the in-memory store."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write_file("a.txt", "alpha")
    assert sorted(await store.list_files("")) == ["a.txt"]
    assert sorted(await store.list_files("   ")) == ["a.txt"]


def test_filesystem_store_requires_non_empty_root() -> None:
    """The filesystem store constructor should refuse blank root paths."""
    with pytest.raises(ValueError, match="must not be empty"):
        FileSystemAgentFileStore("")
    with pytest.raises(ValueError, match="must not be empty"):
        FileSystemAgentFileStore("   ")


async def test_file_access_provider_registers_tools_and_instructions(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """``FileAccessProvider.before_run`` should add the canonical instructions and five tools."""
    session = AgentSession(session_id="session-1")
    store = InMemoryAgentFileStore()
    provider = FileAccessProvider(store=store)
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )

    tools = options["tools"]
    assert isinstance(tools, list)
    expected_names = {
        "file_access_save_file",
        "file_access_read_file",
        "file_access_delete_file",
        "file_access_list_files",
        "file_access_search_files",
    }
    assert {getattr(tool, "name", None) for tool in tools} >= expected_names

    instructions = options.get("instructions")
    if isinstance(instructions, str):
        assert DEFAULT_FILE_ACCESS_INSTRUCTIONS in instructions
    else:
        assert any(DEFAULT_FILE_ACCESS_INSTRUCTIONS in chunk for chunk in (instructions or []))


async def test_file_access_provider_delete_approval_defaults_to_always_require(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """By default ``file_access_delete_file`` should require host approval."""
    session = AgentSession(session_id="session-1")
    provider = FileAccessProvider(store=InMemoryAgentFileStore())
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )

    tools = options["tools"]
    assert isinstance(tools, list)
    delete_file = _tool_by_name(tools, "file_access_delete_file")
    assert delete_file.approval_mode == "always_require"
    # The non-destructive tools should remain autonomous.
    for name in (
        "file_access_save_file",
        "file_access_read_file",
        "file_access_list_files",
        "file_access_search_files",
    ):
        assert _tool_by_name(tools, name).approval_mode == "never_require"


async def test_file_access_provider_delete_approval_opt_out(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """``require_delete_approval=False`` should drop delete to ``never_require``."""
    session = AgentSession(session_id="session-1")
    provider = FileAccessProvider(store=InMemoryAgentFileStore(), require_delete_approval=False)
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )

    delete_file = _tool_by_name(options["tools"], "file_access_delete_file")  # type: ignore[arg-type]
    assert delete_file.approval_mode == "never_require"


async def test_file_access_provider_tools_round_trip_files(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """The provider's tools should drive save/read/list/search/delete flows on an ``InMemoryAgentFileStore``."""
    session = AgentSession(session_id="session-1")
    store = InMemoryAgentFileStore()
    provider = FileAccessProvider(store=store)
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    save_file = _tool_by_name(tools, "file_access_save_file")
    read_file = _tool_by_name(tools, "file_access_read_file")
    delete_file = _tool_by_name(tools, "file_access_delete_file")
    list_files = _tool_by_name(tools, "file_access_list_files")
    search_files = _tool_by_name(tools, "file_access_search_files")

    saved = await save_file.invoke(arguments={"file_name": "plan.md", "content": "step 1\nERROR step 2"})
    assert "plan.md" in saved[0].text and "saved" in saved[0].text

    # Default overwrite=False should refuse the second save.
    refused = await save_file.invoke(arguments={"file_name": "plan.md", "content": "stomp"})
    assert "already exists" in refused[0].text

    # overwrite=True should succeed.
    overwritten = await save_file.invoke(
        arguments={"file_name": "plan.md", "content": "stomp\nERROR replaced", "overwrite": True}
    )
    assert "saved" in overwritten[0].text

    read_back = await read_file.invoke(arguments={"file_name": "plan.md"})
    assert read_back[0].text == "stomp\nERROR replaced"

    listed = await list_files.invoke()
    assert json.loads(listed[0].text) == ["plan.md"]

    # The list tool should accept an optional directory argument so agents can
    # enumerate nested folders (not only the root).
    await save_file.invoke(arguments={"file_name": "reports/2024.md", "content": "annual"})
    listed_nested = await list_files.invoke(arguments={"directory": "reports"})
    assert json.loads(listed_nested[0].text) == ["2024.md"]
    # Blank / whitespace directory should fall back to the root listing.
    listed_blank = await list_files.invoke(arguments={"directory": "   "})
    assert sorted(json.loads(listed_blank[0].text)) == ["plan.md"]

    missing = await read_file.invoke(arguments={"file_name": "missing.md"})
    assert "not found" in missing[0].text

    search_payload = await search_files.invoke(arguments={"regex_pattern": "error", "file_pattern": "*.md"})
    parsed = json.loads(search_payload[0].text)
    assert parsed[0]["file_name"] == "plan.md"
    assert parsed[0]["matching_lines"][0]["line"] == "ERROR replaced"

    # The search tool should likewise accept an optional directory argument so
    # agents can scope a search to a subfolder.
    await save_file.invoke(arguments={"file_name": "reports/issues.md", "content": "ERROR nested"})
    scoped = await search_files.invoke(
        arguments={"regex_pattern": "error", "file_pattern": "*.md", "directory": "reports"}
    )
    scoped_parsed = json.loads(scoped[0].text)
    assert [entry["file_name"] for entry in scoped_parsed] == ["issues.md"]

    deleted = await delete_file.invoke(arguments={"file_name": "plan.md"})
    assert "deleted" in deleted[0].text

    missing_delete = await delete_file.invoke(arguments={"file_name": "plan.md"})
    assert "not found" in missing_delete[0].text


async def test_file_access_provider_accepts_custom_instructions() -> None:
    """Custom instructions should override the default banner."""
    store = InMemoryAgentFileStore()
    provider = FileAccessProvider(store=store, instructions="custom-banner")
    assert provider.instructions == "custom-banner"
    assert provider.source_id == DEFAULT_FILE_ACCESS_SOURCE_ID


async def test_in_memory_store_write_file_raises_when_exists_and_no_overwrite() -> None:
    """The atomic exclusive-create path should raise ``FileExistsError`` under the lock."""
    store = InMemoryAgentFileStore()
    await store.write_file("plan.md", "v1")

    with pytest.raises(FileExistsError):
        await store.write_file("plan.md", "v2", overwrite=False)

    # The original content is preserved.
    assert await store.read_file("plan.md") == "v1"

    # Default ``overwrite=True`` still replaces.
    await store.write_file("plan.md", "v3")
    assert await store.read_file("plan.md") == "v3"


async def test_filesystem_store_write_file_raises_when_exists_and_no_overwrite(tmp_path: Path) -> None:
    """The filesystem store should use exclusive-create semantics when ``overwrite=False``."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write_file("plan.md", "v1")

    with pytest.raises(FileExistsError):
        await store.write_file("plan.md", "v2", overwrite=False)

    assert (tmp_path / "plan.md").read_text(encoding="utf-8") == "v1"

    await store.write_file("plan.md", "v3", overwrite=True)
    assert (tmp_path / "plan.md").read_text(encoding="utf-8") == "v3"


async def test_run_search_with_timeout_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A scan that exceeds the timeout should surface a clean ``ValueError``."""
    monkeypatch.setattr(_file_access_module, "_SEARCH_TIMEOUT_SECONDS", 0.01)

    def slow() -> list[FileSearchResult]:
        time.sleep(0.5)
        return []

    with pytest.raises(ValueError, match="did not complete"):
        await _run_search_with_timeout(slow)


async def test_filesystem_store_symlink_probe_fails_closed_on_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If ``Path.is_symlink`` raises during the probe, the operation must be refused."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write_file("ok.txt", "content")

    def boom(self: Path) -> bool:
        raise PermissionError("access denied")

    monkeypatch.setattr(Path, "is_symlink", boom)

    with pytest.raises(ValueError, match="symbolic link or reparse point"):
        await store.read_file("ok.txt")


def test_file_access_harness_classes_are_marked_experimental() -> None:
    """File-access harness public classes should expose HARNESS experimental metadata."""
    assert AgentFileStore.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert InMemoryAgentFileStore.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert FileSystemAgentFileStore.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert FileSearchMatch.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert FileSearchResult.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert FileAccessProvider.__feature_id__ == ExperimentalFeature.HARNESS.value
    assert ".. warning:: Experimental" in (FileAccessProvider.__doc__ or "")


async def test_in_memory_store_preserves_original_case_on_list_and_search() -> None:
    """``list_files`` / ``search_files`` should return original-case names, not lowercased keys.

    Matches :class:`FileSystemAgentFileStore` on case-preserving filesystems so
    tests written against the in-memory backend cannot encode a contract that
    will diverge in production.
    """
    store = InMemoryAgentFileStore()
    await store.write_file("Plan.MD", "ERROR happens here\n")
    await store.write_file("Reports/Q1.MD", "alpha")

    # list_files keeps the original case
    assert sorted(await store.list_files()) == ["Plan.MD"]
    assert sorted(await store.list_files("Reports")) == ["Q1.MD"]

    # case-insensitive directory lookup still works
    assert sorted(await store.list_files("reports")) == ["Q1.MD"]

    # search_files emits the original-case file name in FileSearchResult
    results = await store.search_files("", "error", "*.MD")
    assert [r.file_name for r in results] == ["Plan.MD"]

    # read_file remains case-insensitive
    assert await store.read_file("plan.md") == "ERROR happens here\n"


async def test_filesystem_store_read_file_raises_value_error_on_non_utf8(tmp_path: Path) -> None:
    """Binary / non-UTF-8 files should raise a clean ``ValueError`` rather than ``UnicodeDecodeError``.

    The tool-layer wrapper relies on this contract to convert the failure into
    a recoverable string response for the agent.
    """
    store = FileSystemAgentFileStore(tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x80\x81\x82\x83")

    with pytest.raises(ValueError, match="not UTF-8 text"):
        await store.read_file("blob.bin")


async def test_filesystem_store_search_logs_skipped_non_utf8_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``search_files`` skips non-UTF-8 files but logs per-file and a summary so operators have signal."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write_file("notes.md", "ERROR happens here")
    (tmp_path / "blob.bin").write_bytes(b"\x80\x81\x82\x83")

    with caplog.at_level("INFO", logger="agent_framework._harness._file_access"):
        results = await store.search_files("", "error")

    assert [r.file_name for r in results] == ["notes.md"]
    assert any("Skipping non-UTF-8 file during search" in rec.message for rec in caplog.records)
    assert any("skipped 1 non-UTF-8 file" in rec.message for rec in caplog.records)


async def test_file_access_tool_wrappers_surface_value_error_as_message(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Recoverable failures (bad path, oversized regex, non-UTF-8 read) should be returned as strings.

    Without these wrappers the model sees a raw stack trace for "you used ``..``"
    but a polite message for "the file already exists", which is the opposite
    of what is recoverable.
    """
    session = AgentSession(session_id="session-1")
    store = InMemoryAgentFileStore()
    provider = FileAccessProvider(store=store)
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    save_file = _tool_by_name(tools, "file_access_save_file")
    read_file = _tool_by_name(tools, "file_access_read_file")
    delete_file = _tool_by_name(tools, "file_access_delete_file")
    list_files = _tool_by_name(tools, "file_access_list_files")
    search_files = _tool_by_name(tools, "file_access_search_files")

    # Path-traversal attempts on each tool should return a clean string, not raise.
    saved = await save_file.invoke(arguments={"file_name": "../escape.txt", "content": "x"})
    assert "Could not save" in saved[0].text and "escape" in saved[0].text.lower()
    read = await read_file.invoke(arguments={"file_name": "../escape.txt"})
    assert "Could not read" in read[0].text
    deleted = await delete_file.invoke(arguments={"file_name": "../escape.txt"})
    assert "Could not delete" in deleted[0].text
    listed = await list_files.invoke(arguments={"directory": "../escape"})
    assert "Could not list" in listed[0].text

    # Regex length cap should also be returned to the model as text.
    too_long = "a" * 1024
    searched = await search_files.invoke(arguments={"regex_pattern": too_long})
    assert "Could not search files" in searched[0].text


async def test_file_access_tool_read_file_wrapper_surfaces_non_utf8(
    tmp_path: Path, chat_client_base: SupportsChatGetResponse
) -> None:
    """The read-file tool wrapper should convert a non-UTF-8 ``ValueError`` into a readable string."""
    store = FileSystemAgentFileStore(tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x80\x81\x82\x83")

    session = AgentSession(session_id="session-1")
    provider = FileAccessProvider(store=store)
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # type: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["read it"])],
    )
    read_file = _tool_by_name(options["tools"], "file_access_read_file")
    response = await read_file.invoke(arguments={"file_name": "blob.bin"})
    assert "Could not read" in response[0].text and "UTF-8" in response[0].text


_NEEDS_SYMLINK = "Symbolic links are not supported in this environment"


async def test_filesystem_store_rejects_symlink_on_delete_search_and_list(tmp_path: Path) -> None:
    """The same symlink probe must front delete/search/list, not just read/write."""
    target = tmp_path / "outside.txt"
    target.write_text("outside", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    link = root / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"{_NEEDS_SYMLINK}: {exc!r}")

    store = FileSystemAgentFileStore(root)

    with pytest.raises(ValueError, match="symbolic link"):
        await store.delete_file("link.txt")

    # search_files of the root never touches the symlink leaf directly, but
    # search_files of a symlinked *directory* path must be rejected by the
    # safe-directory resolver.
    dir_link = root / "alias_dir"
    other_dir = tmp_path / "outside_dir"
    other_dir.mkdir()
    try:
        dir_link.symlink_to(other_dir)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"{_NEEDS_SYMLINK}: {exc!r}")

    with pytest.raises(ValueError, match="symbolic link"):
        await store.search_files("alias_dir", "anything")
    with pytest.raises(ValueError, match="symbolic link"):
        await store.list_files("alias_dir")


async def test_filesystem_store_rejects_symlinked_intermediate_directory(tmp_path: Path) -> None:
    """A symlink used as a non-leaf path segment must still be rejected.

    The classic escape vector is ``root/aliased_dir/file.txt`` where
    ``aliased_dir`` is a symlink to somewhere outside the root. The
    ``_throw_if_contains_symlink`` walk must check every segment, not only
    the leaf.
    """
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    (outside / "secret.txt").write_text("payload", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    link = root / "aliased_dir"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"{_NEEDS_SYMLINK}: {exc!r}")

    store = FileSystemAgentFileStore(root)

    for op in ("read", "write", "delete"):
        with pytest.raises(ValueError, match="symbolic link"):
            if op == "read":
                await store.read_file("aliased_dir/secret.txt")
            elif op == "write":
                await store.write_file("aliased_dir/secret.txt", "stomp")
            else:
                await store.delete_file("aliased_dir/secret.txt")
