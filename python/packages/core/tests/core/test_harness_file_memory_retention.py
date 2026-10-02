# Copyright (c) Microsoft. All rights reserved.

"""Persistence and failure contracts for opt-in file-memory lifecycle management."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agent_framework import (
    AgentSession,
    FileMemoryProvider,
    FileMemoryRetentionManager,
    FileSystemAgentFileStore,
)
from agent_framework._sessions import SessionContext


async def _prepare(provider: FileMemoryProvider) -> tuple[SessionContext, dict[str, Any]]:
    context = SessionContext(session_id="conversation", input_messages=[])
    await provider.before_run(agent=None, session=AgentSession(session_id="conversation"), context=context, state={})
    return context, {tool.name: tool for tool in context.tools}


async def _call(tools: dict[str, Any], name: str, **arguments: object) -> str:
    result = await tools[name].invoke(arguments=arguments)
    return str(result[0].text or "")


async def test_retention_refreshes_read_and_hides_expiry_on_every_surface(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    provider = FileMemoryProvider(store, retention=manager)
    _, tools = await _prepare(provider)
    assert "written" in await _call(tools, "file_memory_write", file_name="notes.md", content="hello")
    now[0] = 109
    assert await _call(tools, "file_memory_read", file_name="notes.md") == "hello"
    now[0] = 118
    assert await manager.collect() == 0
    now[0] = 119
    context, tools = await _prepare(provider)
    assert "not found" in await _call(tools, "file_memory_read", file_name="notes.md")
    assert await _call(tools, "file_memory_ls") == "[]"
    assert await _call(tools, "file_memory_grep", regex_pattern="hello") == "[]"
    assert not context.context_messages
    assert (store.root_path / "conversation/notes.md").exists()
    assert await manager.collect() == 1
    assert not (store.root_path / "conversation/notes.md").exists()


async def test_old_memory_without_metadata_is_not_adopted_by_read_or_gc(tmp_path: Path) -> None:
    store = FileSystemAgentFileStore(tmp_path / "owner")
    await store.write("conversation/legacy.md", "preserve")
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=1)
    manager._now = lambda: 1000.0
    provider = FileMemoryProvider(store, retention=manager)
    _, tools = await _prepare(provider)
    assert await _call(tools, "file_memory_read", file_name="legacy.md") == "preserve"
    assert await manager.collect() == 0
    assert await store.read("conversation/legacy.md") == "preserve"
    for state in (tmp_path / ".retention").glob("*.json"):
        assert "legacy.md" not in state.read_text()


async def test_expiry_preserves_description_still_referenced_by_another_memory(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    provider = FileMemoryProvider(store, retention=manager)
    _, tools = await _prepare(provider)
    await _call(tools, "file_memory_write", file_name="notes.md", content="first", description="shared")
    now[0] = 105
    await _call(tools, "file_memory_write", file_name="notes.txt", content="second", description="shared")
    now[0] = 111
    assert await manager.collect() == 1
    assert await store.read("conversation/notes_description.md") == "shared"
    assert "notes.txt" in (await store.read("conversation/memories.md") or "")
    now[0] = 116
    assert await manager.collect() == 1
    assert await store.read("conversation/notes_description.md") is None


async def test_active_request_protects_storage_and_visibility_past_deadline(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    provider = FileMemoryProvider(store, retention=manager)
    _, tools = await _prepare(provider)
    await _call(tools, "file_memory_write", file_name="notes.md", content="hello")
    now[0] = 109
    async with provider.protect():
        now[0] = 120
        assert await manager.collect() == 0
        assert await _call(tools, "file_memory_read", file_name="notes.md") == "hello"
    now[0] = 131
    assert await manager.collect() == 1


async def test_disable_resume_and_restart_have_distinct_persistent_behavior(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    provider = FileMemoryProvider(store, retention=manager)
    _, tools = await _prepare(provider)
    await _call(tools, "file_memory_write", file_name="notes.md", content="hello")
    now[0] = 105
    await manager.set_retention(None)
    manifests = list((tmp_path / ".retention").glob("*.json"))
    manifest = next(path for path in manifests if path.name != "policy.json")
    before = manifest.read_bytes()
    now[0] = 200
    assert await _call(tools, "file_memory_read", file_name="notes.md") == "hello"
    assert await manager.collect() == 0
    assert manifest.read_bytes() == before

    # A restarted worker reads the durable disabled policy even with an initial TTL.
    restarted = FileMemoryRetentionManager(tmp_path, retention_seconds=999)
    restarted._now = lambda: now[0]
    assert await restarted.collect() == 0
    assert restarted.retention_seconds is None

    # An explicit resume grants ten complete seconds, visible to other workers.
    await restarted.set_retention(10)
    policy = json.loads((tmp_path / ".retention/policy.json").read_text())
    assert policy["resumed_expires_at"] == 210
    assert policy["generation"] == 1
    now[0] = 209
    assert await manager.collect() == 0
    await restarted.set_retention(10)
    assert json.loads((tmp_path / ".retention/policy.json").read_text()) == policy
    now[0] = 210
    assert await manager.collect() == 1


async def test_multiple_resumes_and_successful_use_keep_individual_deadlines(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="hello")
    await manager.set_retention(None)
    now[0] = 200
    await manager.set_retention(10)
    now[0] = 205
    assert await _call(tools, "file_memory_read", file_name="notes.md") == "hello"
    now[0] = 211
    assert await manager.collect() == 0
    await manager.set_retention(None)
    now[0] = 300
    await manager.set_retention(20)
    assert json.loads((tmp_path / ".retention/policy.json").read_text())["generation"] == 2
    now[0] = 319
    assert await manager.collect() == 0
    now[0] = 320
    assert await manager.collect() == 1


async def test_positive_policy_change_does_not_recalculate_existing_deadlines(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    _, tools = await _prepare(FileMemoryProvider(FileSystemAgentFileStore(tmp_path / "owner"), retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="hello")
    await manager.set_retention(100)
    now[0] = 110
    assert await manager.collect() == 1


async def test_metadata_commit_failure_protects_actual_partial_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="old")
    original = manager._save

    def fail_commit(backing: FileSystemAgentFileStore, state: dict[str, Any], *, reclaim: bool = False) -> None:
        if any(record["state"] == "ready" for record in state["entries"].values()):
            raise OSError("injected failure")
        original(backing, state, reclaim=reclaim)

    monkeypatch.setattr(manager, "_save", fail_commit)
    result = await _call(tools, "file_memory_write", file_name="notes.md", content="new")
    assert "content may have changed" in result
    assert await store.read("conversation/notes.md") == "new"
    monkeypatch.setattr(manager, "_save", original)
    now[0] = 1000
    assert await manager.collect() == 0
    assert await store.read("conversation/notes.md") == "new"


async def test_registration_failure_preserves_previous_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="old")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("failure containing a private host path")

    monkeypatch.setattr(manager, "_save", fail)
    result = await _call(tools, "file_memory_write", file_name="notes.md", content="new")
    assert "private host path" not in result
    assert await store.read("conversation/notes.md") == "old"


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        '{"schema_version":99}',
        '{"schema_version":true}',
        '{"schema_version":1,"generation":0,"resumed_expires_at":null}',
    ],
)
async def test_unknown_or_corrupt_policy_is_preserved_and_cannot_delete_files(tmp_path: Path, payload: str) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=1)
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="preserve")
    path = tmp_path / ".retention/policy.json"
    path.write_text(payload)
    with pytest.raises(ValueError):
        await manager.collect()
    assert path.read_text() == payload
    assert await store.read("conversation/notes.md") == "preserve"


async def test_resume_does_not_adopt_unregistered_legacy_files(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=1)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    await store.write("conversation/legacy.md", "legacy")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="managed")
    await manager.set_retention(None)
    now[0] = 200
    await manager.set_retention(1)
    now[0] = 201
    assert await manager.collect() == 1
    assert await store.read("conversation/legacy.md") == "legacy"


def _manifest(directory: Path) -> Path:
    return next(path for path in (directory / ".retention").glob("*.json") if path.name != "policy.json")


async def test_listing_and_unmatched_search_do_not_renew_other_records(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="a.md", content="alpha")
    await _call(tools, "file_memory_write", file_name="b.md", content="beta")
    now[0] = 109
    assert "a.md" in await _call(tools, "file_memory_ls")
    assert await _call(tools, "file_memory_grep", regex_pattern="missing") == "[]"
    assert "a.md" in await _call(tools, "file_memory_grep", regex_pattern="alpha")
    now[0] = 110
    assert await manager.collect() == 1
    assert await store.read("conversation/a.md") == "alpha"
    assert await store.read("conversation/b.md") is None
    now[0] = 119
    assert await manager.collect() == 1


@pytest.mark.parametrize("corruption", ["version", "state", "missing_expiry", "null_expiry", "reference"])
async def test_invalid_manifest_preserves_original_bytes_and_body(tmp_path: Path, corruption: str) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=1)
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="preserve")
    path = _manifest(tmp_path)
    state = json.loads(path.read_text())
    record = next(iter(state["entries"].values()))
    if corruption == "version":
        state["schema_version"] = 99
    elif corruption == "state":
        record["state"] = "unknown"
    elif corruption == "missing_expiry":
        del record["expires_at"]
    elif corruption == "null_expiry":
        record["expires_at"] = None
    else:
        record["description"] = next(iter(state["entries"]))
    path.write_text(json.dumps(state))
    original = path.read_bytes()
    assert await manager.collect() == 0
    assert "Could not" in await _call(tools, "file_memory_write", file_name="notes.md", content="replace")
    assert await store.read("conversation/notes.md") == "preserve"
    assert path.read_bytes() == original


async def test_compatible_extension_fields_survive_overwrite(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    _, tools = await _prepare(FileMemoryProvider(FileSystemAgentFileStore(tmp_path / "owner"), retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="old")
    path = _manifest(tmp_path)
    state = json.loads(path.read_text())
    state["future_top_level"] = "keep"
    state["store_limits"]["future_limit"] = "keep"
    next(iter(state["entries"].values()))["future_field"] = "keep"
    path.write_text(json.dumps(state))
    assert "written" in await _call(tools, "file_memory_write", file_name="notes.md", content="new")
    after = json.loads(path.read_text())
    assert after["future_top_level"] == "keep"
    assert after["store_limits"]["future_limit"] == "keep"
    assert next(iter(after["entries"].values()))["future_field"] == "keep"


async def test_quota_refusal_before_body_write_does_not_leave_updating(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10, max_total_bytes=2000)
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    # A body alone fits, but registration plus its atomic-copy reserve does not.
    result = await _call(tools, "file_memory_write", file_name="notes.md", content="x" * 900)
    assert "shared_max_total_bytes" in result
    assert await store.read("conversation/notes.md") is None
    for path in (tmp_path / ".retention").glob("*.json"):
        if path.name != "policy.json":
            assert not json.loads(path.read_text())["entries"]


async def test_interrupted_update_requires_explicit_repair_before_expiry(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="inspect me")
    path = _manifest(tmp_path)
    state = json.loads(path.read_text())
    next(iter(state["entries"].values()))["state"] = "updating"
    path.write_text(json.dumps(state))
    now[0] = 1000
    assert await manager.collect() == 0
    assert await manager.repair(store) == 1
    assert await manager.repair(store) == 0
    now[0] = 1010
    assert await manager.collect() == 1


async def test_empty_unleased_scope_directories_are_reclaimed(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    store = FileSystemAgentFileStore(tmp_path / "owner")
    await store.create_directory("conversation")
    await _prepare(FileMemoryProvider(store, retention=manager))
    assert (store.root_path / "conversation").is_dir()
    assert await manager.collect() == 0
    assert not store.root_path.exists()


async def test_nested_quota_lock_name_is_an_ordinary_expiring_memory(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=1)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name=".agent-framework-quota.lock", content="ordinary")
    now[0] = 101
    assert await manager.collect() == 1
    assert await store.read("conversation/.agent-framework-quota.lock") is None


async def test_corrupt_policy_does_not_pin_request_protection(tmp_path: Path) -> None:
    from filelock import FileLock

    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    store = FileSystemAgentFileStore(tmp_path / "owner")
    async with manager._protect_store(store):
        token = next((tmp_path / ".retention/active").rglob("*.lock"))
        (tmp_path / ".retention/policy.json").write_text("{")
    assert not token.exists()
    with FileLock(tmp_path / ".retention/manager.lock", timeout=0, preserve_lock_file=True):
        pass


_WORKER = """
import asyncio, json, os, sys
from pathlib import Path
from agent_framework import AgentSession, FileMemoryProvider, FileMemoryRetentionManager, FileSystemAgentFileStore
from agent_framework._sessions import SessionContext
directory, mode, root, name, budget, phase = sys.argv[1:]
async def main():
    manager = FileMemoryRetentionManager(directory, retention_seconds=10,
        max_total_bytes=int(budget) if budget else None)
    manager._now = lambda: 100.0
    store = FileSystemAgentFileStore(Path(directory) / root)
    if mode == "lease":
        manager._now = lambda: 109.0
        async with manager._protect_store(store):
            print("ready", flush=True)
            await asyncio.to_thread(sys.stdin.readline)
        return
    provider = FileMemoryProvider(store, retention=manager)
    if mode in ("race_read", "race_gc") and phase == "no_hold":
        print("attempting", flush=True)
    context = SessionContext(session_id="conversation", input_messages=[])
    await provider.before_run(agent=None, session=AgentSession(session_id="conversation"), context=context, state={})
    tools = {tool.name: tool for tool in context.tools}
    if mode in ("race_read", "race_gc"):
        manager._now = lambda: 109.0 if mode == "race_read" else 111.0
        original = manager._save
        held = False
        def hold_after_save(backing, state, *, reclaim=False):
            nonlocal held
            original(backing, state, reclaim=reclaim)
            if not held and phase != "no_hold":
                held = True
                print("held", flush=True)
                sys.stdin.readline()
        manager._save = hold_after_save
        if mode == "race_gc":
            print(json.dumps(await manager.collect()), flush=True)
        else:
            response = await tools["file_memory_read"].invoke(arguments={"file_name": name})
            print(json.dumps(response[0].text), flush=True)
        return
    if mode == "write":
        print("ready", flush=True)
        await asyncio.to_thread(sys.stdin.readline)
        response = await tools["file_memory_write"].invoke(arguments={"file_name": name, "content": "x" * 600})
        print(json.dumps(response[0].text), flush=True)
        return
    if mode == "crash_write":
        original = manager._atomic
        def crash(path, payload, *, overwrite=True):
            if phase == "before_body" and path.name == name:
                os._exit(17)
            original(path, payload, overwrite=overwrite)
            if phase == "after_body" and path.name == name:
                os._exit(17)
        manager._atomic = crash
        await tools["file_memory_write"].invoke(arguments={"file_name": name, "content": "new"})
    if mode == "crash_gc":
        manager._now = lambda: 111.0
        original = manager._save
        def crash(backing, state, *, reclaim=False):
            original(backing, state, reclaim=reclaim)
            if any(record["state"] == "deleting" for record in state["entries"].values()):
                os._exit(17)
        manager._save = crash
        await manager.collect()
