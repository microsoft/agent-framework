# Copyright (c) Microsoft. All rights reserved.

"""Private filesystem security helpers."""

from __future__ import annotations

import hashlib
import stat
from base64 import b32encode
from pathlib import Path

_WINDOWS_RESERVED_FILE_STEMS: frozenset[str] = frozenset({
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
    "COM¹",
    "COM²",
    "COM³",
    "LPT¹",
    "LPT²",
    "LPT³",
})

_MAX_ENCODED_STORAGE_KEY_SEGMENT_LENGTH = 180
_DIGEST_SEGMENT_MARKER = "sha256-"


def _is_link_or_reparse_point(path: Path) -> bool:  # pyright: ignore[reportUnusedFunction]
    """Return whether ``path`` is a symbolic link, junction, or other reparse point."""
    path_stat = path.lstat()
    if stat.S_ISLNK(path_stat.st_mode):
        return True

    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True

    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    return bool(reparse_attribute and file_attributes & reparse_attribute)


def _is_literal_storage_key_segment_safe(value: str) -> bool:
    """Return whether an opaque identifier can be used verbatim as one path segment.

    The predicate is deliberately conservative because the result is used as a
    security boundary (see :func:`_storage_key_segment`). Only *lowercase* ASCII
    alphanumerics and ``.``/``_``/``-`` are accepted, so a literal segment can
    never be folded onto a different identifier by the filesystem:

    * Rejecting non-ASCII avoids Unicode normalization folding (macOS APFS and
      HFS+ map the NFD and NFC forms of the same text onto one directory entry).
    * Rejecting uppercase avoids case folding (NTFS and APFS are case-insensitive
      by default, so ``A`` and ``a`` would be one directory entry). Uppercase
      values are encoded rather than lowercased, because lowercasing ``A`` would
      collide with a genuine ``a``.

    Values that are not literal-safe are encoded rather than rejected.
    """
    if (
        not value
        or value.startswith(".")
        or value.endswith((" ", "."))
        or value.split(".", maxsplit=1)[0].upper() in _WINDOWS_RESERVED_FILE_STEMS
    ):
        return False
    if any(ord(character) < 32 for character in value):
        return False
    return all(
        character.isascii() and ((character.isalnum() and not character.isupper()) or character in "._-")
        for character in value
    )


def _storage_key_segment(value: str, *, encoded_prefix: str) -> str:  # pyright: ignore[reportUnusedFunction]
    """Return a filesystem-safe path segment for an opaque identifier.

    This is the single derivation used everywhere an identifier that participates
    in an isolation boundary (a session ID, an owner ID, a memory scope) is turned
    into a storage location. Callers must not pre-normalize the value: a general
    path canonicalizer is lossy, and identifiers that differ only in separators or
    surrounding whitespace would then share one storage namespace.

    The derivation has three branches:

    * Literal-safe values are returned verbatim, so on-disk layouts stay readable.
    * Everything else is encoded under ``encoded_prefix`` using lowercase base32.
      This branch is **injective**: base32 is exactly reversible, and its alphabet
      (``a``-``z`` and ``2``-``7``) is case-stable, so the mapping stays one-to-one
      even on a case-insensitive filesystem. The literal and encoded namespaces
      cannot overlap because :func:`_is_literal_storage_key_segment_safe` rejects
      every value starting with ``~``, which each ``encoded_prefix`` begins with.
    * Past :data:`_MAX_ENCODED_STORAGE_KEY_SEGMENT_LENGTH` the encoding is replaced
      by a SHA-256 digest so the segment stays within filesystem name limits. This
      branch maps an unbounded input space onto 256 bits, so it is
      **collision-resistant** rather than injective: distinct identifiers sharing a
      namespace requires finding a SHA-256 collision.

    Args:
        value: The opaque identifier to convert.

    Keyword Args:
        encoded_prefix: Component-specific prefix applied to encoded values, so
            that two components encoding the same identifier stay distinguishable.
            Must start with ``~`` to stay outside the literal namespace.

    Returns:
        A single path segment containing no path separators.
    """
    if _is_literal_storage_key_segment_safe(value):
        return value
    encoded_value = b32encode(value.encode("utf-8")).decode("ascii").rstrip("=").lower()
    encoded_segment = f"{encoded_prefix}{encoded_value}"
    if len(encoded_segment) <= _MAX_ENCODED_STORAGE_KEY_SEGMENT_LENGTH:
        return encoded_segment
    # ``-`` is outside the base32 alphabet, so a digest segment can never collide
    # with the encoding of some other (shorter) identifier.
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"{encoded_prefix}{_DIGEST_SEGMENT_MARKER}{digest}"
