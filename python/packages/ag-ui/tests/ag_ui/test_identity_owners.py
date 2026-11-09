# Copyright (c) Microsoft. All rights reserved.

"""Tests of the identity-keyed owner registry that AG-UI uses to bind executors and sessions to a scope."""

from __future__ import annotations

import gc
import weakref

from agent_framework import AgentSession

from agent_framework_ag_ui._session_ownership import IdentityOwners


def test_identity_owners_find_an_object_by_identity() -> None:
    owners = IdentityOwners()
    first, second = AgentSession(), AgentSession()

    owners.bind(first, "scope-a")

    assert owners.owner_of(first, None) == "scope-a"
    assert owners.owner_of(second, None) is None


def test_identity_owners_forget_an_object_when_it_is_collected() -> None:
    owners = IdentityOwners()
    subject = AgentSession()
    owners.bind(subject, "scope-a")
    assert len(owners) == 1

    del subject
    gc.collect()

    assert len(owners) == 0


def test_identity_owners_do_not_keep_an_object_alive() -> None:
    owners = IdentityOwners()
    subject = AgentSession()
    reference = weakref.ref(subject)
    owners.bind(subject, "scope-a")

    del subject
    gc.collect()

    assert reference() is None


def test_identity_owners_rebinding_keeps_one_entry_with_the_latest_owner() -> None:
    owners = IdentityOwners()
    subject = AgentSession()

    owners.bind(subject, "scope-a")
    owners.bind(subject, "scope-b")

    assert len(owners) == 1
    assert owners.owner_of(subject, None) == "scope-b"


def test_identity_owners_ignore_an_entry_that_belongs_to_another_object() -> None:
    owners = IdentityOwners()
    first, second = AgentSession(), AgentSession()
    owners.bind(first, "scope-a")
    # Move the entry of `first` under the key of `second`, as if `second` had reused the identity of a dead object.
    owners._entries[id(second)] = owners._entries.pop(id(first))  # pyright: ignore[reportPrivateUsage]

    assert owners.owner_of(second, None) is None


def test_identity_owners_replace_an_entry_that_belongs_to_another_object() -> None:
    owners = IdentityOwners()
    first, second = AgentSession(), AgentSession()
    owners.bind(first, "scope-a")
    owners._entries[id(second)] = owners._entries.pop(id(first))  # pyright: ignore[reportPrivateUsage]

    owners.bind(second, "scope-b")

    assert len(owners) == 1
    assert owners.owner_of(second, None) == "scope-b"


def test_identity_owners_obsolete_cleanup_keeps_the_entry_of_a_newer_object() -> None:
    owners = IdentityOwners()
    old, new = AgentSession(), AgentSession()
    owners.bind(old, "scope-a")
    # Keep the cleanup of `old` alive so that it runs when `old` dies, then hand its key to `new`.
    old_reference = owners._entries[id(old)][0]  # pyright: ignore[reportPrivateUsage]
    owners._entries[id(old)] = (weakref.ref(new), "scope-b")  # pyright: ignore[reportPrivateUsage]

    del old
    gc.collect()

    assert old_reference() is None
    assert len(owners) == 1
