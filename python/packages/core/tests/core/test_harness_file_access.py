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
    Content,
    ExperimentalFeature,
    FileAccessProvider,
    FileSearchMatch,
    FileSearchResult,
    FileStoreEntry,
    FileSystemAgentFileStore,
    FunctionTool,
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


async def _list_files(store: AgentFileStore, directory: str = "") -> list[str]:
    """Return only the file names from a combined ``store.list_children`` call."""
    return [entry.name for entry in await store.list_children(directory) if entry.type == FileStoreEntry.FILE]


async def _list_dirs(store: AgentFileStore, directory: str = "") -> list[str]:
    """Return only the subdirectory names from a combined ``store.list_children`` call."""
    return [entry.name for entry in await store.list_children(directory) if entry.type == FileStoreEntry.DIRECTORY]


def _tool_by_name(tools: list[object], name: str) -> FunctionTool:
    """Return the tool with the requested name from a prepared tool list."""
    for tool in tools:
        if isinstance(tool, FunctionTool) and tool.name == name:
            return tool
    raise AssertionError(f"Tool {name!r} was not found.")


def _text(content: Content) -> str:
    assert content.text is not None
    return content.text


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

    await store.write("a.txt", "alpha")
    await store.write("sub/b.txt", "beta")

    assert await store.file_exists("a.txt")
    assert not await store.file_exists("missing.txt")
    assert await store.read("a.txt") == "alpha"
    assert await store.read("missing.txt") is None

    assert sorted(await _list_files(store)) == ["a.txt"]  # subdirs are not direct children
    assert sorted(await _list_files(store, "sub")) == ["b.txt"]

    assert await store.delete("a.txt") is True
    assert await store.delete("a.txt") is False
    assert sorted(await _list_files(store)) == []


async def test_in_memory_store_search_returns_matches_with_snippets() -> None:
    """The in-memory store should search file content case-insensitively and respect glob filters."""
    store = InMemoryAgentFileStore()
    await store.write("a.md", "line one\nThis line has ERROR inside\nline three\r")
    await store.write("b.md", "no match here")
    await store.write("notes.txt", "ERROR but wrong extension")

    results = await store.search("", "error", "*.md")
    assert [result.file_name for result in results] == ["a.md"]
    matching_lines = results[0].matching_lines
    assert matching_lines == [FileSearchMatch(line_number=2, line="This line has ERROR inside")]
    assert "ERROR" in results[0].snippet

    # No glob -> searches every file.
    results_all = await store.search("", "error")
    assert {result.file_name for result in results_all} == {"a.md", "notes.txt"}


async def test_in_memory_store_search_is_recursive_with_root_relative_names() -> None:
    """Recursive search should find files at any depth and return root-relative names."""
    store = InMemoryAgentFileStore()
    await store.write("top.md", "ERROR at top")
    await store.write("reports/q1.md", "ERROR in q1")
    await store.write("reports/2024/q2.md", "ERROR in q2")
    await store.write("reports/2024/data.txt", "ERROR wrong extension")

    # Non-recursive (default) only sees the direct child.
    direct = await store.search("", "error")
    assert {result.file_name for result in direct} == {"top.md"}

    # Recursive sees every descendant, with store-root-relative file names.
    recursive = await store.search("", "error", recursive=True)
    assert {result.file_name for result in recursive} == {
        "top.md",
        "reports/q1.md",
        "reports/2024/q2.md",
        "reports/2024/data.txt",
    }

    # Subtree scoping via the glob (``*`` crosses ``/`` with fnmatch).
    scoped = await store.search("", "error", "reports/*", recursive=True)
    assert {result.file_name for result in scoped} == {
        "reports/q1.md",
        "reports/2024/q2.md",
        "reports/2024/data.txt",
    }

    # Extension glob matches markdown at any depth but not other extensions.
    markdown = await store.search("", "error", "*.md", recursive=True)
    assert {result.file_name for result in markdown} == {
        "top.md",
        "reports/q1.md",
        "reports/2024/q2.md",
    }


async def test_in_memory_store_list_directories() -> None:
    """``list_directories`` should return direct child subdirectories only, preserving casing."""
    store = InMemoryAgentFileStore()
    await store.write("top.md", "x")
    await store.write("Reports/q1.md", "x")
    await store.write("Reports/2024/q2.md", "x")
    await store.write("data/raw.csv", "x")

    assert sorted(await _list_dirs(store)) == ["Reports", "data"]
    assert sorted(await _list_dirs(store, "Reports")) == ["2024"]
    # A directory with no subdirectories returns an empty list.
    assert await _list_dirs(store, "data") == []
    # A missing directory returns an empty list.
    assert await _list_dirs(store, "missing") == []


async def test_in_memory_store_list_directories_rejects_traversal() -> None:
    """``list_directories`` must reject traversal inputs the way ``list_files`` does."""
    store = InMemoryAgentFileStore()
    await store.write("reports/q1.md", "x")
    for bad in ("../escape", "/abs/path", ".."):
        with pytest.raises(ValueError):
            await _list_dirs(store, bad)


