# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import re

import pytest

from agent_framework import (
    AgentSession,
    Content,
    FileMemoryProvider,
    FunctionTool,
    InMemoryAgentFileStore,
)
from agent_framework._harness._file_memory import (
    _MAX_INDEX_ENTRIES,
    _MEMORY_INDEX_FILE_NAME,
    DEFAULT_FILE_MEMORY_INSTRUCTIONS,
    DEFAULT_FILE_MEMORY_SOURCE_ID,
    _combine_paths,
    _description_file_name,
    _is_internal_file,
)
from agent_framework._sessions import SessionContext


def _tool_by_name(tools: list[object], name: str) -> object:
    """Return the tool with the requested name from a prepared tool list."""
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return tool
    raise AssertionError(f"Tool {name!r} was not found.")


def _text(result: list[Content]) -> str:
    """Return the first content item's text (memory tools always emit text)."""
    return result[0].text or ""


async def _prepare(
    provider: FileMemoryProvider, *, session_id: str = "session-1"
) -> tuple[SessionContext, dict[str, FunctionTool]]:
    """Run ``before_run`` against a fresh session context and return tools by name."""
    session = AgentSession(session_id=session_id)
    context = SessionContext(session_id=session_id, input_messages=[])
    await provider.before_run(agent=None, session=session, context=context, state={})
    tools: dict[str, FunctionTool] = {tool.name: tool for tool in context.tools}
    return context, tools


def test_description_file_name_replaces_extension() -> None:
    """The description sidecar replaces a known extension and appends otherwise."""
    assert _description_file_name("notes.md") == "notes_description.md"
    assert _description_file_name("data.json") == "data_description.md"
    assert _description_file_name("noext") == "noext_description.md"
    # Leading-dot files have no stem, so the suffix is appended.
    assert _description_file_name(".hidden") == ".hidden_description.md"


def test_is_internal_file_detects_sidecars_and_index() -> None:
    """Internal files are description sidecars and the memory index, case-insensitively."""
    assert _is_internal_file("notes_description.md")
    assert _is_internal_file("NOTES_DESCRIPTION.MD")
    assert _is_internal_file(_MEMORY_INDEX_FILE_NAME)
    assert _is_internal_file("Memories.md")
    assert not _is_internal_file("notes.md")
    assert not _is_internal_file("description.md")


def test_combine_paths_joins_with_forward_slash() -> None:
    """Working-folder paths join with a single forward slash and tolerate empties."""
    assert _combine_paths("session-1", "notes.md") == "session-1/notes.md"
    assert _combine_paths("session-1/", "/notes.md") == "session-1/notes.md"
    assert _combine_paths("", "notes.md") == "notes.md"
    assert _combine_paths("session-1", "") == "session-1"


async def test_provider_registers_tools_and_instructions() -> None:
    """``before_run`` should register all tools and the default instructions."""
    provider = FileMemoryProvider(store=InMemoryAgentFileStore())
    context, tools = await _prepare(provider)

    expected = {
        "file_memory_write",
        "file_memory_read",
        "file_memory_delete",
        "file_memory_ls",
        "file_memory_grep",
        "file_memory_replace",
        "file_memory_replace_lines",
    }
    assert set(tools) >= expected
    assert all(t.approval_mode == "never_require" for t in context.tools)  # type: ignore[attr-defined]
    assert any(DEFAULT_FILE_MEMORY_INSTRUCTIONS in chunk for chunk in context.instructions)


async def test_provider_uses_default_source_id() -> None:
    """The default source id should match the public constant."""
    provider = FileMemoryProvider(store=InMemoryAgentFileStore())
    assert provider.source_id == DEFAULT_FILE_MEMORY_SOURCE_ID


