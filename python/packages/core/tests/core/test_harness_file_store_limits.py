# Copyright (c) Microsoft. All rights reserved.

"""Behavioral coverage for opt-in file-store capacity limits."""

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from agent_framework import AgentFileStore, FileSystemAgentFileStore, InMemoryAgentFileStore


def _store(kind: str, directory: Path, **limits: Any) -> AgentFileStore:
    """Exercise the same capacity contract through either backing implementation."""
    return InMemoryAgentFileStore(**limits) if kind == "memory" else FileSystemAgentFileStore(directory, **limits)


@pytest.mark.parametrize("kind", ["memory", "filesystem"])
async def test_file_size_limit_counts_utf8_and_preserves_previous_content(kind: str, tmp_path: Path) -> None:
    store = _store(kind, tmp_path, max_file_bytes=4)
    await store.write("notes.md", "old")
    with pytest.raises(ValueError, match="max_file_bytes"):
        await store.write("notes.md", "你好")
    assert await store.read("notes.md") == "old"


@pytest.mark.parametrize("kind", ["memory", "filesystem"])
async def test_store_limits_account_for_overwrite_delete_and_nested_files(kind: str, tmp_path: Path) -> None:
    store = _store(kind, tmp_path, max_files=2, max_total_bytes=6)
    await store.write("nested/first.txt", "abc")
    await store.write("second.txt", "def")
    with pytest.raises(ValueError, match="max_files"):
        await store.write("third.txt", "")
    with pytest.raises(ValueError, match="max_total_bytes"):
        await store.write("second.txt", "defg")
    assert await store.read("second.txt") == "def"
    await store.write("nested/first.txt", "a")
    await store.write("second.txt", "defgh")
    await store.delete("nested/first.txt")
    await store.write("third.txt", "x")
    assert await store.read("third.txt") == "x"


async def test_filesystem_limits_include_existing_files_and_survive_new_instances(tmp_path: Path) -> None:
    (tmp_path / "existing.txt").write_text("abc", encoding="utf-8")
    store = FileSystemAgentFileStore(tmp_path, max_files=1, max_total_bytes=3)
    with pytest.raises(ValueError, match="max_files"):
        await store.write("new.txt", "x")
    other = FileSystemAgentFileStore(tmp_path, max_total_bytes=3)
    with pytest.raises(ValueError, match="max_total_bytes"):
        await other.write("existing.txt", "abcd")
    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "abc"


@pytest.mark.parametrize("kind", ["memory", "filesystem"])
@pytest.mark.parametrize("name", ["max_file_bytes", "max_files", "max_total_bytes"])
@pytest.mark.parametrize("invalid", [0, -1, True, 1.5, "4"])
def test_explicit_invalid_limits_fail_without_creating_storage(
    kind: str, name: str, invalid: Any, tmp_path: Path
) -> None:
    root = tmp_path / "uncreated"
    with pytest.raises(ValueError, match=name):
        _store(kind, root, **{name: invalid})
    assert not root.exists()


async def test_unconfigured_filesystem_store_keeps_original_paths_and_metadata_behavior(tmp_path: Path) -> None:
    root = tmp_path / "uncreated"
    store = FileSystemAgentFileStore(root)
    assert not root.exists()
    await store.write(".agent-framework-quota.lock", "existing application data")
    assert await store.read(".agent-framework-quota.lock") == "existing application data"
    assert [entry.name for entry in await store.list_children()] == [".agent-framework-quota.lock"]


@pytest.mark.parametrize("kind", ["memory", "filesystem"])
async def test_exclusive_create_keeps_file_exists_error_with_limits(kind: str, tmp_path: Path) -> None:
    store = _store(kind, tmp_path, max_file_bytes=3, max_files=1)
    await store.write("first.txt", "abc")
    with pytest.raises(FileExistsError):
        await store.write("first.txt", "oversized", overwrite=False)
    assert await store.read("first.txt") == "abc"