async def test_in_memory_store_search_rejects_invalid_and_oversize_regex() -> None:
    """``search`` should surface clean errors for bad regex input."""
    store = InMemoryAgentFileStore()
    await store.write("a.md", "hello")

    with pytest.raises(re.error):
        await store.search("", "[unclosed")

    with pytest.raises(ValueError, match="too long"):
        await store.search("", "a" * 257)


async def test_in_memory_store_normalizes_paths() -> None:
    """Path normalization should reject traversal in the in-memory store too."""
    store = InMemoryAgentFileStore()
    for bad in ("../escape.txt", "/abs/path.txt", "."):
        with pytest.raises(ValueError):
            await store.write(bad, "boom")


async def test_filesystem_store_round_trips_files(tmp_path: Path) -> None:
    """The filesystem store should round-trip files on disk and create parents on write."""
    store = FileSystemAgentFileStore(tmp_path)

    await store.write("nested/a.txt", "alpha")
    assert (tmp_path / "nested" / "a.txt").read_text(encoding="utf-8") == "alpha"

    assert await store.read("nested/a.txt") == "alpha"
    assert await store.read("missing.txt") is None
    assert await store.file_exists("nested/a.txt")
    assert not await store.file_exists("missing.txt")
    assert sorted(await _list_files(store, "nested")) == ["a.txt"]
    assert sorted(await _list_files(store)) == []  # root only contains the directory

    assert await store.delete("nested/a.txt") is True
    assert await store.delete("nested/a.txt") is False


async def test_filesystem_store_rejects_traversal_and_rooted_paths(tmp_path: Path) -> None:
    """The filesystem store should refuse paths that escape the configured root."""
    store = FileSystemAgentFileStore(tmp_path)

    for bad in ("../escape.txt", "/etc/passwd", "C:/Windows/System32/notepad.exe", ".", ".."):
        with pytest.raises(ValueError):
            await store.write(bad, "boom")


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
        await store.read("link.txt")
    with pytest.raises(ValueError, match="symbolic link"):
        await store.write("link.txt", "stomp")

    # List operations should silently skip the symlink entry rather than raise.
    assert await _list_files(store) == []


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
        await store.read("alias.txt")
    # The non-symlinked sibling must still be readable.
    assert await store.read("real.txt") == "payload"


async def test_filesystem_store_search_matches_lines_and_filters_globs(tmp_path: Path) -> None:
    """The filesystem store should search files on disk and apply glob filters by file name."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write("a.md", "hello\nERROR happens\nbye\r")
    await store.write("b.txt", "ERROR happens too")
    await store.write("c.md", "nothing here")

    results = await store.search("", "error", "*.md")
    assert [result.file_name for result in results] == ["a.md"]
    assert results[0].matching_lines == [FileSearchMatch(line_number=2, line="ERROR happens")]
    assert "ERROR" in results[0].snippet

    results_all = await store.search("", "error")
    assert {result.file_name for result in results_all} == {"a.md", "b.txt"}


async def test_filesystem_store_search_is_recursive_with_root_relative_names(tmp_path: Path) -> None:
    """Recursive filesystem search should walk the subtree and return root-relative names."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write("top.md", "ERROR at top")
    await store.write("reports/q1.md", "ERROR in q1")
    await store.write("reports/2024/q2.md", "ERROR in q2")

    direct = await store.search("", "error")
    assert {result.file_name for result in direct} == {"top.md"}

    recursive = await store.search("", "error", recursive=True)
    assert {result.file_name for result in recursive} == {
        "top.md",
        "reports/q1.md",
        "reports/2024/q2.md",
    }

    scoped = await store.search("", "error", "reports/*", recursive=True)
    assert {result.file_name for result in scoped} == {
        "reports/q1.md",
        "reports/2024/q2.md",
    }


async def test_filesystem_store_list_directories(tmp_path: Path) -> None:
    """``list_directories`` should list direct child subdirectories only."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write("top.md", "x")
    await store.write("reports/q1.md", "x")
    await store.write("reports/2024/q2.md", "x")
    await store.write("data/raw.csv", "x")

    assert sorted(await _list_dirs(store)) == ["data", "reports"]
    assert sorted(await _list_dirs(store, "reports")) == ["2024"]
    assert await _list_dirs(store, "data") == []
    assert await _list_dirs(store, "missing") == []


async def test_filesystem_store_list_directories_rejects_traversal(tmp_path: Path) -> None:
    """``list_directories`` is security-critical and must reject paths that escape the root."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write("reports/q1.md", "x")
    for bad in ("../escape", "/etc", "C:/Windows", ".."):
        with pytest.raises(ValueError):
            await _list_dirs(store, bad)