async def test_save_read_delete_round_trip() -> None:
    """The tools should drive a save/read/list/delete flow with index maintenance."""
    store = InMemoryAgentFileStore()
    provider = FileMemoryProvider(store=store)
    _, tools = await _prepare(provider)

    save = tools["file_memory_write"]
    read = tools["file_memory_read"]
    delete = tools["file_memory_delete"]
    list_files = tools["file_memory_ls"]

    saved = await save.invoke(arguments={"file_name": "plan.md", "content": "step 1"})
    assert "plan.md" in _text(saved) and "written" in _text(saved)

    read_back = await read.invoke(arguments={"file_name": "plan.md"})
    assert _text(read_back) == "step 1"

    # Overwrite is allowed (no overwrite flag needed).
    await save.invoke(arguments={"file_name": "plan.md", "content": "step 2"})
    assert _text(await read.invoke(arguments={"file_name": "plan.md"})) == "step 2"

    listed = json.loads(_text(await list_files.invoke()))
    assert listed == [{"name": "plan.md", "type": "file", "description": None}]

    deleted = await delete.invoke(arguments={"file_name": "plan.md"})
    assert "deleted" in _text(deleted)
    missing = await read.invoke(arguments={"file_name": "plan.md"})
    assert "not found" in _text(missing)
    missing_delete = await delete.invoke(arguments={"file_name": "plan.md"})
    assert "not found" in _text(missing_delete)


async def test_description_sidecar_is_written_and_listed() -> None:
    """Saving with a description writes a sidecar and surfaces it in listings."""
    store = InMemoryAgentFileStore()
    provider = FileMemoryProvider(store=store, scope="user-1")
    _, tools = await _prepare(provider)
    save = tools["file_memory_write"]
    list_files = tools["file_memory_ls"]

    result = await save.invoke(
        arguments={"file_name": "arch.md", "content": "big content", "description": "system architecture"}
    )
    assert "with description" in _text(result)

    sidecar = await store.read(_combine_paths("user-1", "arch_description.md"))
    assert sidecar == "system architecture"

    listed = json.loads(_text(await list_files.invoke()))
    assert listed == [{"name": "arch.md", "type": "file", "description": "system architecture"}]

    # Re-saving without a description removes the sidecar.
    await save.invoke(arguments={"file_name": "arch.md", "content": "big content"})
    assert await store.read(_combine_paths("user-1", "arch_description.md")) is None
    listed_again = json.loads(_text(await list_files.invoke()))
    assert listed_again == [{"name": "arch.md", "type": "file", "description": None}]


async def test_delete_removes_sidecar() -> None:
    """Deleting a file also removes its companion description sidecar."""
    store = InMemoryAgentFileStore()
    provider = FileMemoryProvider(store=store, scope="user-1")
    _, tools = await _prepare(provider)

    await tools["file_memory_write"].invoke(arguments={"file_name": "arch.md", "content": "x", "description": "desc"})
    assert await store.read(_combine_paths("user-1", "arch_description.md")) == "desc"

    await tools["file_memory_delete"].invoke(arguments={"file_name": "arch.md"})
    assert await store.read(_combine_paths("user-1", "arch_description.md")) is None


async def test_index_is_rebuilt_and_injected_on_next_run() -> None:
    """Saved memories should be summarized in the index and injected as a context message."""
    store = InMemoryAgentFileStore()
    provider = FileMemoryProvider(store=store, scope="user-1")
    _, tools = await _prepare(provider)

    await tools["file_memory_write"].invoke(
        arguments={"file_name": "arch.md", "content": "x", "description": "architecture"}
    )
    await tools["file_memory_write"].invoke(arguments={"file_name": "todo.md", "content": "y"})

    index = await store.read(_combine_paths("user-1", _MEMORY_INDEX_FILE_NAME))
    assert index is not None
    assert "# Memory Index" in index
    assert "- **arch.md**: architecture" in index
    assert "- **todo.md**" in index

    # A subsequent run injects the index as a user context message.
    session = AgentSession(session_id="ignored")
    context = SessionContext(session_id="ignored", input_messages=[])
    await provider.before_run(agent=None, session=session, context=context, state={})
    injected = context.context_messages.get(DEFAULT_FILE_MEMORY_SOURCE_ID, [])
    assert len(injected) == 1
    assert injected[0].role == "user"
    assert "arch.md" in injected[0].text


