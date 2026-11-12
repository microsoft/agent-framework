# Copyright (c) Microsoft. All rights reserved.

"""File-based memory harness provider backed by an ``AgentFileStore``.

:class:`FileMemoryProvider` gives an agent a session-scoped, file-based memory
system. Each memory is stored as an individual file with a meaningful name, and
large files can carry a companion description file — named after the whole
memory file name (``notes.md`` becomes ``notes.md._description.md``) — that
provides a short summary used for discovery. A ``memories.md`` index file is
maintained automatically and injected into the agent's context so the model
knows what memories already exist.

File access is mediated through the :class:`~agent_framework.AgentFileStore`
abstraction (shared with :class:`~agent_framework.FileAccessProvider`), so the
same in-memory, local-disk, or remote-blob backends can be reused here.

Unlike :class:`~agent_framework.FileAccessProvider`, which exposes a *shared*
store visible across sessions and agents, :class:`FileMemoryProvider` isolates
memories per session by default: every session writes under its own working
folder (derived from the session id). Pass an explicit ``scope`` to group
memories differently, for example by user id.

A ``scope`` (and the session id it defaults to) is treated as an **opaque
namespace key**, not as a path: it is mapped to exactly one storage folder by a
derivation that is injective for all but pathologically long values, so two
byte-distinct values cannot share a working folder. Applications that derive a
scope from an externally supplied value should still canonicalize and authorize
that value themselves; the mapping here is the storage-layer guarantee, not a
substitute for that check.

The provider exposes the following tools to the agent (registered on the
per-invocation :class:`~agent_framework.SessionContext` in
:meth:`FileMemoryProvider.before_run`):

* ``file_memory_write`` — Write a memory file (with an optional description).
* ``file_memory_read`` — Read the content of a memory file by name.
* ``file_memory_delete`` — Delete a memory file (and its description).
* ``file_memory_ls`` — List memory files with their descriptions.
* ``file_memory_grep`` — Search memory file contents with a regex.
* ``file_memory_replace`` — Replace a substring within a memory file.
* ``file_memory_replace_lines`` — Replace whole lines within a memory file.
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from collections.abc import Iterable
from typing import Annotated, Any

from pydantic import BaseModel, Field

from .._filesystem import _storage_key_segment  # pyright: ignore[reportPrivateUsage]
from .._sessions import AgentSession, ContextProvider, SessionContext
from .._tools import tool
from .._types import Message
from ._file_access import (
    AgentFileStore,
    FileStoreEntry,
    _apply_replace,  # pyright: ignore[reportPrivateUsage]
    _apply_replace_lines,  # pyright: ignore[reportPrivateUsage]
    _line_edits,  # pyright: ignore[reportPrivateUsage]
    _matches_glob,  # pyright: ignore[reportPrivateUsage]
    _normalize_relative_path,  # pyright: ignore[reportPrivateUsage]
    _store_write_lock,  # pyright: ignore[reportPrivateUsage]
)

logger = logging.getLogger(__name__)

DEFAULT_FILE_MEMORY_SOURCE_ID = "file_memory"

DEFAULT_FILE_MEMORY_INSTRUCTIONS = (
    "## File Based Memory\n"
    "You have access to a session-scoped, file-based memory system via the `file_memory_*` tools "
    "for storing and retrieving information across interactions. "
    "These files act as your working memory for the current session and are isolated from other sessions. "
    "Use these tools to store plans, memories, processing results, or downloaded data.\n\n"
    '- Use descriptive file names (e.g., "projectarchitecture.md", "userpreferences.md").\n'
    "- Include a description when writing a file to help with future discovery.\n"
    "- Before starting new tasks, use file_memory_ls and file_memory_grep to check for "
    "relevant existing memories to avoid duplicate work.\n"
    "- Keep memories up-to-date by overwriting files when information changes.\n"
    "- When you receive large amounts of data (e.g., downloaded web pages, API responses, research results), "
    "write them to files if they will be required later, so that they are not lost when older context is "
    "compacted or truncated. This ensures important data remains accessible across long-running sessions."
)


_DESCRIPTION_SUFFIX = "_description.md"
# New-format sidecars are ``<whole memory file name>._description.md``. The
# separating dot is what isolates the format: a *legacy* sidecar is
# ``<stem>_description.md`` where ``<stem>`` is the memory file name with its
# last extension removed, and a stem never ends in ``.`` (removing an extension
# always cuts at a dot). So ``<name>._description.md`` can never equal any
# legacy sidecar name, which makes the two namespaces disjoint by construction:
# an old sidecar can never be read as another memory's description.
_NEW_DESCRIPTION_SUFFIX = f".{_DESCRIPTION_SUFFIX}"
_MEMORY_INDEX_FILE_NAME = "memories.md"
_MAX_INDEX_ENTRIES = 50
# Common per-component filesystem name budget (bytes on ext4, APFS and NTFS).
# A sidecar must fit inside it so every valid memory file name keeps a writable
# companion; names too long to carry the suffix verbatim use a digest instead.
_MAX_DESCRIPTION_FILE_NAME_BYTES = 255
# Prefix for scope values that are not usable verbatim as a folder name. Kept
# distinct from the other harness prefixes so the same value under a different
# component never lands in the same directory.
_ENCODED_SCOPE_PREFIX = "~scope-"
# Namespace for description sidecars that cannot be spelled verbatim: memory
# names whose sidecar would exceed the name budget, plus names that could
# otherwise forge a digest sidecar. Digest names keep the description suffix so
# they stay internal and hidden from the agent.
_DIGEST_DESCRIPTION_PREFIX = "~memory-desc-"


def _is_reserved_digest_name(file_name: str) -> bool:
    """Return whether ``file_name`` belongs to the reserved digest namespace.

    The check runs on an NFKC-normalized, case-folded copy of the name so that
    every spelling a case-folding or Unicode-folding filesystem treats as the
    prefix is caught: ASCII case variants (``~MEMORY-DESC-``), Unicode case
    pairs (long s folding to ``s``) and NFKC compatibility forms (a fullwidth
    spelling of the prefix). Matching only ASCII lower-casing would
    let a short name alias a long name's digest sidecar on default APFS or
    NTFS, where writing the short name would overwrite the long name's
    description and deleting it would remove that description.
    """
    normalized = unicodedata.normalize("NFKC", file_name).casefold()
    return normalized.startswith(_DIGEST_DESCRIPTION_PREFIX)


def _requires_digest_sidecar(file_name: str) -> bool:
    """Return whether ``file_name`` must use the digest sidecar namespace.

    This is true when the verbatim sidecar would exceed the filesystem name
    budget, and when the name itself sits in the reserved digest namespace —
    otherwise a short name could be spelled so that its verbatim sidecar is
    exactly another name's digest sidecar, and the two would collide without
    any hash collision.
    """
    if _is_reserved_digest_name(file_name):
        return True
    return len(f"{file_name}{_NEW_DESCRIPTION_SUFFIX}".encode("utf-8")) > _MAX_DESCRIPTION_FILE_NAME_BYTES


def _description_file_name(file_name: str) -> str:
    """Return the companion description file name for ``file_name``.

    The suffix is appended to the *whole* memory file name after a separating
    dot, so ``notes.md`` becomes ``notes.md._description.md`` while ``notes``
    becomes ``notes._description.md``. Keeping the extension in the derivation
    makes the mapping injective — distinct memory files always get distinct
    sidecars — and the dot keeps the new names disjoint from every legacy
    ``<stem>_description.md`` name (see :data:`_NEW_DESCRIPTION_SUFFIX`).

    Names whose verbatim sidecar would not fit within
    :data:`_MAX_DESCRIPTION_FILE_NAME_BYTES`, and names in the reserved digest
    namespace, are derived from a SHA-256 digest instead. The caller is
    responsible for passing the backend's canonical stored file name, because
    on a case-folding store the digest must not depend on which spelling the
    caller used.
    """
    if _requires_digest_sidecar(file_name):
        digest = hashlib.sha256(file_name.encode("utf-8")).hexdigest()
        return f"{_DIGEST_DESCRIPTION_PREFIX}{digest}{_NEW_DESCRIPTION_SUFFIX}"
    return f"{file_name}{_NEW_DESCRIPTION_SUFFIX}"


def _legacy_description_file_name(file_name: str) -> str:
    """Return the pre-isolation description file name for ``file_name``.

    Sidecars written before format isolation replaced the original extension
    when one was present (``notes.md`` became ``notes_description.md``) and
    appended the suffix otherwise. This name is only ever read as a fallback,
    and only when :func:`_legacy_sidecar_is_unambiguous` says it can belong to
    exactly one existing memory file.
    """
    dot_index = file_name.rfind(".")
    if dot_index > 0:
        return f"{file_name[:dot_index]}{_DESCRIPTION_SUFFIX}"
    return f"{file_name}{_DESCRIPTION_SUFFIX}"


def _legacy_sidecar_is_unambiguous(file_name: str, existing_file_names: Iterable[str]) -> bool:
    """Return whether the legacy sidecar of ``file_name`` can only belong to it.

    Two memory files share a legacy sidecar exactly when they share a stem, so
    the sidecar is unambiguous when no other existing memory file maps to the
    same legacy name. Reading it anyway would hand one memory another's
    description; when it is ambiguous the description is left unread rather
    than guessed at.

    Stems are compared with :meth:`str.casefold` because a case-folding store
    (NTFS, APFS) treats ``Notes.md`` and ``notes.md`` as the same file and folds
    their legacy sidecars together too; folding in the conservative direction
    only ever suppresses a risky read, it never invents one.
    """
    dot_index = file_name.rfind(".")
    folded_file_name = file_name.casefold()
    stem = (file_name[:dot_index] if dot_index > 0 else file_name).casefold()
    for other in existing_file_names:
        if other.casefold() == folded_file_name:
            continue
        other_dot_index = other.rfind(".")
        other_stem = (other[:other_dot_index] if other_dot_index > 0 else other).casefold()
        if other_stem == stem:
            return False
    return True


async def _canonical_file_name(store: AgentFileStore, working_folder: str, file_name: str) -> str:
    """Return the name under which ``file_name`` is actually stored.

    Only consulted before hashing a digest sidecar: on a case-folding store the
    same memory can be addressed under several spellings, and hashing each
    spelling would scatter one description across several sidecars. A
    case-sensitive store keeps distinct spellings distinct because
    :meth:`~agent_framework.AgentFileStore.file_exists` answers for the exact
    name only, so a differently-cased name that does not exist yet keeps its own
    spelling instead of being collapsed onto its neighbour.

    The alias search folds with :meth:`str.lower`, mirroring the key function
    :class:`InMemoryAgentFileStore` itself uses, so an entry is only adopted
    when the store would treat it as the very same file.
    """
    entries = await store.list_children(working_folder)
    if any(entry.name == file_name for entry in entries):
        return file_name
    if not await store.file_exists(_combine_paths(working_folder, file_name)):
        return file_name
    lowered = file_name.lower()
    for entry in entries:
        if entry.name.lower() == lowered:
            return entry.name
    return file_name


def _is_internal_file(file_name: str) -> bool:
    """Return whether ``file_name`` is an internal file hidden from the agent.

    Internal files are the description sidecars and the ``memories.md`` index.
    """
    lowered = file_name.lower()
    return lowered.endswith(_DESCRIPTION_SUFFIX) or lowered == _MEMORY_INDEX_FILE_NAME


def _combine_paths(base_path: str, relative_path: str) -> str:
    """Join a working-folder path with a relative path using forward slashes."""
    if not base_path:
        return relative_path
    if not relative_path:
        return base_path
    return f"{base_path.rstrip('/')}/{relative_path.lstrip('/')}"


def _is_nested_path(normalized_file_name: str) -> bool:
    """Return whether a normalized file name points into a subdirectory.

    File memory is a flat, session-scoped space: every discovery surface
    (the ``memories.md`` index, ``file_memory_ls``, and non-recursive
    ``file_memory_grep``) only enumerates direct children of the
    working folder. A nested name such as ``"notes/plan.md"`` would therefore
    be written but never surface again, so such names are rejected up front.
    ``_normalize_relative_path`` already converts backslashes to forward
    slashes, so checking for ``/`` covers both separators.
    """
    return "/" in normalized_file_name


class _WriteFileInput(BaseModel):
    """Input schema for ``file_memory_write``."""

    file_name: Annotated[str, Field(description="Flat file name to write under; must not contain path separators.")]
    content: Annotated[str, Field(description="Full text content to write to the file.")]
    description: Annotated[
        str | None,
        Field(
            default=None,
            description="Optional summary used to aid future discovery; recommended for large files.",
        ),
    ] = None


class _ReadFileInput(BaseModel):
    """Input schema for ``file_memory_read``."""

    file_name: Annotated[str, Field(description="Name of the memory file to read.")]


class _DeleteFileInput(BaseModel):
    """Input schema for ``file_memory_delete``."""

    file_name: Annotated[str, Field(description="Name of the memory file to delete.")]


class _ListInput(BaseModel):
    """Input schema for ``file_memory_ls``."""

    glob_pattern: Annotated[
        str | None,
        Field(
            default=None,
            description='Optional glob (e.g. "*.md") matched against file names to filter the listing.',
        ),
    ] = None


class _ReplaceInput(BaseModel):
    """Input schema for ``file_memory_replace``."""

    file_name: Annotated[str, Field(description="Name of the memory file to modify.")]
    old_string: Annotated[str, Field(description="Substring to find and replace.")]
    new_string: Annotated[str, Field(description="Replacement text.")]
    replace_all: Annotated[
        bool,
        Field(
            default=False,
            description="When true, replace every occurrence; when false, fail unless exactly one occurrence exists.",
        ),
    ] = False


class _LineEdit(BaseModel):
    """A single literal line replacement for ``file_memory_replace_lines``."""

    line_number: Annotated[int, Field(description="1-based line number to replace.")]
    new_line: Annotated[
        str,
        Field(
            description=(
                "Literal replacement text for the line, including any trailing newline you want to keep "
                "(the editor does not add one). Set to an empty string to delete the line entirely, "
                "including its line break."
            )
        ),
    ]
    expected_line: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Optional: the text you believe is currently on that line, as reported by "
                "file_memory_grep. When supplied, the edit is rejected unless it matches, which "
                "catches an out-of-date line number or a file that changed since you looked. "
                "The trailing newline is ignored in the comparison."
            ),
        ),
    ] = None


class _ReplaceLinesInput(BaseModel):
    """Input schema for ``file_memory_replace_lines``."""

    file_name: Annotated[str, Field(description="Name of the memory file to modify.")]
    edits: Annotated[
        list[_LineEdit],
        Field(description="List of 1-based line numbers and their literal replacement text."),
    ]


class _SearchFilesInput(BaseModel):
    """Input schema for ``file_memory_grep``."""

    regex_pattern: Annotated[
        str,
        Field(description="Case-insensitive regex matched against file contents; 256 characters or fewer."),
    ]
    glob_pattern: Annotated[
        str | None,
        Field(
            default=None,
            description='Optional glob to filter which files are searched (e.g. "*.md", "research*").',
        ),
    ] = None


class FileMemoryProvider(ContextProvider):
    """Context provider that gives an agent session-scoped, file-based memory.

    The provider exposes the following tools to the agent via the per-invocation
    :class:`~agent_framework.SessionContext`:

    - ``file_memory_write`` — Write a memory file with an optional description.
    - ``file_memory_read`` — Read the content of a memory file by name.
    - ``file_memory_delete`` — Delete a memory file and its description.
    - ``file_memory_ls`` — List memory files with their descriptions.
    - ``file_memory_grep`` — Search memory file contents with a regex.
    - ``file_memory_replace`` — Replace a substring within a memory file.
    - ``file_memory_replace_lines`` — Replace whole lines within a memory file.

    Memories are isolated per session: each session reads and writes under a
    working folder derived from its session id. Pass an explicit ``scope`` to
    group memories differently (for example, per user id) across sessions.

    The scope (or session id) is an opaque namespace key, not a path. It is
    mapped to a single folder by a derivation that is injective for all but
    pathologically long values, so two byte-distinct values cannot share a
    working folder.
    """

    def __init__(
        self,
        store: AgentFileStore,
        *,
        source_id: str = DEFAULT_FILE_MEMORY_SOURCE_ID,
        scope: str | None = None,
        instructions: str | None = None,
    ) -> None:
        """Initialize the file memory provider.

        Args:
            store: The file store implementation used for storage operations.

        Keyword Args:
            source_id: Unique source ID for the provider.
            scope: The namespace that logically groups and isolates memories
                (for example, a user ID). Used as the working folder within the
                store. When ``None`` (the default), the active session's
                ``session_id`` is used, isolating memories per session. The
                value is treated as an opaque key rather than a path: it is
                mapped onto exactly one folder, so a multi-segment value
                such as ``"tenants/alice"`` becomes a single encoded folder
                instead of a nested directory.
            instructions: Optional instruction override. When ``None`` the
                default file-memory instructions are used.
        """
        super().__init__(source_id)
        self.store = store
        self.scope = scope
        self.instructions = instructions or DEFAULT_FILE_MEMORY_INSTRUCTIONS

    def _resolve_working_folder(self, context: SessionContext) -> str:
        """Resolve the working folder for the current invocation.

        Uses the configured ``scope`` when set, otherwise the session id. The
        value is an opaque namespace key, not a path: it is mapped to exactly
        one folder name by :func:`~agent_framework._filesystem._storage_key_segment`.
        That derivation is injective except for pathologically long values,
        which fall back to a collision-resistant digest. Two byte-distinct
        scopes or session ids therefore do not resolve to the same working
        folder, so a caller authorized for one of them cannot reach another's
        memories.

        Raises:
            ValueError: When neither ``scope`` nor the session id yields a
                namespace. Without one there is nothing to isolate on, and
                falling back to the store root would expose every other scope.
        """
        raw_scope = self.scope or context.session_id or ""
        if not raw_scope:
            raise ValueError(
                "FileMemoryProvider requires a memory scope: pass an explicit 'scope' or run with a session "
                "that has a 'session_id'. Without one, memories cannot be isolated from other scopes."
            )
        return _storage_key_segment(raw_scope, encoded_prefix=_ENCODED_SCOPE_PREFIX)

    async def _memory_file_names(self, working_folder: str) -> set[str]:
        """Return the agent-visible memory file names in ``working_folder``."""
        entries = await self.store.list_children(working_folder)
        return {
            entry.name for entry in entries if entry.type == FileStoreEntry.FILE and not _is_internal_file(entry.name)
        }

    async def _sidecar_path(self, working_folder: str, file_name: str) -> str:
        """Return the store path of the new-format description sidecar for ``file_name``.

        Digest names are derived from the backend's canonical stored file name
        so a case-folding store cannot scatter one description across several
        sidecars; verbatim names need no resolution because the store folds them
        on its own.
        """
        if _requires_digest_sidecar(file_name):
            file_name = await _canonical_file_name(self.store, working_folder, file_name)
        return _combine_paths(working_folder, _description_file_name(file_name))

    def _legacy_sidecar_path(self, working_folder: str, file_name: str, existing: set[str]) -> str | None:
        """Return the legacy sidecar path, or ``None`` when it is not unambiguously ``file_name``'s."""
        if not _legacy_sidecar_is_unambiguous(file_name, existing):
            return None
        return _combine_paths(working_folder, _legacy_description_file_name(file_name))

    async def _read_description(self, working_folder: str, file_name: str, existing: set[str]) -> str | None:
        """Return the description for ``file_name``, falling back to an unambiguous legacy sidecar."""
        description = await self.store.read(await self._sidecar_path(working_folder, file_name))
        if description is not None:
            return description
        legacy_path = self._legacy_sidecar_path(working_folder, file_name, existing)
        if legacy_path is None:
            return None
        return await self.store.read(legacy_path)

    async def _rebuild_index(self, working_folder: str) -> None:
        """Rebuild the ``memories.md`` index for ``working_folder``.

        Lists the non-internal files, sorts them deterministically, reads any
        companion descriptions, and writes a capped markdown summary.
        """
        entries = await self.store.list_children(working_folder)
        file_names = [entry.name for entry in entries if entry.type == FileStoreEntry.FILE]
        sorted_files = sorted((name for name in file_names if not _is_internal_file(name)), key=str.lower)
        available = set(sorted_files)

        lines = ["# Memory Index", ""]
        for file_name in sorted_files[:_MAX_INDEX_ENTRIES]:
            description = await self._read_description(working_folder, file_name, available)
            if description and description.strip():
                lines.append(f"- **{file_name}**: {description.strip()}")
            else:
                lines.append(f"- **{file_name}**")

        index_path = _combine_paths(working_folder, _MEMORY_INDEX_FILE_NAME)
        await self.store.write(index_path, "\n".join(lines) + "\n")

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject file-memory tools, instructions, and the memory index."""
        working_folder = self._resolve_working_folder(context)

        if working_folder:
            await self.store.create_directory(working_folder)

        @tool(name="file_memory_write", schema=_WriteFileInput, approval_mode="never_require")
        async def file_memory_write(file_name: str, content: str, description: str | None = None) -> str:
            """Write a memory file with the given name and content. Overwrites the file if it already exists. Include a description for large files to provide a summary that helps with future discovery."""  # ruff:ignore[line-too-long]
            try:
                normalized = _normalize_relative_path(file_name)
            except ValueError as exc:
                return f"Could not write file '{file_name}': {exc}"
            if _is_nested_path(normalized):
                return (
                    f"Could not write file '{file_name}': memory files must not be written into a "
                    "subdirectory. Please choose a flat file name without path separators."
                )
            if _is_internal_file(normalized):
                return (
                    f"Could not write file '{file_name}': the file name is reserved for internal use. "
                    "Please choose a different file name."
                )

            path = _combine_paths(working_folder, normalized)
            # Every mutating tool locks the whole working folder, not just the file, because each
            # write and delete rebuilds the folder's memories.md index. The lock is shared by all
            # providers on the store, including file-access tools editing a file in this folder, so
            # they cannot interleave edits or index rebuilds.
            async with _store_write_lock(self.store, working_folder):
                try:
                    desc_path = await self._sidecar_path(working_folder, normalized)
                    await self.store.write(path, content)
                    if description and description.strip():
                        await self.store.write(desc_path, description)
                    else:
                        await self.store.delete(desc_path)
                        # A legacy sidecar left behind by the pre-isolation format would otherwise
                        # be read back as this file's description, so clearing the description
                        # clears it too — but only when it unambiguously belongs to this file.
                        legacy_path = self._legacy_sidecar_path(
                            working_folder, normalized, await self._memory_file_names(working_folder)
                        )
                        if legacy_path is not None:
                            await self.store.delete(legacy_path)
                    await self._rebuild_index(working_folder)
                except ValueError as exc:
                    return f"Could not write file '{file_name}': {exc}"
                except OSError as exc:
                    return f"Could not write file '{file_name}': {exc.strerror or exc}"
            if description and description.strip():
                return f"File '{file_name}' written with description."
            return f"File '{file_name}' written."

        @tool(name="file_memory_read", schema=_ReadFileInput, approval_mode="never_require")
        async def file_memory_read(file_name: str) -> str:
            r"""Read the content of a memory file by name. Returns the file content or a message indicating the file was not found. Line numbers count lines split on \n only: a lone \r never starts a new line, each line keeps its own terminator, and content ending in a newline has a final empty line."""  # ruff:ignore[line-too-long]
            try:
                normalized = _normalize_relative_path(file_name)
            except ValueError as exc:
                return f"Could not read file '{file_name}': {exc}"
            if _is_nested_path(normalized):
                return f"File '{file_name}' not found."
            try:
                content = await self.store.read(_combine_paths(working_folder, normalized))
            except ValueError as exc:
                return f"Could not read file '{file_name}': {exc}"
            except OSError as exc:
                return f"Could not read file '{file_name}': {exc.strerror or exc}"
            return content if content is not None else f"File '{file_name}' not found."

        @tool(name="file_memory_delete", schema=_DeleteFileInput, approval_mode="never_require")
        async def file_memory_delete(file_name: str) -> str:
            """Delete a memory file by name. Also removes its companion description file if one exists."""
            try:
                normalized = _normalize_relative_path(file_name)
            except ValueError as exc:
                return f"Could not delete file '{file_name}': {exc}"
            if _is_nested_path(normalized):
                return f"File '{file_name}' not found."

            path = _combine_paths(working_folder, normalized)
            async with _store_write_lock(self.store, working_folder):
                try:
                    # Resolve the sidecar before the file disappears: a digest name is derived
                    # from the backend's canonical stored name, which is only discoverable while
                    # the file is still listed.
                    desc_path = await self._sidecar_path(working_folder, normalized)
                    deleted = await self.store.delete(path)
                    await self.store.delete(desc_path)
                    legacy_path = self._legacy_sidecar_path(
                        working_folder, normalized, await self._memory_file_names(working_folder)
                    )
                    if legacy_path is not None:
                        await self.store.delete(legacy_path)
                    await self._rebuild_index(working_folder)
                except ValueError as exc:
                    return f"Could not delete file '{file_name}': {exc}"
                except OSError as exc:
                    return f"Could not delete file '{file_name}': {exc.strerror or exc}"
            return f"File '{file_name}' deleted." if deleted else f"File '{file_name}' not found."

        @tool(name="file_memory_ls", schema=_ListInput, approval_mode="never_require")
        async def file_memory_ls(glob_pattern: str | None = None) -> list[dict[str, Any]] | str:
            """List all memory files with their descriptions (if available). Optionally filter file names with a glob_pattern (e.g. "*.md"). Internal files (description sidecars and the memory index) are not shown. Each entry is {"name": <name>, "type": "file", "description": <desc-or-null>}."""  # ruff:ignore[line-too-long]
            try:
                entries = await self.store.list_children(working_folder)
                file_names = [entry.name for entry in entries if entry.type == FileStoreEntry.FILE]
                available = {name for name in file_names if not _is_internal_file(name)}
                results: list[dict[str, Any]] = []
                for file_name in file_names:
                    if _is_internal_file(file_name):
                        continue
                    if not _matches_glob(file_name, glob_pattern):
                        continue
                    description = await self._read_description(working_folder, file_name, available)
                    results.append({"name": file_name, "type": "file", "description": description})
            except OSError as exc:
                return f"Could not list memory files: {exc.strerror or exc}"
            return results

        @tool(name="file_memory_replace", schema=_ReplaceInput, approval_mode="never_require")
        async def file_memory_replace(
            file_name: str, old_string: str, new_string: str, replace_all: bool = False
        ) -> str:
            """Replace occurrences of old_string with new_string in a memory file. Fails if old_string is not found, or if it occurs more than once and replace_all is false. Returns the number of occurrences replaced."""  # ruff:ignore[line-too-long]
            try:
                normalized = _normalize_relative_path(file_name)
            except ValueError as exc:
                return f"Could not replace in file '{file_name}': {exc}"
            if _is_nested_path(normalized):
                return f"File '{file_name}' not found."
            if _is_internal_file(normalized):
                return (
                    f"Could not replace in file '{file_name}': the file name is reserved for internal use. "
                    "Please choose a different file name."
                )
            path = _combine_paths(working_folder, normalized)
            async with _store_write_lock(self.store, working_folder):
                try:
                    content = await self.store.read(path)
                    if content is None:
                        return f"File '{file_name}' not found."
                    new_content, count = _apply_replace(content, old_string, new_string, replace_all)
                    await self.store.write(path, new_content)
                except ValueError as exc:
                    return f"Could not replace in file '{file_name}': {exc}"
                except OSError as exc:
                    return f"Could not replace in file '{file_name}': {exc.strerror or exc}"
            return f"Replaced {count} occurrence(s) in '{file_name}'."

        @tool(name="file_memory_replace_lines", schema=_ReplaceLinesInput, approval_mode="never_require")
        async def file_memory_replace_lines(file_name: str, edits: list[_LineEdit]) -> str:
            r"""Replace lines in a memory file. Provide a list of edits, each with a 1-based line_number and a literal new_line (include your own trailing newline); an empty new_line deletes the line, including its line break. Fails on out-of-range or duplicate line numbers. Line numbers count lines split on \n only: a lone \r never starts a new line, each line keeps its own terminator, and content ending in a newline has a final empty line."""  # ruff:ignore[line-too-long]
            try:
                normalized = _normalize_relative_path(file_name)
            except ValueError as exc:
                return f"Could not edit file '{file_name}': {exc}"
            if _is_nested_path(normalized):
                return f"File '{file_name}' not found."
            if _is_internal_file(normalized):
                return (
                    f"Could not edit file '{file_name}': the file name is reserved for internal use. "
                    "Please choose a different file name."
                )
            path = _combine_paths(working_folder, normalized)
            async with _store_write_lock(self.store, working_folder):
                try:
                    content = await self.store.read(path)
                    if content is None:
                        return f"File '{file_name}' not found."
                    new_content = _apply_replace_lines(content, _line_edits(edits))
                    await self.store.write(path, new_content)
                except ValueError as exc:
                    return f"Could not edit file '{file_name}': {exc}"
                except OSError as exc:
                    return f"Could not edit file '{file_name}': {exc.strerror or exc}"
            return f"Replaced {len(edits)} line(s) in '{file_name}'."

        @tool(name="file_memory_grep", schema=_SearchFilesInput, approval_mode="never_require")
        async def file_memory_grep(
            regex_pattern: str,
            glob_pattern: str | None = None,
        ) -> list[dict[str, Any]] | str:
            """Search memory file contents using a case-insensitive regular expression. Optionally filter which files to search using a glob pattern (e.g., "*.md", "research*"). Returns matching file names, content snippets, and matching lines with line numbers. The regex_pattern must be 256 characters or fewer."""  # ruff:ignore[line-too-long]
            glob_filter = glob_pattern if glob_pattern and glob_pattern.strip() else None
            try:
                results = await self.store.search(working_folder, regex_pattern, glob_filter, recursive=False)
                # The index and the description sidecars are the provider's own bookkeeping and
                # are never shown to the agent, so a match inside one is dropped rather than
                # reported.
                visible = [result for result in results if not _is_internal_file(result.file_name)]
            except ValueError as exc:
                return f"Could not search memory files: {exc}"
            except OSError as exc:
                return f"Could not search memory files: {exc.strerror or exc}"
            return [result.to_dict() for result in visible]

        context.extend_instructions(self.source_id, [self.instructions])
        context.extend_tools(
            self.source_id,
            [
                file_memory_write,
                file_memory_read,
                file_memory_delete,
                file_memory_ls,
                file_memory_grep,
                file_memory_replace,
                file_memory_replace_lines,
            ],
        )

        try:
            index_content = await self.store.read(_combine_paths(working_folder, _MEMORY_INDEX_FILE_NAME))
        except (OSError, ValueError) as exc:
            # A corrupt/unavailable index (e.g. non-UTF8 bytes on disk or a store
            # error) must not block the run. Skip index injection for this run; it
            # self-heals on the next successful write/delete that rebuilds the index.
            logger.warning("Could not read memory index; skipping index injection: %s", exc)
            index_content = None
        if index_content and index_content.strip():
            context.extend_messages(
                self.source_id,
                [
                    Message(
                        role="user",
                        contents=[
                            (
                                "The following is your memory index — a list of files you have previously written. "
                                "You can read any of these files using the file_memory_read tool.\n\n"
                                f"{index_content}"
                            )
                        ],
                    )
                ],
            )


__all__ = [
    "DEFAULT_FILE_MEMORY_INSTRUCTIONS",
    "DEFAULT_FILE_MEMORY_SOURCE_ID",
    "FileMemoryProvider",
]