async def test_filesystem_store_search_and_list_skip_symlinked_directories(tmp_path: Path) -> None:
    """Recursive search must not descend into symlinked dirs and ``list_directories`` must exclude them."""
    target = tmp_path / "outside"
    target.mkdir()
    (target / "secret.md").write_text("ERROR outside the root", encoding="utf-8")

    root = tmp_path / "root"
    root.mkdir()
    (root / "inside.md").write_text("ERROR inside", encoding="utf-8")
    link = root / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symbolic links are not supported in this environment: {exc!r}")

    store = FileSystemAgentFileStore(root)

    # ``list_directories`` excludes the symlinked directory.
    assert await _list_dirs(store) == []

    # Recursive search does not follow the symlink out of the root.
    results = await store.search("", "error", recursive=True)
    assert {result.file_name for result in results} == {"inside.md"}


async def test_filesystem_store_search_skips_non_utf8_files(tmp_path: Path) -> None:
    """The filesystem store should silently skip non-UTF-8 files instead of aborting the search."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write("notes.md", "ERROR happens here")
    (tmp_path / "blob.bin").write_bytes(b"\x80\x81\x82\x83")

    results = await store.search("", "error")
    assert [result.file_name for result in results] == ["notes.md"]


async def test_filesystem_store_create_directory(tmp_path: Path) -> None:
    """The filesystem store should create directories under the configured root."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.create_directory("nested/inner")
    assert (tmp_path / "nested" / "inner").is_dir()


