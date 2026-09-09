# Copyright (c) Microsoft. All rights reserved.

"""Tests for the shared storage-key derivation in ``agent_framework._filesystem``.

Every component that maps a caller-controlled identifier (a session ID, an owner
ID, a memory scope) onto a storage location routes through
:func:`_storage_key_segment`. Its defining property is **injectivity**: two
byte-distinct identifiers must not produce the same segment, because the segment
is an isolation boundary. Only the digest fallback for pathologically long
values weakens this to collision resistance.

Injectivity is asserted **case-insensitively** throughout, because NTFS and APFS
are case-insensitive by default: two segments that differ only in case are one
directory entry there, which would reintroduce the collision this module exists
to prevent.
"""

from __future__ import annotations

import pytest

from agent_framework._filesystem import (  # pyright: ignore[reportPrivateUsage]
    _MAX_ENCODED_STORAGE_KEY_SEGMENT_LENGTH,
    _is_literal_storage_key_segment_safe,
    _storage_key_segment,
)

# Identifiers that a lossy path normalizer -- or a case-insensitive filesystem --
# would fold together. Shared with the per-provider parity tests so every
# component is held to the same contract.
COLLIDING_IDENTIFIERS: tuple[str, ...] = (
    "customer-42",
    "customer-42/",
    "customer-42//",
    "customer-42\\",
    "customer-42\\\\",
    "/customer-42",
    "//customer-42",
    " customer-42",
    "customer-42 ",
    " customer-42 ",
    "\tcustomer-42",
    "customer-42/.",
    "./customer-42",
    "customer-42/..",
    # Case variants: distinct identifiers that a case-insensitive filesystem
    # folds onto one directory entry unless they are encoded apart.
    "Customer-42",
    "CUSTOMER-42",
    "cUsToMeR-42",
    "a",
    "A",
)

UNSAFE_IDENTIFIERS: tuple[str, ...] = (
    "",
    ".",
    "..",
    ".hidden",
    "trailing.",
    "trailing ",
    "CON",
    "con",
    "CON.txt",
    "NUL.log",
    "LPT1",
    "COM\u00b9",
    "with\nnewline",
    "with\x00null",
    "caf\u00e9",  # NFC
    "cafe\u0301",  # NFD - byte-distinct from the NFC form above
    "\u65e5\u672c\u8a9e",
    "a/b",
    "a\\b",
    "a:b",
    "a*b",
    "a b",
    "UID1",  # uppercase is encoded, never lowercased
    "Session-1",
    "0198F0C5-1A2B-7C3D-8E4F-5A6B7C8D9E0F",
)

SAFE_IDENTIFIERS: tuple[str, ...] = (
    "customer-42",
    "customer_42",
    "customer.42",
    "0",
    "a",
    "0198f0c5-1a2b-7c3d-8e4f-5a6b7c8d9e0f",
    "session-1",
    "console",
    "cont",
    "x" * 200,
)


def test_safe_identifiers_are_used_verbatim() -> None:
    """An already-safe identifier keeps its literal folder name.

    This is what keeps typical deployments (lowercase UUIDs, slugs) from needing
    a data migration.
    """
    for value in SAFE_IDENTIFIERS:
        assert _is_literal_storage_key_segment_safe(value)
        assert _storage_key_segment(value, encoded_prefix="~scope-") == value


def test_unsafe_identifiers_are_encoded_not_rejected() -> None:
    for value in UNSAFE_IDENTIFIERS:
        assert not _is_literal_storage_key_segment_safe(value)
        segment = _storage_key_segment(value, encoded_prefix="~scope-")
        assert segment.startswith("~scope-")


def test_derivation_is_injective_over_colliding_identifiers() -> None:
    """The MSRC case: values a path normalizer folds together stay distinct."""
    segments = {value: _storage_key_segment(value, encoded_prefix="~scope-") for value in COLLIDING_IDENTIFIERS}
    assert len(set(segments.values())) == len(COLLIDING_IDENTIFIERS), segments


def test_derivation_is_injective_over_every_known_identifier() -> None:
    all_values = (*COLLIDING_IDENTIFIERS, *UNSAFE_IDENTIFIERS, *SAFE_IDENTIFIERS)
    unique_values = set(all_values)
    segments = {_storage_key_segment(value, encoded_prefix="~scope-") for value in unique_values}
    assert len(segments) == len(unique_values)


