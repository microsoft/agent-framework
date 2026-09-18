# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import ast
from pathlib import Path

import agent_framework


def _stub_all() -> set[str]:
    stub_path = Path(agent_framework.__file__).with_suffix(".pyi")
    module = ast.parse(stub_path.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    return set(ast.literal_eval(node.value))
    raise AssertionError("__all__ not found in agent_framework root stub")


def test_root_all_matches_stub_all() -> None:
    assert set(agent_framework.__all__) == _stub_all()


def test_root_star_import_loads_representative_symbols() -> None:
    namespace: dict[str, object] = {}
    exec("from agent_framework import *", namespace)

    assert namespace["Agent"] is agent_framework.Agent
    assert namespace["Message"] is agent_framework.Message
    assert namespace["tool"] is agent_framework.tool
    assert namespace["FileStoreEntry"] is agent_framework.FileStoreEntry
    assert namespace["SkillsSourceContext"] is agent_framework.SkillsSourceContext


def test_root_from_import_representative_symbols() -> None:
    from agent_framework import Agent, FileStoreEntry, Message, SkillsSourceContext, tool

    assert Agent is agent_framework.Agent
    assert Message is agent_framework.Message
    assert tool is agent_framework.tool
    assert FileStoreEntry is agent_framework.FileStoreEntry
    assert SkillsSourceContext is agent_framework.SkillsSourceContext