async def test_filesystem_store_list_files_accepts_blank_directory(tmp_path: Path) -> None:
    """Whitespace-only directory inputs should resolve to the root, matching the in-memory store."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write("a.txt", "alpha")
    assert sorted(await _list_files(store, "")) == ["a.txt"]
    assert sorted(await _list_files(store, "   ")) == ["a.txt"]


def test_filesystem_store_requires_non_empty_root() -> None:
    """The filesystem store constructor should refuse blank root paths."""
    with pytest.raises(ValueError, match="must not be empty"):
        FileSystemAgentFileStore("")
    with pytest.raises(ValueError, match="must not be empty"):
        FileSystemAgentFileStore("   ")


async def test_filesystem_store_does_not_create_root_until_write(tmp_path: Path) -> None:
    """Constructing a store must not touch the filesystem; the root is created lazily on first write."""
    root = tmp_path / "does-not-exist-yet"

    # Construction performs no filesystem writes (safe in read-only CWDs).
    store = FileSystemAgentFileStore(root)
    assert not root.exists()

    # Read-only operations tolerate the missing root without creating it.
    assert await store.read("a.txt") is None
    assert await store.file_exists("a.txt") is False
    assert await _list_files(store) == []
    assert await _list_dirs(store) == []
    assert await store.search("", ".") == []
    assert not root.exists()

    # The first write creates the root directory lazily.
    await store.write("a.txt", "alpha")
    assert root.is_dir()
    assert await store.read("a.txt") == "alpha"


async def test_file_access_provider_registers_tools_and_instructions(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """``FileAccessProvider.before_run`` should add the canonical instructions and all tools."""
    session = AgentSession(session_id="session-1")
    store = InMemoryAgentFileStore()
    provider = FileAccessProvider(store=store)
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )

    tools = options["tools"]
    assert isinstance(tools, list)
    expected_names = {
        "file_access_write",
        "file_access_read",
        "file_access_delete",
        "file_access_ls",
        "file_access_grep",
        "file_access_replace",
        "file_access_replace_lines",
    }
    assert {getattr(tool, "name", None) for tool in tools} >= expected_names

    instructions = options.get("instructions")
    if isinstance(instructions, str):
        assert DEFAULT_FILE_ACCESS_INSTRUCTIONS in instructions
    else:
        assert any(DEFAULT_FILE_ACCESS_INSTRUCTIONS in chunk for chunk in (instructions or []))


async def test_file_access_provider_all_tools_require_approval(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """Every file-access tool should require host approval."""
    session = AgentSession(session_id="session-1")
    provider = FileAccessProvider(store=InMemoryAgentFileStore())
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )

    tools = options["tools"]
    assert isinstance(tools, list)
    for name in (
        FileAccessProvider.WRITE_TOOL_NAME,
        FileAccessProvider.READ_TOOL_NAME,
        FileAccessProvider.DELETE_TOOL_NAME,
        FileAccessProvider.LS_TOOL_NAME,
        FileAccessProvider.GREP_TOOL_NAME,
        FileAccessProvider.REPLACE_TOOL_NAME,
        FileAccessProvider.REPLACE_LINES_TOOL_NAME,
    ):
        assert _tool_by_name(tools, name).approval_mode == "always_require"


async def test_file_access_provider_approval_opt_outs(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """The approval opt-out flags flip only the affected tool group to ``never_require``."""
    readonly_names = (
        FileAccessProvider.READ_TOOL_NAME,
        FileAccessProvider.LS_TOOL_NAME,
        FileAccessProvider.GREP_TOOL_NAME,
    )
    write_names = (
        FileAccessProvider.WRITE_TOOL_NAME,
        FileAccessProvider.DELETE_TOOL_NAME,
        FileAccessProvider.REPLACE_TOOL_NAME,
        FileAccessProvider.REPLACE_LINES_TOOL_NAME,
    )

    # Disabling read-only approval only affects the read-only tools.
    tools = await _prepare_access_tools(chat_client_base, disable_readonly_tool_approval=True)
    for name in readonly_names:
        assert _tool_by_name(tools, name).approval_mode == "never_require"
    for name in write_names:
        assert _tool_by_name(tools, name).approval_mode == "always_require"

    # Disabling write approval only affects the write tools.
    tools = await _prepare_access_tools(chat_client_base, disable_write_tool_approval=True)
    for name in readonly_names:
        assert _tool_by_name(tools, name).approval_mode == "always_require"
    for name in write_names:
        assert _tool_by_name(tools, name).approval_mode == "never_require"

    # Disabling both drops approval everywhere.
    tools = await _prepare_access_tools(
        chat_client_base, disable_readonly_tool_approval=True, disable_write_tool_approval=True
    )
    for name in (*readonly_names, *write_names):
        assert _tool_by_name(tools, name).approval_mode == "never_require"


def test_read_only_tools_auto_approval_rule() -> None:
    """The read-only rule approves only the non-mutating tools."""
    approved = {
        FileAccessProvider.READ_TOOL_NAME,
        FileAccessProvider.LS_TOOL_NAME,
        FileAccessProvider.GREP_TOOL_NAME,
    }
    rejected = {
        FileAccessProvider.WRITE_TOOL_NAME,
        FileAccessProvider.DELETE_TOOL_NAME,
        FileAccessProvider.REPLACE_TOOL_NAME,
        FileAccessProvider.REPLACE_LINES_TOOL_NAME,
        "some_other_tool",
    }
    for name in approved:
        call = Content("function_call", call_id="c1", name=name, arguments="{}")
        assert FileAccessProvider.read_only_tools_auto_approval_rule(call) is True
    for name in rejected:
        call = Content("function_call", call_id="c1", name=name, arguments="{}")
        assert FileAccessProvider.read_only_tools_auto_approval_rule(call) is False
    # A hosted tool with the same name (carrying a server_label) is NOT auto-approved.
    for name in approved:
        hosted = Content(
            "function_call",
            call_id="c1",
            name=name,
            arguments="{}",
            additional_properties={"server_label": "remote"},
        )
        assert FileAccessProvider.read_only_tools_auto_approval_rule(hosted) is False


def test_all_tools_auto_approval_rule() -> None:
    """The all-tools rule approves every file-access tool but nothing else."""
    for name in (
        FileAccessProvider.WRITE_TOOL_NAME,
        FileAccessProvider.READ_TOOL_NAME,
        FileAccessProvider.DELETE_TOOL_NAME,
        FileAccessProvider.LS_TOOL_NAME,
        FileAccessProvider.GREP_TOOL_NAME,
        FileAccessProvider.REPLACE_TOOL_NAME,
        FileAccessProvider.REPLACE_LINES_TOOL_NAME,
    ):
        call = Content("function_call", call_id="c1", name=name, arguments="{}")
        assert FileAccessProvider.all_tools_auto_approval_rule(call) is True
        # A hosted tool with the same name (carrying a server_label) is NOT auto-approved.
        hosted = Content(
            "function_call",
            call_id="c1",
            name=name,
            arguments="{}",
            additional_properties={"server_label": "remote"},
        )
        assert FileAccessProvider.all_tools_auto_approval_rule(hosted) is False

    unrelated = Content("function_call", call_id="c1", name="some_other_tool", arguments="{}")
    assert FileAccessProvider.all_tools_auto_approval_rule(unrelated) is False


async def test_file_access_provider_tools_round_trip_files(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """The provider's tools should drive save/read/list/search/delete flows on an ``InMemoryAgentFileStore``."""
    session = AgentSession(session_id="session-1")
    store = InMemoryAgentFileStore()
    provider = FileAccessProvider(store=store)
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    save_file = _tool_by_name(tools, "file_access_write")
    read = _tool_by_name(tools, "file_access_read")
    delete = _tool_by_name(tools, "file_access_delete")
    ls = _tool_by_name(tools, "file_access_ls")
    search = _tool_by_name(tools, "file_access_grep")

    saved = await save_file.invoke(arguments={"file_name": "plan.md", "content": "step 1\nERROR step 2"})
    assert "plan.md" in _text(saved[0]) and "written" in _text(saved[0])

    # Default overwrite=False should refuse the second save.
    refused = await save_file.invoke(arguments={"file_name": "plan.md", "content": "stomp"})
    assert "already exists" in _text(refused[0])

    # overwrite=True should succeed.
    overwritten = await save_file.invoke(
        arguments={"file_name": "plan.md", "content": "stomp\nERROR replaced", "overwrite": True}
    )
    assert "written" in _text(overwritten[0])

    read_back = await read.invoke(arguments={"file_name": "plan.md"})
    assert _text(read_back[0]) == "stomp\nERROR replaced"

    listed = await ls.invoke()
    assert json.loads(_text(listed[0])) == [{"name": "plan.md", "type": "file"}]

    # The ls tool should accept an optional directory argument so agents can
    # enumerate nested folders (not only the root).
    await save_file.invoke(arguments={"file_name": "reports/2024.md", "content": "annual"})
    listed_nested = await ls.invoke(arguments={"directory": "reports"})
    assert json.loads(_text(listed_nested[0])) == [{"name": "2024.md", "type": "file"}]
    # Blank / whitespace directory should fall back to the root listing, showing the
    # "reports" directory and the "plan.md" file (directories listed first).
    listed_blank = await ls.invoke(arguments={"directory": "   "})
    assert json.loads(_text(listed_blank[0])) == [
        {"name": "reports", "type": "directory"},
        {"name": "plan.md", "type": "file"},
    ]
    # A glob pattern filters the listing to files only.
    listed_pattern = await ls.invoke(arguments={"glob_pattern": "*.md"})
    assert json.loads(_text(listed_pattern[0])) == [{"name": "plan.md", "type": "file"}]

    missing = await read.invoke(arguments={"file_name": "missing.md"})
    assert "not found" in _text(missing[0])

    search_payload = await search.invoke(arguments={"regex_pattern": "error", "glob_pattern": "*.md"})
    parsed = json.loads(_text(search_payload[0]))
    assert parsed[0]["file_name"] == "plan.md"
    assert parsed[0]["matching_lines"][0]["line"] == "ERROR replaced"

    # The search tool is recursive from the store root; scope to a subtree using
    # the glob (``*`` crosses ``/`` with fnmatch). Results use root-relative names.
    await save_file.invoke(arguments={"file_name": "reports/issues.md", "content": "ERROR nested"})
    scoped = await search.invoke(arguments={"regex_pattern": "error", "glob_pattern": "reports/*"})
    scoped_parsed = json.loads(_text(scoped[0]))
    assert [entry["file_name"] for entry in scoped_parsed] == ["reports/issues.md"]
    # The directory param restricts the search base, but returned names stay relative to the
    # store root so they compose directly with file_access_read/replace/delete.
    scoped_dir = await search.invoke(arguments={"regex_pattern": "error", "directory": "reports"})
    scoped_dir_parsed = json.loads(_text(scoped_dir[0]))
    assert [entry["file_name"] for entry in scoped_dir_parsed] == ["reports/issues.md"]
    # The grep result name is usable directly with file_access_read.
    reread = await read.invoke(arguments={"file_name": scoped_dir_parsed[0]["file_name"]})
    assert "ERROR nested" in _text(reread[0])

    deleted = await delete.invoke(arguments={"file_name": "plan.md"})
    assert "deleted" in _text(deleted[0])

    missing_delete = await delete.invoke(arguments={"file_name": "plan.md"})
    assert "not found" in _text(missing_delete[0])