def test_derivation_is_injective_on_case_insensitive_filesystems() -> None:
    """Distinct identifiers must not fold together on NTFS or APFS.

    Comparing case-folded segments is the same check the filesystem performs
    when deciding whether two names are one directory entry.
    """
    all_values = (*COLLIDING_IDENTIFIERS, *UNSAFE_IDENTIFIERS, *SAFE_IDENTIFIERS)
    unique_values = set(all_values)
    folded = {_storage_key_segment(value, encoded_prefix="~scope-").lower() for value in unique_values}
    assert len(folded) == len(unique_values)


def test_uppercase_identifiers_are_encoded_rather_than_lowercased() -> None:
    """``A`` must not be stored as ``a``: that is a genuine other identifier."""
    assert _storage_key_segment("a", encoded_prefix="~scope-") == "a"
    upper = _storage_key_segment("A", encoded_prefix="~scope-")
    assert upper.startswith("~scope-")
    assert upper.lower() != "a"


def test_encoded_segments_use_a_case_stable_alphabet() -> None:
    """Lowercase base32 (``a``-``z``, ``2``-``7``) survives case folding intact."""
    alphabet = set("abcdefghijklmnopqrstuvwxyz234567")
    for value in (*COLLIDING_IDENTIFIERS, *UNSAFE_IDENTIFIERS):
        segment = _storage_key_segment(value, encoded_prefix="~scope-")
        if not segment.startswith("~scope-"):
            continue
        body = segment.removeprefix("~scope-")
        assert set(body) <= alphabet, (value, segment)
        assert body == body.lower()


def test_unicode_normalization_forms_do_not_collide() -> None:
    """NFC and NFD spellings are byte-distinct and must stay distinct.

    A literal non-ASCII folder name would be folded onto one directory entry by
    macOS APFS/HFS+, so non-ASCII values are always encoded.
    """
    nfc = _storage_key_segment("caf\u00e9", encoded_prefix="~scope-")
    nfd = _storage_key_segment("cafe\u0301", encoded_prefix="~scope-")
    assert nfc != nfd


def test_segments_never_contain_path_separators() -> None:
    for value in (*COLLIDING_IDENTIFIERS, *UNSAFE_IDENTIFIERS, *SAFE_IDENTIFIERS):
        segment = _storage_key_segment(value, encoded_prefix="~scope-")
        assert "/" not in segment
        assert "\\" not in segment


def test_literal_namespace_cannot_collide_with_encoded_namespace() -> None:
    """No literal-safe value can look like an encoded segment.

    ``~`` is outside the literal charset, so an attacker cannot pick a plain
    identifier that lands on some other identifier's encoded folder.
    """
    assert not _is_literal_storage_key_segment_safe("~scope-mn2xg5dpnvsxeljugixq")
    literal = _storage_key_segment("customer-42", encoded_prefix="~scope-")
    encoded = _storage_key_segment("customer-42/", encoded_prefix="~scope-")
    assert not literal.startswith("~")
    assert encoded.startswith("~")


def test_prefix_separates_components_for_the_same_identifier() -> None:
    """Two components encoding the same value stay in distinct folders."""
    value = "customer-42/"
    assert _storage_key_segment(value, encoded_prefix="~scope-") != _storage_key_segment(value, encoded_prefix="~todo-")


def test_long_identifiers_fall_back_to_a_digest_segment() -> None:
    long_value = "customer-42/" + "x" * 400
    segment = _storage_key_segment(long_value, encoded_prefix="~scope-")
    assert segment.startswith("~scope-sha256-")
    assert len(segment) <= _MAX_ENCODED_STORAGE_KEY_SEGMENT_LENGTH


def test_digest_segments_are_collision_resistant() -> None:
    """The digest branch is collision-resistant, not injective.

    SHA-256 maps an unbounded input space onto 256 bits, so distinct long
    identifiers sharing a namespace requires finding a SHA-256 collision.
    """
    first = _storage_key_segment("a" * 400, encoded_prefix="~scope-")
    second = _storage_key_segment("a" * 401, encoded_prefix="~scope-")
    assert first != second


def test_digest_marker_is_outside_the_encoded_alphabet() -> None:
    """A base32 encoding can never be mistaken for a digest segment.

    ``-`` is not a base32 character, so the two encoded forms occupy disjoint
    namespaces even though they share a prefix.
    """
    encoded = _storage_key_segment("customer-42/", encoded_prefix="~scope-")
    assert "-" not in encoded.removeprefix("~scope-")


@pytest.mark.parametrize("value", ["customer-42", "customer-42/", "caf\u00e9", "a" * 400])
def test_derivation_is_deterministic(value: str) -> None:
    assert _storage_key_segment(value, encoded_prefix="~scope-") == _storage_key_segment(
        value, encoded_prefix="~scope-"
    )