asyncio.run(main())
"""


async def _worker(
    directory: Path, mode: str, *, root: str = "owner", name: str = "notes.md", budget: str = "", phase: str = ""
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _WORKER,
        str(directory),
        mode,
        root,
        name,
        budget,
        phase,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def test_independent_processes_cannot_lose_manifest_entries(tmp_path: Path) -> None:
    processes = [await _worker(tmp_path, "write", name=f"{n}.md") for n in range(2)]
    try:
        for process in processes:
            assert process.stdout is not None and process.stdin is not None
            assert await asyncio.wait_for(process.stdout.readline(), 15) == b"ready\n"
        for process in processes:
            assert process.stdin is not None
            process.stdin.write(b"go\n")
            await process.stdin.drain()
        for process in processes:
            output, error = await asyncio.wait_for(process.communicate(), 15)
            assert process.returncode == 0, error.decode()
            assert "written" in json.loads(output)
        assert len(json.loads(_manifest(tmp_path).read_text())["entries"]) == 2
        assert (tmp_path / "owner/conversation/0.md").read_text() == "x" * 600
        assert (tmp_path / "owner/conversation/1.md").read_text() == "x" * 600
        assert "0.md" in (tmp_path / "owner/conversation/memories.md").read_text()
        assert "1.md" in (tmp_path / "owner/conversation/memories.md").read_text()
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
                await process.wait()


async def test_independent_roots_cannot_oversubscribe_shared_capacity(tmp_path: Path) -> None:
    processes = [await _worker(tmp_path, "write", root=f"owner-{n}", budget="1900") for n in range(2)]
    try:
        for process in processes:
            assert process.stdout is not None
            assert await asyncio.wait_for(process.stdout.readline(), 15) == b"ready\n"
        for process in processes:
            assert process.stdin is not None
            process.stdin.write(b"go\n")
            await process.stdin.drain()
        outcomes = []
        for process in processes:
            output, error = await asyncio.wait_for(process.communicate(), 15)
            assert process.returncode == 0, error.decode()
            outcomes.append(json.loads(output))
        assert sum("written" in outcome for outcome in outcomes) == 1
        assert (
            await asyncio.to_thread(lambda: sum(p.stat().st_size for p in tmp_path.rglob("*") if p.is_file())) <= 1900
        )
        assert await asyncio.to_thread(lambda: len(list(tmp_path.glob("*/conversation/notes.md")))) == 1
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
                await process.wait()


@pytest.mark.parametrize("phase", ["before_body", "after_body"])
async def test_process_death_during_write_preserves_atomic_body_and_protects_update(tmp_path: Path, phase: str) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    manager._now = lambda: 100.0
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="old")
    process = await _worker(tmp_path, "crash_write", phase=phase)
    _, error = await asyncio.wait_for(process.communicate(), 15)
    assert process.returncode == 17, error.decode()
    assert await store.read("conversation/notes.md") == ("old" if phase == "before_body" else "new")
    manager._now = lambda: 1000.0
    assert await manager.collect() == 0
    assert next(iter(json.loads(_manifest(tmp_path).read_text())["entries"].values()))["state"] == "updating"


async def test_process_death_releases_os_lease_for_later_gc(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="hello")
    process = await _worker(tmp_path, "lease")
    try:
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), 15) == b"ready\n"
        now[0] = 120
        assert await manager.collect() == 0
        process.kill()
        await asyncio.wait_for(process.wait(), 15)
        assert await manager.collect() == 1
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def test_interrupted_deletion_is_completed_idempotently_and_not_revived(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="hello", description="summary")
    process = await _worker(tmp_path, "crash_gc")
    _, error = await asyncio.wait_for(process.communicate(), 15)
    assert process.returncode == 17, error.decode()
    await manager.set_retention(None)
    now[0] = 200
    await manager.set_retention(10)
    assert "not found" in await _call(tools, "file_memory_read", file_name="notes.md")
    assert "Could not" in await _call(tools, "file_memory_write", file_name="notes.md", content="revive")
    assert await manager.collect() == 1
    assert await manager.collect() == 0
    assert await store.read("conversation/notes.md") is None
    assert await store.read("conversation/notes_description.md") is None


async def test_cancelled_operation_finishes_commit_before_releasing_manager_lock(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    store = FileSystemAgentFileStore(tmp_path / "owner")
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(view: Any) -> None:
        await view.write("conversation/notes.md", "complete")
        entered.set()
        await finish.wait()

    operation = asyncio.create_task(manager._run(store, write, purpose="write"))
    await asyncio.wait_for(entered.wait(), 5)
    operation.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(operation, 5)
    assert await store.read("conversation/notes.md") == "complete"
    assert next(iter(json.loads(_manifest(tmp_path).read_text())["entries"].values()))["state"] == "ready"


async def test_cancellation_during_registration_exit_releases_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collections.abc import AsyncGenerator
    from contextlib import asynccontextmanager

    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    store = FileSystemAgentFileStore(tmp_path / "owner")
    original = manager._locked

    @asynccontextmanager
    async def cancel_on_exit(*, load_policy: bool = True) -> AsyncGenerator[None]:
        async with original(load_policy=load_policy):
            yield
        if load_policy:
            raise asyncio.CancelledError

    monkeypatch.setattr(manager, "_locked", cancel_on_exit)
    with pytest.raises(asyncio.CancelledError):
        async with manager._protect_store(store):
            pytest.fail("registration should have been cancelled")
    assert not list((tmp_path / ".retention/active").rglob("*.lock"))


async def test_file_access_cannot_expose_manager_control_directory(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from agent_framework import FileAccessProvider

    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    provider = FileMemoryProvider(FileSystemAgentFileStore(tmp_path / "owner"), retention=manager)
    agent = SimpleNamespace(context_providers=[FileAccessProvider(FileSystemAgentFileStore(tmp_path))])
    with pytest.raises(ValueError, match="must not expose"):
        await provider.before_run(
            agent=agent,
            session=AgentSession(session_id="conversation"),
            context=SessionContext(session_id="conversation", input_messages=[]),
            state={},
        )
    assert not (tmp_path / ".retention").exists()


async def test_description_read_cannot_bypass_body_expiry(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    _, tools = await _prepare(FileMemoryProvider(FileSystemAgentFileStore(tmp_path / "owner"), retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="body", description="private summary")
    now[0] = 110
    assert "not found" in await _call(tools, "file_memory_read", file_name="notes_description.md")


def test_retention_rejects_unsupported_store_before_any_io(tmp_path: Path) -> None:
    from agent_framework import InMemoryAgentFileStore

    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    with pytest.raises(ValueError, match="requires FileSystemAgentFileStore"):
        FileMemoryProvider(InMemoryAgentFileStore(), retention=manager)
    assert not (tmp_path / ".retention").exists()


async def test_root_quota_pressure_reclaims_expired_records_before_refusing(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner", max_files=2)
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    assert "written" in await _call(tools, "file_memory_write", file_name="old.md", content="old")
    now[0] = 110
    assert "written" in await _call(tools, "file_memory_write", file_name="new.md", content="new")
    assert await store.read("conversation/old.md") is None
    assert await store.read("conversation/new.md") == "new"


@pytest.mark.parametrize("root_limit", [True, False])
async def test_gc_index_rebuild_cannot_bypass_capacity(tmp_path: Path, root_limit: bool) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10, max_total_bytes=None if root_limit else 2000)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner", max_file_bytes=200 if root_limit else None)
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="old.md", content="old")
    # Legacy files count toward storage but are not automatically given TTL.
    for n in range(10):
        await store.write(f"conversation/{n}.md", "legacy")
        await store.write(f"conversation/{n}_description.md", "d" * (150 if root_limit else 80))
    before = await store.read("conversation/memories.md")
    now[0] = 110
    assert before is not None
    assert await manager.collect() == 1
    assert await store.read("conversation/old.md") is None
    assert await store.read("conversation/memories.md") is None
    assert not json.loads(_manifest(tmp_path).read_text())["entries"]
    assert await manager.collect() == 0


@pytest.mark.parametrize("first", ["read", "gc"])
async def test_renew_and_gc_recheck_serialized_state_in_both_process_orders(tmp_path: Path, first: str) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    manager._now = lambda: 100.0
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="hello")
    primary = await _worker(tmp_path, f"race_{first}")
    secondary: asyncio.subprocess.Process | None = None
    try:
        assert primary.stdout is not None and primary.stdin is not None
        assert await asyncio.wait_for(primary.stdout.readline(), 15) == b"held\n"
        secondary = await _worker(tmp_path, "race_gc" if first == "read" else "race_read", phase="no_hold")
        assert secondary.stdout is not None
        assert await asyncio.wait_for(secondary.stdout.readline(), 15) == b"attempting\n"
        primary.stdin.write(b"release\n")
        await primary.stdin.drain()
        primary_output, primary_error = await asyncio.wait_for(primary.communicate(), 15)
        second_output, second_error = await asyncio.wait_for(secondary.communicate(), 15)
        assert primary.returncode == secondary.returncode == 0, (primary_error, second_error)
        if first == "read":
            assert json.loads(primary_output) == "hello"
            assert json.loads(second_output) == 0
            assert await store.read("conversation/notes.md") == "hello"
        else:
            assert json.loads(primary_output) == 1
            assert "not found" in json.loads(second_output)
            assert await store.read("conversation/notes.md") is None
    finally:
        for process in (primary, secondary):
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()


async def test_managed_limited_scope_does_not_leave_a_redundant_quota_lock(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=1)
    now = [100.0]
    manager._now = lambda: now[0]
    store = FileSystemAgentFileStore(tmp_path / "owner", max_file_bytes=1024, max_files=100, max_total_bytes=10000)
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    await _call(tools, "file_memory_write", file_name="notes.md", content="hello")
    assert not (store.root_path / ".agent-framework-quota.lock").exists()
    now[0] = 101
    assert await manager.collect() == 1
    assert not store.root_path.exists()
    assert (tmp_path / ".retention/manager.lock").exists()


async def test_process_death_before_data_creation_reclaims_orphan_request_token(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    process = await _worker(tmp_path, "lease", root="no-data")
    try:
        assert process.stdout is not None
        assert await asyncio.wait_for(process.stdout.readline(), 15) == b"ready\n"
        assert not (tmp_path / "no-data").exists()
        assert await manager.collect() == 0
        process.kill()
        await asyncio.wait_for(process.wait(), 15)
        assert await manager.collect() == 0
        assert not await asyncio.to_thread(lambda: list((tmp_path / ".retention/active").iterdir()))
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def test_custom_filesystem_backend_keeps_default_behavior_and_fails_retention_early(tmp_path: Path) -> None:
    class EncodedStore(FileSystemAgentFileStore):
        async def write(self, path: str, content: str, *, overwrite: bool = True) -> None:
            await super().write(path, "encoded:" + content, overwrite=overwrite)

        async def read(self, path: str) -> str | None:
            content = await super().read(path)
            return content.removeprefix("encoded:") if content is not None else None

    store = EncodedStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store))
    assert "written" in await _call(tools, "file_memory_write", file_name="notes.md", content="hello")
    assert (store.root_path / "conversation/notes.md").read_text() == "encoded:hello"
    manager = FileMemoryRetentionManager(tmp_path, retention_seconds=10)
    with pytest.raises(ValueError, match="without backend overrides"):
        FileMemoryProvider(store, retention=manager)
    assert not (tmp_path / ".retention").exists()


async def test_read_only_managed_requests_do_not_allocate_empty_data_directories(tmp_path: Path) -> None:
    manager = FileMemoryRetentionManager(tmp_path)
    store = FileSystemAgentFileStore(tmp_path / "owner")
    _, tools = await _prepare(FileMemoryProvider(store, retention=manager))
    assert await _call(tools, "file_memory_ls") == "[]"
    assert "not found" in await _call(tools, "file_memory_read", file_name="notes.md")
    assert not store.root_path.exists()