async def test_file_access_provider_accepts_custom_instructions() -> None:
    """Custom instructions should override the default banner."""
    store = InMemoryAgentFileStore()
    provider = FileAccessProvider(store=store, instructions="custom-banner")
    assert provider.instructions == "custom-banner"
    assert provider.source_id == DEFAULT_FILE_ACCESS_SOURCE_ID


async def test_in_memory_store_write_file_raises_when_exists_and_no_overwrite() -> None:
    """The atomic exclusive-create path should raise ``FileExistsError`` under the lock."""
    store = InMemoryAgentFileStore()
    await store.write("plan.md", "v1")

    with pytest.raises(FileExistsError):
        await store.write("plan.md", "v2", overwrite=False)

    # The original content is preserved.
    assert await store.read("plan.md") == "v1"

    # Default ``overwrite=True`` still replaces.
    await store.write("plan.md", "v3")
    assert await store.read("plan.md") == "v3"


async def test_filesystem_store_write_file_raises_when_exists_and_no_overwrite(tmp_path: Path) -> None:
    """The filesystem store should use exclusive-create semantics when ``overwrite=False``."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write("plan.md", "v1")

    with pytest.raises(FileExistsError):
        await store.write("plan.md", "v2", overwrite=False)

    assert (tmp_path / "plan.md").read_text(encoding="utf-8") == "v1"

    await store.write("plan.md", "v3", overwrite=True)
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
    await store.write("ok.txt", "content")

    def boom(self: Path) -> bool:
        raise PermissionError("access denied")

    monkeypatch.setattr(Path, "is_symlink", boom)

    with pytest.raises(ValueError, match="symbolic link or reparse point"):
        await store.read("ok.txt")


def test_file_access_harness_classes_are_marked_experimental() -> None:
    """File-access harness public classes should expose HARNESS experimental metadata."""
    assert getattr(AgentFileStore, "__feature_id__", None) == ExperimentalFeature.HARNESS.value
    assert getattr(InMemoryAgentFileStore, "__feature_id__", None) == ExperimentalFeature.HARNESS.value
    assert getattr(FileSystemAgentFileStore, "__feature_id__", None) == ExperimentalFeature.HARNESS.value
    assert getattr(FileSearchMatch, "__feature_id__", None) == ExperimentalFeature.HARNESS.value
    assert getattr(FileSearchResult, "__feature_id__", None) == ExperimentalFeature.HARNESS.value
    assert getattr(FileAccessProvider, "__feature_id__", None) == ExperimentalFeature.HARNESS.value
    assert ".. warning:: Experimental" in (FileAccessProvider.__doc__ or "")


async def test_in_memory_store_preserves_original_case_on_list_and_search() -> None:
    """``list_files`` / ``search`` should return original-case names, not lowercased keys.

    Matches :class:`FileSystemAgentFileStore` on case-preserving filesystems so
    tests written against the in-memory backend cannot encode a contract that
    will diverge in production.
    """
    store = InMemoryAgentFileStore()
    await store.write("Plan.MD", "ERROR happens here\n")
    await store.write("Reports/Q1.MD", "alpha")

    # list_files keeps the original case
    assert sorted(await _list_files(store)) == ["Plan.MD"]
    assert sorted(await _list_files(store, "Reports")) == ["Q1.MD"]

    # case-insensitive directory lookup still works
    assert sorted(await _list_files(store, "reports")) == ["Q1.MD"]

    # search emits the original-case file name in FileSearchResult
    results = await store.search("", "error", "*.MD")
    assert [r.file_name for r in results] == ["Plan.MD"]

    # read remains case-insensitive
    assert await store.read("plan.md") == "ERROR happens here\n"


async def test_filesystem_store_read_file_raises_value_error_on_non_utf8(tmp_path: Path) -> None:
    """Binary / non-UTF-8 files should raise a clean ``ValueError`` rather than ``UnicodeDecodeError``.

    The tool-layer wrapper relies on this contract to convert the failure into
    a recoverable string response for the agent.
    """
    store = FileSystemAgentFileStore(tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x80\x81\x82\x83")

    with pytest.raises(ValueError, match="not UTF-8 text"):
        await store.read("blob.bin")


async def test_filesystem_store_search_logs_skipped_non_utf8_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``search`` skips non-UTF-8 files but logs per-file and a summary so operators have signal."""
    store = FileSystemAgentFileStore(tmp_path)
    await store.write("notes.md", "ERROR happens here")
    (tmp_path / "blob.bin").write_bytes(b"\x80\x81\x82\x83")

    with caplog.at_level("INFO", logger="agent_framework._harness._file_access"):
        results = await store.search("", "error")

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

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)

    save_file = _tool_by_name(tools, "file_access_write")
    read = _tool_by_name(tools, "file_access_read")
    delete = _tool_by_name(tools, "file_access_delete")
    list_files = _tool_by_name(tools, "file_access_ls")
    search = _tool_by_name(tools, "file_access_grep")

    # Path-traversal attempts on each tool should return a clean string, not raise.
    saved = await save_file.invoke(arguments={"file_name": "../escape.txt", "content": "x"})
    assert "Could not write" in _text(saved[0]) and "escape" in _text(saved[0]).lower()
    read_result = await read.invoke(arguments={"file_name": "../escape.txt"})
    assert "Could not read" in _text(read_result[0])
    deleted = await delete.invoke(arguments={"file_name": "../escape.txt"})
    assert "Could not delete" in _text(deleted[0])
    listed = await list_files.invoke(arguments={"directory": "../escape"})
    assert "Could not list" in _text(listed[0])

    # Regex length cap should also be returned to the model as text.
    too_long = "a" * 1024
    searched = await search.invoke(arguments={"regex_pattern": too_long})
    assert "Could not search files" in _text(searched[0])

    # An invalid regex is surfaced to the caller (the model) as a raised error
    # so it can correct the pattern and retry.
    with pytest.raises(re.error):
        await search.invoke(arguments={"regex_pattern": "[unclosed"})