async def test_list_and_search_hide_internal_files() -> None:
    """Listing and search must hide description sidecars and the memory index."""
    store = InMemoryAgentFileStore()
    provider = FileMemoryProvider(store=store, scope="user-1")
    _, tools = await _prepare(provider)

    await tools["file_memory_write"].invoke(
        arguments={"file_name": "arch.md", "content": "architecture text", "description": "architecture"}
    )

    listed = json.loads(_text(await tools["file_memory_ls"].invoke()))
    assert [e["name"] for e in listed] == ["arch.md"]

    # The description text lives in an internal sidecar, so a regex matching it
    # must not return the sidecar (only the memory file itself).
    found = json.loads(_text(await tools["file_memory_grep"].invoke(arguments={"regex_pattern": "architecture"})))
    names = [e["file_name"] for e in found]
    assert "arch.md" in names
    assert all(not _is_internal_file(name) for name in names)


async def test_scope_isolates_memories_across_sessions() -> None:
    """Two sessions sharing a store should not see each other's memories by default."""
    store = InMemoryAgentFileStore()
    provider = FileMemoryProvider(store=store)

    _, tools_a = await _prepare(provider, session_id="session-a")
    await tools_a["file_memory_write"].invoke(arguments={"file_name": "a.md", "content": "from a"})

    _, tools_b = await _prepare(provider, session_id="session-b")
    listed_b = json.loads(_text(await tools_b["file_memory_ls"].invoke()))
    assert listed_b == []

    # The original session still sees its own memory.
    _, tools_a2 = await _prepare(provider, session_id="session-a")
    listed_a = json.loads(_text(await tools_a2["file_memory_ls"].invoke()))
    assert [e["name"] for e in listed_a] == ["a.md"]


async def test_explicit_scope_shares_memories_across_sessions() -> None:
    """An explicit scope groups memories regardless of session id."""
    store = InMemoryAgentFileStore()
    provider = FileMemoryProvider(store=store, scope="shared")

    _, tools_a = await _prepare(provider, session_id="session-a")
    await tools_a["file_memory_write"].invoke(arguments={"file_name": "shared.md", "content": "v"})

    _, tools_b = await _prepare(provider, session_id="session-b")
    listed_b = json.loads(_text(await tools_b["file_memory_ls"].invoke()))
    assert [e["name"] for e in listed_b] == ["shared.md"]


async def test_save_rejects_reserved_internal_names() -> None:
    """Saving a file whose name collides with an internal file must be rejected."""
    provider = FileMemoryProvider(store=InMemoryAgentFileStore())
    _, tools = await _prepare(provider)
    save = tools["file_memory_write"]

    reserved = await save.invoke(arguments={"file_name": _MEMORY_INDEX_FILE_NAME, "content": "x"})
    assert "reserved" in _text(reserved)

    sidecar = await save.invoke(arguments={"file_name": "notes_description.md", "content": "x"})
    assert "reserved" in _text(sidecar)


async def test_tools_surface_path_validation_errors() -> None:
    """Path traversal and rooted paths should be reported as tool messages, not raised."""
    provider = FileMemoryProvider(store=InMemoryAgentFileStore())
    _, tools = await _prepare(provider)

    bad_save = await tools["file_memory_write"].invoke(arguments={"file_name": "../escape.md", "content": "x"})
    assert "Could not write" in _text(bad_save)

    bad_read = await tools["file_memory_read"].invoke(arguments={"file_name": "/rooted.md"})
    assert "Could not read" in _text(bad_read)

    bad_delete = await tools["file_memory_delete"].invoke(arguments={"file_name": "../escape.md"})
    assert "Could not delete" in _text(bad_delete)


async def test_provider_accepts_custom_instructions() -> None:
    """Custom instructions override the default banner."""
    provider = FileMemoryProvider(store=InMemoryAgentFileStore(), instructions="custom memory banner")
    context, _ = await _prepare(provider)
    assert "custom memory banner" in context.instructions
    assert all(DEFAULT_FILE_MEMORY_INSTRUCTIONS not in chunk for chunk in context.instructions)


def test_file_memory_provider_is_experimental() -> None:
    """The provider should be marked experimental under the harness feature."""
    assert getattr(FileMemoryProvider, "__feature_stage__", None) == "experimental"


