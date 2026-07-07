# Copyright (c) Microsoft. All rights reserved.

"""File-based memory harness provider backed by an ``AgentFileStore``.

:class:`FileMemoryProvider` gives an agent a session-scoped, file-based memory
system. Each memory is stored as an individual file with a meaningful name, and
large files can carry a companion description file (suffixed with
``_description.md``) that provides a short summary used for discovery. A
``memories.md`` index file is maintained automatically and injected into the
agent's context so the model knows what memories already exist.

File access is mediated through the :class:`~agent_framework.AgentFileStore`
abstraction (shared with :class:`~agent_framework.FileAccessProvider`), so the
same in-memory, local-disk, or remote-blob backends can be reused here.

Unlike :class:`~agent_framework.FileAccessProvider`, which exposes a *shared*
store visible across sessions and agents, :class:`FileMemoryProvider` isolates
memories per session by default: every session writes under its own working
folder (derived from the session id). Pass an explicit ``scope`` to group
memories differently, for example by user id.

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

import asyncio
import logging
from typing import Annotated, Any

from pydantic import BaseModel, Field

from .._feature_stage import ExperimentalFeature, experimental
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
_MEMORY_INDEX_FILE_NAME = "memories.md"
_MAX_INDEX_ENTRIES = 50


def _description_file_name(file_name: str) -> str:
    """Return the companion description file name for ``file_name``.

    The suffix replaces the original extension when present (so ``notes.md``
    becomes ``notes_description.md``); otherwise it is appended.
    """
    dot_index = file_name.rfind(".")
    if dot_index > 0:
        return f"{file_name[:dot_index]}{_DESCRIPTION_SUFFIX}"
    return f"{file_name}{_DESCRIPTION_SUFFIX}"


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


@experimental(feature_id=ExperimentalFeature.HARNESS)
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
                ``session_id`` is used, isolating memories per session.
            instructions: Optional instruction override. When ``None`` the
                default file-memory instructions are used.
        """
        super().__init__(source_id)
        self.store = store
        self.scope = scope
        self.instructions = instructions or DEFAULT_FILE_MEMORY_INSTRUCTIONS
        # Serializes write/delete operations (and their index rebuilds) so the
        # ``memories.md`` index stays consistent. A single per-instance lock is
        # sufficient for v1; concurrent writes across scopes are rare in practice.
        self._write_lock = asyncio.Lock()

    def _resolve_working_folder(self, context: SessionContext) -> str:
        """Resolve the working folder for the current invocation.

        Uses the configured ``scope`` when set, otherwise the session id. The
        result is normalized as a relative directory path so it cannot escape
        the store root.
        """
        raw_scope = self.scope or context.session_id or ""
        return _normalize_relative_path(raw_scope, is_directory=True)

    async def _rebuild_index(self, working_folder: str) -> None:
        """Rebuild the ``memories.md`` index for ``working_folder``.

        Lists the non-internal files, sorts them deterministically, reads any
        companion descriptions, and writes a capped markdown summary.
        """
        entries = await self.store.list_children(working_folder)
        file_names = [entry.name for entry in entries if entry.type == FileStoreEntry.FILE]
        sorted_files = sorted((name for name in file_names if not _is_internal_file(name)), key=str.lower)

        lines = ["# Memory Index", ""]
        for file_name in sorted_files[:_MAX_INDEX_ENTRIES]:
            description = await self.store.read(_combine_paths(working_folder, _description_file_name(file_name)))
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
            """Write a memory file with the given name and content. Overwrites the file if it already exists. Include a description for large files to provide a summary that helps with future discovery."""  # noqa: E501
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
            desc_path = _combine_paths(working_folder, _description_file_name(normalized))
            async with self._write_lock:
                try:
                    await self.store.write(path, content)
                    if description and description.strip():
                        await self.store.write(desc_path, description)
                    else:
                        await self.store.delete(desc_path)
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
            """Read the content of a memory file by name. Returns the file content or a message indicating the file was not found."""  # noqa: E501
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
            desc_path = _combine_paths(working_folder, _description_file_name(normalized))
            async with self._write_lock:
                try:
                    deleted = await self.store.delete(path)
                    await self.store.delete(desc_path)
                    await self._rebuild_index(working_folder)
                except ValueError as exc:
                    return f"Could not delete file '{file_name}': {exc}"
                except OSError as exc:
                    return f"Could not delete file '{file_name}': {exc.strerror or exc}"
            return f"File '{file_name}' deleted." if deleted else f"File '{file_name}' not found."

        @tool(name="file_memory_ls", schema=_ListInput, approval_mode="never_require")
        async def file_memory_ls(glob_pattern: str | None = None) -> list[dict[str, Any]] | str:
            """List all memory files with their descriptions (if available). Optionally filter file names with a glob_pattern (e.g. "*.md"). Internal files (description sidecars and the memory index) are not shown. Each entry is {"name": <name>, "type": "file", "description": <desc-or-null>}."""  # noqa: E501
            try:
                entries = await self.store.list_children(working_folder)
            except OSError as exc:
                return f"Could not list memory files: {exc.strerror or exc}"

            file_names = [entry.name for entry in entries if entry.type == FileStoreEntry.FILE]
            available = set(file_names)
            results: list[dict[str, Any]] = []
            for file_name in file_names:
                if _is_internal_file(file_name):
                    continue
                if not _matches_glob(file_name, glob_pattern):
                    continue
                description: str | None = None
                desc_file_name = _description_file_name(file_name)
                if desc_file_name in available:
                    description = await self.store.read(_combine_paths(working_folder, desc_file_name))
                results.append({"name": file_name, "type": "file", "description": description})
            return results

        @tool(name="file_memory_replace", schema=_ReplaceInput, approval_mode="never_require")
        async def file_memory_replace(
            file_name: str, old_string: str, new_string: str, replace_all: bool = False
        ) -> str:
            """Replace occurrences of old_string with new_string in a memory file. Fails if old_string is not found, or if it occurs more than once and replace_all is false. Returns the number of occurrences replaced."""  # noqa: E501
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
            async with self._write_lock:
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
            """Replace lines in a memory file. Provide a list of edits, each with a 1-based line_number and a literal new_line (include your own trailing newline); an empty new_line deletes the line, including its line break. Fails on out-of-range or duplicate line numbers."""  # noqa: E501
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
            async with self._write_lock:
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
            """Search memory file contents using a case-insensitive regular expression. Optionally filter which files to search using a glob pattern (e.g., "*.md", "research*"). Returns matching file names, content snippets, and matching lines with line numbers. The regex_pattern must be 256 characters or fewer."""  # noqa: E501
            glob_filter = glob_pattern if glob_pattern and glob_pattern.strip() else None
            try:
                results = await self.store.search(working_folder, regex_pattern, glob_filter, recursive=False)
            except ValueError as exc:
                return f"Could not search memory files: {exc}"
            except OSError as exc:
                return f"Could not search memory files: {exc.strerror or exc}"
            return [result.to_dict() for result in results if not _is_internal_file(result.file_name)]

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