async def test_file_access_tool_read_file_wrapper_surfaces_non_utf8(
    tmp_path: Path, chat_client_base: SupportsChatGetResponse
) -> None:
    """The read-file tool wrapper should convert a non-UTF-8 ``ValueError`` into a readable string."""
    store = FileSystemAgentFileStore(tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x80\x81\x82\x83")

    session = AgentSession(session_id="session-1")
    provider = FileAccessProvider(store=store)
    agent = Agent(client=chat_client_base, context_providers=[provider])

    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["read it"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)
    read = _tool_by_name(tools, "file_access_read")
    response = await read.invoke(arguments={"file_name": "blob.bin"})
    assert "Could not read" in _text(response[0]) and "UTF-8" in _text(response[0])


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
        await store.delete("link.txt")

    # search of the root never touches the symlink leaf directly, but
    # search of a symlinked *directory* path must be rejected by the
    # safe-directory resolver.
    dir_link = root / "alias_dir"
    other_dir = tmp_path / "outside_dir"
    other_dir.mkdir()
    try:
        dir_link.symlink_to(other_dir)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"{_NEEDS_SYMLINK}: {exc!r}")

    with pytest.raises(ValueError, match="symbolic link"):
        await store.search("alias_dir", "anything")
    with pytest.raises(ValueError, match="symbolic link"):
        await _list_files(store, "alias_dir")


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
                await store.read("aliased_dir/secret.txt")
            elif op == "write":
                await store.write("aliased_dir/secret.txt", "stomp")
            else:
                await store.delete("aliased_dir/secret.txt")