async def test_tools_reject_nested_paths() -> None:
    """Memory files must stay flat; nested names are rejected/undiscoverable."""
    store = InMemoryAgentFileStore()
    provider = FileMemoryProvider(store=store)
    _, tools = await _prepare(provider)

    saved = await tools["file_memory_write"].invoke(arguments={"file_name": "notes/plan.md", "content": "x"})
    assert "subdirectory" in _text(saved)
    # Nothing should have been written for the nested name.
    assert await store.list_children("") == []

    # Backslash separators are normalized to "/" and rejected the same way.
    saved_backslash = await tools["file_memory_write"].invoke(arguments={"file_name": "notes\\plan.md", "content": "x"})
    assert "subdirectory" in _text(saved_backslash)

    # Reading/deleting a nested name reports a clean "not found" message.
    read_back = await tools["file_memory_read"].invoke(arguments={"file_name": "notes/plan.md"})
    assert "not found" in _text(read_back)
    deleted = await tools["file_memory_delete"].invoke(arguments={"file_name": "notes/plan.md"})
    assert "not found" in _text(deleted)


async def test_index_caps_entries_at_max() -> None:
    """The rebuilt ``memories.md`` index lists at most ``_MAX_INDEX_ENTRIES`` files."""
    store = InMemoryAgentFileStore()
    provider = FileMemoryProvider(store=store, scope="user-1")
    _, tools = await _prepare(provider)
    save = tools["file_memory_write"]

    total = _MAX_INDEX_ENTRIES + 5
    for i in range(total):
        await save.invoke(arguments={"file_name": f"memory-{i:03d}.md", "content": "x"})

    index = await store.read(_combine_paths("user-1", _MEMORY_INDEX_FILE_NAME))
    assert index is not None
    entry_lines = [line for line in index.splitlines() if line.startswith("- ")]
    assert len(entry_lines) == _MAX_INDEX_ENTRIES


async def test_tools_surface_store_value_errors() -> None:
    """``ValueError`` raised by the store is returned as a tool message, not raised."""

    class _ValueErrorStore(InMemoryAgentFileStore):
        async def write(self, path: str, content: str, *, overwrite: bool = True) -> None:
            raise ValueError("boom-write")

        async def read(self, path: str) -> str | None:
            raise ValueError("boom-read")

        async def delete(self, path: str) -> bool:
            raise ValueError("boom-delete")

    provider = FileMemoryProvider(store=_ValueErrorStore())
    _, tools = await _prepare(provider)

    saved = await tools["file_memory_write"].invoke(arguments={"file_name": "plan.md", "content": "x"})
    assert "Could not write" in _text(saved) and "boom-write" in _text(saved)

    read_back = await tools["file_memory_read"].invoke(arguments={"file_name": "plan.md"})
    assert "Could not read" in _text(read_back) and "boom-read" in _text(read_back)

    deleted = await tools["file_memory_delete"].invoke(arguments={"file_name": "plan.md"})
    assert "Could not delete" in _text(deleted) and "boom-delete" in _text(deleted)


async def test_before_run_skips_injection_when_index_unreadable() -> None:
    """A failing index read must not crash the run; injection is simply skipped."""

    class _UnreadableIndexStore(InMemoryAgentFileStore):
        async def read(self, path: str) -> str | None:
            if path.endswith(_MEMORY_INDEX_FILE_NAME):
                raise ValueError("corrupt index")
            return await super().read(path)

    store = _UnreadableIndexStore()
    # Seed an index so before_run attempts to read it.
    await store.write(_combine_paths("user-1", _MEMORY_INDEX_FILE_NAME), "# Memory Index\n")
    provider = FileMemoryProvider(store=store, scope="user-1")

    session = AgentSession(session_id="s-1")
    context = SessionContext(session_id="s-1", input_messages=[])
    # Should not raise despite the unreadable index.
    await provider.before_run(agent=None, session=session, context=context, state={})
    assert context.context_messages.get(DEFAULT_FILE_MEMORY_SOURCE_ID, []) == []


async def test_search_propagates_invalid_regex() -> None:
    """An invalid regex from the model is surfaced as a raised error so it can retry."""
    provider = FileMemoryProvider(store=InMemoryAgentFileStore())
    _, tools = await _prepare(provider)

    with pytest.raises(re.error):
        await tools["file_memory_grep"].invoke(arguments={"regex_pattern": "[unclosed"})