@pytest.mark.parametrize("kind", ["memory", "filesystem"])
async def test_concurrent_writes_cannot_oversubscribe_root(kind: str, tmp_path: Path) -> None:
    shared = _store(kind, tmp_path, max_files=1, max_total_bytes=3)
    stores = (
        [shared] * 12
        if kind == "memory"
        else [FileSystemAgentFileStore(tmp_path, max_files=1, max_total_bytes=3) for _ in range(12)]
    )
    outcomes = await asyncio.gather(
        *(store.write(f"file-{n}.txt", "abc") for n, store in enumerate(stores)), return_exceptions=True
    )
    assert sum(result is None for result in outcomes) == 1
    assert all(result is None or isinstance(result, ValueError) for result in outcomes)
    entries = await shared.list_children()
    assert len(entries) == 1
    assert await shared.read(entries[0].name) == "abc"


async def test_separate_roots_have_independent_capacity(tmp_path: Path) -> None:
    first = FileSystemAgentFileStore(tmp_path / "first", max_files=1, max_total_bytes=3)
    second = FileSystemAgentFileStore(tmp_path / "second", max_files=1, max_total_bytes=3)
    await asyncio.gather(first.write("note.txt", "abc"), second.write("note.txt", "def"))
    assert await first.read("note.txt") == "abc"
    assert await second.read("note.txt") == "def"


async def test_read_limit_preserves_oversized_existing_file_and_hides_identity(tmp_path: Path) -> None:
    root = tmp_path / "private-user-identity"
    root.mkdir()
    (root / "note.txt").write_text("abcdef", encoding="utf-8")
    store = FileSystemAgentFileStore(root, max_file_bytes=4)
    with pytest.raises(ValueError, match="max_file_bytes") as error:
        await store.read("note.txt")
    assert "private-user-identity" not in str(error.value)
    assert (root / "note.txt").read_text(encoding="utf-8") == "abcdef"
    assert not (root / ".agent-framework-quota.lock").exists()


async def test_quota_metadata_is_hidden_and_cannot_replace_existing_data(tmp_path: Path) -> None:
    store = FileSystemAgentFileStore(tmp_path, max_files=1)
    await store.write("notes.txt", "hello")
    assert [entry.name for entry in await store.list_children()] == ["notes.txt"]
    assert not await store.file_exists(".agent-framework-quota.lock")
    for operation in (store.read, store.delete):
        with pytest.raises(ValueError, match="reserved"):
            await operation(".agent-framework-quota.lock")
    with pytest.raises(ValueError, match="reserved"):
        await store.write(".agent-framework-quota.lock", "replacement")
    assert [item.file_name for item in await store.search("", "hello")] == ["notes.txt"]

    other_root = tmp_path / "legacy"
    other_root.mkdir()
    lock_path = other_root / ".agent-framework-quota.lock"
    lock_path.write_text("application data", encoding="utf-8")
    other = FileSystemAgentFileStore(other_root, max_files=2)
    with pytest.raises(ValueError, match="conflicts"):
        await other.write("note.txt", "x")
    assert lock_path.read_text(encoding="utf-8") == "application data"


async def test_filesystem_capacity_is_shared_between_processes(tmp_path: Path) -> None:
    script = """import asyncio, sys
from agent_framework import FileSystemAgentFileStore
store = FileSystemAgentFileStore(sys.argv[1], max_files=1, max_total_bytes=3)
print('ready', flush=True)
sys.stdin.readline()
try:
    asyncio.run(store.write(sys.argv[2], 'abc'))
    print('written', flush=True)
except ValueError:
    print('refused', flush=True)
"""
    processes = [
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            str(tmp_path),
            f"child-{n}.txt",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        for n in range(2)
    ]
    try:
        for process in processes:
            assert process.stdout is not None
            assert await asyncio.wait_for(process.stdout.readline(), 20) == b"ready\n"
        for process in processes:
            assert process.stdin is not None
            process.stdin.write(b"go\n")
            await process.stdin.drain()
            process.stdin.close()
        results = await asyncio.gather(*(asyncio.wait_for(p.communicate(), 20) for p in processes))
        assert sorted(out.decode().strip() for out, _ in results) == ["refused", "written"]
        assert all(process.returncode == 0 for process in processes)
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
            await process.wait()


async def test_search_reports_configured_read_quota_instead_of_empty_matches(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("matching", encoding="utf-8")
    store = FileSystemAgentFileStore(tmp_path, max_file_bytes=3)
    with pytest.raises(ValueError, match="max_file_bytes"):
        await store.search("", "matching")