async def _prepare_access_tools(
    chat_client_base: SupportsChatGetResponse,
    *,
    disable_write_tools: bool = False,
    disable_readonly_tool_approval: bool = False,
    disable_write_tool_approval: bool = False,
) -> list[object]:
    """Prepare a FileAccessProvider and return its registered tools."""
    session = AgentSession(session_id="session-1")
    provider = FileAccessProvider(
        store=InMemoryAgentFileStore(),
        disable_write_tools=disable_write_tools,
        disable_readonly_tool_approval=disable_readonly_tool_approval,
        disable_write_tool_approval=disable_write_tool_approval,
    )
    agent = Agent(client=chat_client_base, context_providers=[provider])
    _, options = await agent._prepare_session_and_messages(  # pyright: ignore[reportPrivateUsage]
        session=session,
        input_messages=[Message(role="user", contents=["work with files"])],
    )
    tools = options["tools"]
    assert isinstance(tools, list)
    return tools


async def test_file_access_replace(chat_client_base: SupportsChatGetResponse) -> None:
    """``file_access_replace`` should substitute text and enforce match-count rules."""
    tools = await _prepare_access_tools(chat_client_base)
    save = _tool_by_name(tools, "file_access_write")
    read = _tool_by_name(tools, "file_access_read")
    replace = _tool_by_name(tools, "file_access_replace")

    await save.invoke(arguments={"file_name": "a.txt", "content": "foo bar foo"})

    # Not found -> failure.
    missing = await replace.invoke(arguments={"file_name": "a.txt", "old_string": "zzz", "new_string": "q"})
    assert "not found" in _text(missing[0]).lower()

    # Multiple occurrences without replace_all -> failure.
    multi = await replace.invoke(arguments={"file_name": "a.txt", "old_string": "foo", "new_string": "baz"})
    assert "2 times" in _text(multi[0])

    # replace_all replaces every occurrence and reports the count.
    done = await replace.invoke(
        arguments={"file_name": "a.txt", "old_string": "foo", "new_string": "baz", "replace_all": True}
    )
    assert "2 occurrence" in _text(done[0])
    assert _text((await read.invoke(arguments={"file_name": "a.txt"}))[0]) == "baz bar baz"

    # Unique single occurrence with the default replace_all=False -> replaces exactly one.
    await save.invoke(arguments={"file_name": "u.txt", "content": "alpha beta gamma", "overwrite": True})
    single = await replace.invoke(arguments={"file_name": "u.txt", "old_string": "beta", "new_string": "BETA"})
    assert "1 occurrence" in _text(single[0])
    assert _text((await read.invoke(arguments={"file_name": "u.txt"}))[0]) == "alpha BETA gamma"

    # Missing file -> not found.
    none = await replace.invoke(arguments={"file_name": "none.txt", "old_string": "x", "new_string": "y"})
    assert "not found" in _text(none[0])