async def test_memory_replace() -> None:
    """``file_memory_replace`` substitutes text and enforces match-count rules."""
    provider = FileMemoryProvider(store=InMemoryAgentFileStore())
    _, tools = await _prepare(provider)
    await tools["file_memory_write"].invoke(arguments={"file_name": "a.md", "content": "foo bar foo"})

    multi = await tools["file_memory_replace"].invoke(
        arguments={"file_name": "a.md", "old_string": "foo", "new_string": "baz"}
    )
    assert "2 times" in _text(multi)

    done = await tools["file_memory_replace"].invoke(
        arguments={"file_name": "a.md", "old_string": "foo", "new_string": "baz", "replace_all": True}
    )
    assert "2 occurrence" in _text(done)
    assert _text(await tools["file_memory_read"].invoke(arguments={"file_name": "a.md"})) == "baz bar baz"

    # Unique single occurrence with the default replace_all=False -> replaces exactly one.
    await tools["file_memory_write"].invoke(arguments={"file_name": "u.md", "content": "alpha beta gamma"})
    single = await tools["file_memory_replace"].invoke(
        arguments={"file_name": "u.md", "old_string": "beta", "new_string": "BETA"}
    )
    assert "1 occurrence" in _text(single)
    assert _text(await tools["file_memory_read"].invoke(arguments={"file_name": "u.md"})) == "alpha BETA gamma"

    # Internal files (the memories.md index and *_description.md sidecars) are reserved.
    reserved = await tools["file_memory_replace"].invoke(
        arguments={"file_name": "memories.md", "old_string": "x", "new_string": "y"}
    )
    assert "reserved for internal use" in _text(reserved)
    reserved_desc = await tools["file_memory_replace"].invoke(
        arguments={"file_name": "a_description.md", "old_string": "x", "new_string": "y"}
    )
    assert "reserved for internal use" in _text(reserved_desc)


async def test_memory_replace_lines() -> None:
    """``file_memory_replace_lines`` applies literal 1-based line edits and rejects bad input."""
    provider = FileMemoryProvider(store=InMemoryAgentFileStore())
    _, tools = await _prepare(provider)

    async def write(content: str) -> None:
        await tools["file_memory_write"].invoke(arguments={"file_name": "a.md", "content": content})

    async def current() -> str:
        return _text(await tools["file_memory_read"].invoke(arguments={"file_name": "a.md"}))

    # Literal replacement: the caller supplies the trailing newline.
    await write("one\ntwo\nthree")
    done = await tools["file_memory_replace_lines"].invoke(
        arguments={"file_name": "a.md", "edits": [{"line_number": 2, "new_line": "TWO\n"}]}
    )
    assert "1 line" in _text(done)
    assert await current() == "one\nTWO\nthree"

    # Empty new_line deletes a line; embedded newlines expand one line into several.
    await write("a\nb\nc\n")
    await tools["file_memory_replace_lines"].invoke(
        arguments={
            "file_name": "a.md",
            "edits": [{"line_number": 1, "new_line": ""}, {"line_number": 2, "new_line": "b1\nb2\n"}],
        }
    )
    assert await current() == "b1\nb2\nc\n"

    oor = await tools["file_memory_replace_lines"].invoke(
        arguments={"file_name": "a.md", "edits": [{"line_number": 9, "new_line": "x"}]}
    )
    assert "out of range" in _text(oor)

    # Internal files (the memories.md index and *_description.md sidecars) are reserved.
    reserved = await tools["file_memory_replace_lines"].invoke(
        arguments={"file_name": "memories.md", "edits": [{"line_number": 1, "new_line": "x"}]}
    )
    assert "reserved for internal use" in _text(reserved)

    # Empty edits list -> failure surfaced to the caller.
    await write("one\ntwo")
    empty = await tools["file_memory_replace_lines"].invoke(arguments={"file_name": "a.md", "edits": []})
    assert "At least one line edit" in _text(empty)

    # Duplicate line numbers -> failure surfaced to the caller.
    dup = await tools["file_memory_replace_lines"].invoke(
        arguments={
            "file_name": "a.md",
            "edits": [{"line_number": 1, "new_line": "x"}, {"line_number": 1, "new_line": "y"}],
        }
    )
    assert "Duplicate" in _text(dup)