async def test_file_access_replace_lines(chat_client_base: SupportsChatGetResponse) -> None:
    """``file_access_replace_lines`` should apply literal 1-based line edits and reject bad input."""
    tools = await _prepare_access_tools(chat_client_base)
    save = _tool_by_name(tools, "file_access_write")
    read = _tool_by_name(tools, "file_access_read")
    replace_lines = _tool_by_name(tools, "file_access_replace_lines")

    async def write(content: str) -> None:
        await save.invoke(arguments={"file_name": "a.txt", "content": content, "overwrite": True})

    async def current() -> str:
        return _text((await read.invoke(arguments={"file_name": "a.txt"}))[0])

    # Literal replacement: the caller supplies the trailing newline.
    await write("one\ntwo\nthree")
    done = await replace_lines.invoke(
        arguments={"file_name": "a.txt", "edits": [{"line_number": 2, "new_line": "TWO\n"}]}
    )
    assert "1 line" in _text(done[0])
    assert await current() == "one\nTWO\nthree"

    # Empty new_line deletes a middle line, including its terminator.
    await write("line1\nline2\nline3\n")
    await replace_lines.invoke(arguments={"file_name": "a.txt", "edits": [{"line_number": 2, "new_line": ""}]})
    assert await current() == "line1\nline3\n"

    # Empty new_line deletes the last line even when it has no terminator.
    await write("line1\nline2")
    await replace_lines.invoke(arguments={"file_name": "a.txt", "edits": [{"line_number": 2, "new_line": ""}]})
    assert await current() == "line1\n"

    # Delete + replace in the same call.
    await write("a\nb\nc\n")
    await replace_lines.invoke(
        arguments={
            "file_name": "a.txt",
            "edits": [{"line_number": 1, "new_line": ""}, {"line_number": 3, "new_line": "C\n"}],
        }
    )
    assert await current() == "b\nC\n"

    # Embedded newlines expand one line into several.
    await write("a\nb\nc\n")
    await replace_lines.invoke(arguments={"file_name": "a.txt", "edits": [{"line_number": 2, "new_line": "b1\nb2\n"}]})
    assert await current() == "a\nb1\nb2\nc\n"

    # CRLF terminators are preserved when the caller keeps them.
    await write("line1\r\nline2\r\nline3")
    await replace_lines.invoke(
        arguments={"file_name": "a.txt", "edits": [{"line_number": 2, "new_line": "CHANGED\r\n"}]}
    )
    assert await current() == "line1\r\nCHANGED\r\nline3"

    # Out-of-range line -> failure.
    await write("one\ntwo\nthree")
    oor = await replace_lines.invoke(arguments={"file_name": "a.txt", "edits": [{"line_number": 9, "new_line": "x"}]})
    assert "out of range" in _text(oor[0])

    # Empty edits list -> failure.
    empty = await replace_lines.invoke(arguments={"file_name": "a.txt", "edits": []})
    assert "At least one line edit" in _text(empty[0])

    # Duplicate line numbers -> failure.
    dup = await replace_lines.invoke(
        arguments={
            "file_name": "a.txt",
            "edits": [{"line_number": 1, "new_line": "x"}, {"line_number": 1, "new_line": "y"}],
        }
    )
    assert "Duplicate" in _text(dup[0])


async def test_file_access_grep_line_numbers_are_editable(chat_client_base: SupportsChatGetResponse) -> None:
    """A ``line_number`` returned by ``file_access_grep`` must be in range for ``replace_lines``.

    This is the core cross-tool invariant: agents locate lines with grep and then edit
    them by number, so the two tools must enumerate lines identically -- including the
    trailing empty line of a newline-terminated file and interior blank lines.
    """
    tools = await _prepare_access_tools(chat_client_base)
    save = _tool_by_name(tools, "file_access_write")
    read = _tool_by_name(tools, "file_access_read")
    grep = _tool_by_name(tools, "file_access_grep")
    replace_lines = _tool_by_name(tools, "file_access_replace_lines")

    async def write(content: str) -> None:
        await save.invoke(arguments={"file_name": "a.txt", "content": content, "overwrite": True})

    async def current() -> str:
        return _text((await read.invoke(arguments={"file_name": "a.txt"}))[0])

    async def grep_line_numbers(pattern: str) -> list[int]:
        result = await grep.invoke(arguments={"regex_pattern": pattern, "glob_pattern": "a.txt"})
        payload = json.loads(_text(result[0]))
        return [match["line_number"] for entry in payload for match in entry["matching_lines"]]

    # Interior blank line: grep ^$ finds it, replace_lines can fill it in range.
    # The trailing empty line (line 4) is also exposed by grep -- both must be editable.
    await write("a\n\nc\n")
    blanks = await grep_line_numbers("^$")
    assert blanks == [2, 4]
    await replace_lines.invoke(
        arguments={"file_name": "a.txt", "edits": [{"line_number": blanks[0], "new_line": "b\n"}]}
    )
    assert await current() == "a\nb\nc\n"

    # Trailing empty line of a newline-terminated file: grep exposes it and it is
    # editable (e.g. to append), rather than being rejected as out of range.
    await write("a\nb\n")
    trailing = await grep_line_numbers("^$")
    assert trailing == [3]
    appended = await replace_lines.invoke(
        arguments={"file_name": "a.txt", "edits": [{"line_number": trailing[0], "new_line": "c\n"}]}
    )
    assert "out of range" not in _text(appended[0])
    assert await current() == "a\nb\nc\n"


async def test_file_access_disable_write_tools_hides_write_tools(
    chat_client_base: SupportsChatGetResponse,
) -> None:
    """When ``disable_write_tools`` is set only the read-only tools are advertised."""
    tools = await _prepare_access_tools(chat_client_base, disable_write_tools=True)
    names = {getattr(tool, "name", None) for tool in tools}
    assert "file_access_read" in names
    assert "file_access_ls" in names
    assert "file_access_grep" in names
    assert "file_access_write" not in names
    assert "file_access_delete" not in names
    assert "file_access_replace" not in names
    assert "file_access_replace_lines" not in names
