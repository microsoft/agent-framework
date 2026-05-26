# Copyright (c) Microsoft. All rights reserved.

"""File-access harness provider exposing CRUD/search tools backed by an ``AgentFileStore``.

Unlike :class:`~agent_framework.MemoryContextProvider`, which provides
session-scoped memory that may be isolated per session, :class:`FileAccessProvider`
operates on a shared, persistent storage area whose contents are visible across
sessions and agents. The provider exposes five tools — ``file_access_save_file``,
``file_access_read_file``, ``file_access_delete_file``, ``file_access_list_files``,
and ``file_access_search_files`` — by registering them on the per-invocation
:class:`~agent_framework.SessionContext` in :meth:`FileAccessProvider.before_run`.

The store abstraction is generic so callers can plug in in-memory, local-disk, or
remote-blob backends. Two backends are shipped here:

* :class:`InMemoryAgentFileStore` — dict-backed, suitable for tests.
* :class:`FileSystemAgentFileStore` — disk-backed, with traversal and symlink
  protections.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
from abc import ABC, abstractmethod
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, cast

from .._feature_stage import ExperimentalFeature, experimental
from .._serialization import SerializationMixin
from .._sessions import AgentSession, ContextProvider, SessionContext
from .._tools import tool

DEFAULT_FILE_ACCESS_SOURCE_ID = "file_access"
DEFAULT_FILE_ACCESS_INSTRUCTIONS = (
    "## File Access\n"
    "You have access to a shared file storage area via the `file_access_*` tools "
    "for reading, writing, and managing files.\n"
    "These files persist beyond the current session and may be shared across "
    "sessions or agents.\n"
    "Use these tools to read input data provided by the user, write output "
    "artifacts, and manage any files the user has asked you to work with.\n\n"
    "- Never delete or overwrite existing files unless the user has explicitly "
    "asked you to do so."
)

# Maximum number of characters of context to include on either side of the first
# regex match when building a result snippet.
_SEARCH_SNIPPET_RADIUS = 50


def _normalize_relative_path(path: str, *, is_directory: bool = False) -> str:
    """Normalize and validate a relative store path.

    Replaces backslashes with forward slashes, collapses repeated separators, and
    rejects rooted paths, drive letters, and ``.``/``..`` segments. When
    ``is_directory`` is True, an empty result is allowed and represents the root;
    otherwise an empty result is rejected.

    Args:
        path: The relative path to normalize.

    Keyword Args:
        is_directory: Whether the path represents a directory (allows empty
            results) or a file (rejects empty results).

    Returns:
        The normalized forward-slash relative path.

    Raises:
        ValueError: When the path is rooted, starts with a drive letter, contains
            ``.``/``..`` segments, or is empty for a file path.
    """
    if not path or not path.strip():
        if not is_directory:
            raise ValueError("A file path must not be empty or whitespace-only.")
        return ""

    normalized = path.replace("\\", "/").strip("/")

    if (
        os.path.isabs(path)
        or path.startswith(("/", "\\"))
        or (len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == ":")
    ):
        raise ValueError(
            f"Invalid path: {path!r}. Paths must be relative and must not start with '/', '\\', or a drive root."
        )

    clean_segments: list[str] = []
    for segment in normalized.split("/"):
        if not segment:
            continue
        if segment in (".", ".."):
            raise ValueError(f"Invalid path: {path!r}. Paths must not contain '.' or '..' segments.")
        clean_segments.append(segment)

    result = "/".join(clean_segments)
    if not is_directory and not result:
        raise ValueError(f"Invalid path: {path!r}. A file path must not be empty.")
    return result


def _matches_glob(file_name: str, pattern: str | None) -> bool:
    """Return whether ``file_name`` matches the optional glob pattern (case-insensitive).

    When ``pattern`` is ``None`` or blank this returns True so callers can skip
    filtering by passing nothing. Matching uses :func:`fnmatch.fnmatchcase` over a
    lowercased pattern/name pair to give consistent results across operating
    systems (``fnmatch.fnmatch`` is case-sensitive on POSIX but not on Windows).
    """
    if pattern is None or not pattern.strip():
        return True
    return fnmatch.fnmatchcase(file_name.lower(), pattern.lower())


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileSearchMatch(SerializationMixin):
    """Represent one line within a file that matched a search pattern."""

    line_number: int
    line: str
    __slots__ = ("line", "line_number")

    def __init__(self, line_number: int, line: str) -> None:
        r"""Initialize one search match.

        Args:
            line_number: The 1-based line number where the match was found.
            line: The content of the matching line (trailing ``\r`` removed).
        """
        if line_number < 1:
            raise ValueError("line_number must be a positive integer.")
        self.line_number = line_number
        self.line = line

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Serialize this match to a JSON-compatible dictionary."""
        del exclude, exclude_none
        return {"line_number": self.line_number, "line": self.line}

    @classmethod
    def from_dict(
        cls, raw_match: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> FileSearchMatch:
        """Parse one search match from its dict representation."""
        del dependencies
        line_number = raw_match.get("line_number")
        line = raw_match.get("line", "")
        if not isinstance(line_number, int) or isinstance(line_number, bool):
            raise ValueError("FileSearchMatch.line_number must be an integer.")
        if not isinstance(line, str):
            raise ValueError("FileSearchMatch.line must be a string.")
        return cls(line_number=line_number, line=line)

    def __eq__(self, other: object) -> bool:
        """Return whether two matches have the same values."""
        return isinstance(other, FileSearchMatch) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        """Return a helpful debug representation."""
        return f"FileSearchMatch(line_number={self.line_number!r}, line={self.line!r})"


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileSearchResult(SerializationMixin):
    """Represent the search result for one file: the file name, a snippet, and the matching lines."""

    file_name: str
    snippet: str
    matching_lines: list[FileSearchMatch]
    __slots__ = ("file_name", "matching_lines", "snippet")

    def __init__(
        self,
        file_name: str,
        snippet: str = "",
        matching_lines: list[FileSearchMatch] | None = None,
    ) -> None:
        """Initialize one search result.

        Args:
            file_name: The name of the file that matched the search.
            snippet: A short context snippet around the first match.
            matching_lines: The list of matching lines within the file.
        """
        self.file_name = file_name
        self.snippet = snippet
        self.matching_lines = list(matching_lines) if matching_lines is not None else []

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Serialize this result to a JSON-compatible dictionary."""
        del exclude, exclude_none
        return {
            "file_name": self.file_name,
            "snippet": self.snippet,
            "matching_lines": [match.to_dict() for match in self.matching_lines],
        }

    @classmethod
    def from_dict(
        cls, raw_result: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> FileSearchResult:
        """Parse one search result from its dict representation."""
        del dependencies
        file_name = raw_result.get("file_name", "")
        snippet = raw_result.get("snippet", "")
        raw_matching_lines = raw_result.get("matching_lines", [])
        if not isinstance(file_name, str):
            raise ValueError("FileSearchResult.file_name must be a string.")
        if not isinstance(snippet, str):
            raise ValueError("FileSearchResult.snippet must be a string.")
        if not isinstance(raw_matching_lines, list):
            raise ValueError("FileSearchResult.matching_lines must be a list.")
        matching_lines = [
            FileSearchMatch.from_dict(cast(MutableMapping[str, Any], item)) for item in raw_matching_lines
        ]
        return cls(file_name=file_name, snippet=snippet, matching_lines=matching_lines)

    def __eq__(self, other: object) -> bool:
        """Return whether two results have the same values."""
        return isinstance(other, FileSearchResult) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        """Return a helpful debug representation."""
        return (
            "FileSearchResult("
            f"file_name={self.file_name!r}, snippet={self.snippet!r}, matching_lines={self.matching_lines!r})"
        )


def _search_file_content(file_name: str, content: str, regex: re.Pattern[str]) -> FileSearchResult | None:
    r"""Search one file's content and return a :class:`FileSearchResult` if any lines match.

    Lines are split on ``\n`` (so ``\r`` at the end of each line is stripped on
    the matching line itself). A snippet of up to ``±_SEARCH_SNIPPET_RADIUS``
    characters around the first match is included. Returns ``None`` when no
    lines match.
    """
    lines = content.split("\n")
    matching_lines: list[FileSearchMatch] = []
    first_snippet: str | None = None
    line_start_offset = 0

    for index, line in enumerate(lines):
        match = regex.search(line)
        if match is not None:
            matching_lines.append(FileSearchMatch(line_number=index + 1, line=line.rstrip("\r")))
            if first_snippet is None:
                char_index = line_start_offset + match.start()
                snippet_start = max(0, char_index - _SEARCH_SNIPPET_RADIUS)
                snippet_end = min(len(content), char_index + (match.end() - match.start()) + _SEARCH_SNIPPET_RADIUS)
                first_snippet = content[snippet_start:snippet_end]
        # Advance past this line and the implied '\n' separator.
        line_start_offset += len(line) + 1

    if not matching_lines:
        return None
    return FileSearchResult(
        file_name=file_name,
        snippet=first_snippet or "",
        matching_lines=matching_lines,
    )


@experimental(feature_id=ExperimentalFeature.HARNESS)
class AgentFileStore(ABC):
    """Abstract base class for file storage operations used by :class:`FileAccessProvider`.

    All paths are relative to an implementation-defined root. Implementations may
    map these paths to a local file system, in-memory store, remote blob storage,
    or other mechanisms. Paths use forward slashes as separators and must not
    escape the root (e.g., via ``..`` segments). Implementations are responsible
    for enforcing that invariant.
    """

    @abstractmethod
    async def write_file(self, path: str, content: str) -> None:
        """Write ``content`` to the file at ``path``, creating or overwriting it.

        Args:
            path: The relative path of the file to write.
            content: The content to write to the file.
        """

    @abstractmethod
    async def read_file(self, path: str) -> str | None:
        """Read the content of the file at ``path``.

        Args:
            path: The relative path of the file to read.

        Returns:
            The file content, or ``None`` if the file does not exist.
        """

    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        """Delete the file at ``path``.

        Args:
            path: The relative path of the file to delete.

        Returns:
            ``True`` if the file was deleted; ``False`` if it did not exist.
        """

    @abstractmethod
    async def list_files(self, directory: str = "") -> list[str]:
        """List the direct child files of ``directory``.

        Args:
            directory: The relative directory path to list. Use ``""`` for the root.

        Returns:
            The list of file names (not full paths) in the specified directory.
        """

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Return whether a file exists at ``path``.

        Args:
            path: The relative path of the file to check.
        """

    @abstractmethod
    async def search_files(
        self,
        directory: str,
        regex_pattern: str,
        file_pattern: str | None = None,
    ) -> list[FileSearchResult]:
        """Search files in ``directory`` for content matching ``regex_pattern``.

        Args:
            directory: The relative directory to search. Use ``""`` for the root.
            regex_pattern: A regular expression matched against file contents
                (case-insensitive). For example, ``"error|warning"`` matches lines
                containing ``"error"`` or ``"warning"``.
            file_pattern: An optional glob pattern (case-insensitive) used to
                filter which files are searched. When ``None`` or blank, every
                file in the directory is searched.

        Returns:
            The list of files whose content matched, with snippet and matching
            line metadata.
        """

    @abstractmethod
    async def create_directory(self, path: str) -> None:
        """Ensure ``path`` exists as a directory, creating it if necessary."""


@experimental(feature_id=ExperimentalFeature.HARNESS)
class InMemoryAgentFileStore(AgentFileStore):
    """An in-memory :class:`AgentFileStore` backed by a dict.

    Suitable for tests and lightweight scenarios where persistence is not
    required. Directory concepts are simulated using path prefixes — no explicit
    directory structure is maintained.
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory file store."""
        # Keys are normalized forward-slash relative paths; comparisons are case-
        # insensitive.
        self._files: dict[str, str] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(path: str) -> str:
        return _normalize_relative_path(path).lower()

    async def write_file(self, path: str, content: str) -> None:
        """Write ``content`` to the file at ``path``."""
        key = self._key(path)
        async with self._lock:
            self._files[key] = content

    async def read_file(self, path: str) -> str | None:
        """Return the file content, or ``None`` if the file does not exist."""
        key = self._key(path)
        async with self._lock:
            return self._files.get(key)

    async def delete_file(self, path: str) -> bool:
        """Delete the file and return whether anything was removed."""
        key = self._key(path)
        async with self._lock:
            return self._files.pop(key, None) is not None

    async def list_files(self, directory: str = "") -> list[str]:
        """Return the direct child files of ``directory``."""
        prefix = _normalize_relative_path(directory, is_directory=True).lower()
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        async with self._lock:
            keys = list(self._files.keys())
        return [key[len(prefix) :] for key in keys if key.startswith(prefix) and "/" not in key[len(prefix) :]]

    async def file_exists(self, path: str) -> bool:
        """Return whether the file exists."""
        key = self._key(path)
        async with self._lock:
            return key in self._files

    async def search_files(
        self,
        directory: str,
        regex_pattern: str,
        file_pattern: str | None = None,
    ) -> list[FileSearchResult]:
        """Search file contents for ``regex_pattern`` matches."""
        prefix = _normalize_relative_path(directory, is_directory=True).lower()
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        # Compiled here once for reuse across files. Python's stdlib ``re`` has
        # no built-in timeout, matching the existing approach in ``_memory.py``.
        regex = re.compile(regex_pattern, flags=re.IGNORECASE)

        async with self._lock:
            entries = list(self._files.items())

        results: list[FileSearchResult] = []
        for key, file_content in entries:
            if not key.startswith(prefix):
                continue
            relative_name = key[len(prefix) :]
            if "/" in relative_name:
                continue
            if not _matches_glob(relative_name, file_pattern):
                continue
            result = _search_file_content(relative_name, file_content, regex)
            if result is not None:
                results.append(result)
        return results

    async def create_directory(self, path: str) -> None:
        """No-op: directories are implicit from file paths in the in-memory store."""
        del path


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileSystemAgentFileStore(AgentFileStore):
    """A disk-backed :class:`AgentFileStore` rooted under a configurable directory.

    All paths are resolved relative to the root directory provided at
    construction time. Lexical path traversal attempts (for example, via ``..``
    segments or absolute paths) are rejected with :class:`ValueError`. The root
    directory is created automatically if it does not already exist.

    Symbolic links and reparse points anywhere along the resolved path are
    rejected on read, write, delete, and existence checks to prevent escaping
    the root.
    """

    def __init__(self, root_directory: str | os.PathLike[str]) -> None:
        """Initialize the file-system store.

        Args:
            root_directory: The directory under which all files are stored.
                Created if it does not exist.
        """
        raw_root = os.fspath(root_directory)
        if not raw_root or not raw_root.strip():
            raise ValueError("root_directory must not be empty or whitespace-only.")
        root_path = Path(raw_root).resolve()
        root_path.mkdir(parents=True, exist_ok=True)
        self._root_path = root_path

    @property
    def root_path(self) -> Path:
        """Return the resolved root directory."""
        return self._root_path

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """Resolve a relative file path safely under the root directory."""
        normalized = _normalize_relative_path(relative_path)
        candidate = (self._root_path / normalized).resolve()
        try:
            candidate.relative_to(self._root_path)
        except ValueError as exc:
            raise ValueError(f"Invalid path: {relative_path!r}. The resolved path escapes the root directory.") from exc
        self._throw_if_contains_symlink(candidate)
        return candidate

    def _resolve_safe_directory_path(self, relative_directory: str) -> Path:
        """Resolve a relative directory path safely under the root directory.

        An empty string resolves to the root directory itself.
        """
        if not relative_directory:
            return self._root_path
        return self._resolve_safe_path(relative_directory)

    def _throw_if_contains_symlink(self, candidate: Path) -> None:
        """Reject any segment between the root and ``candidate`` that is a symlink/reparse point.

        Walks each ancestor down from the root. Stops once a segment does not
        exist on disk so write scenarios remain allowed. ``Path.is_symlink``
        detects both POSIX symlinks and Windows reparse points (junctions).
        """
        try:
            relative_parts = candidate.relative_to(self._root_path).parts
        except ValueError:
            # ``_resolve_safe_path`` already validates containment; an
            # unrelated path here would mean we were called with a path that
            # never belonged to the root in the first place.
            raise ValueError("Invalid path: the resolved path is not under the root directory.") from None

        current = self._root_path
        for segment in relative_parts:
            current = current / segment
            try:
                if current.is_symlink():
                    raise ValueError("Invalid path: the resolved path contains a symbolic link or reparse point.")
            except OSError:
                # Permission errors and similar transient OS errors during the
                # symlink probe should not silently allow the access; treat as
                # missing and stop checking so the underlying I/O surfaces the
                # real error.
                break
            if not current.exists():
                break

    async def write_file(self, path: str, content: str) -> None:
        """Write ``content`` to the file at ``path``."""
        full_path = self._resolve_safe_path(path)
        await asyncio.to_thread(self._write_file_sync, full_path, content)

    @staticmethod
    def _write_file_sync(full_path: Path, content: str) -> None:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

    async def read_file(self, path: str) -> str | None:
        """Return the file content, or ``None`` if the file does not exist."""
        full_path = self._resolve_safe_path(path)
        return await asyncio.to_thread(self._read_file_sync, full_path)

    @staticmethod
    def _read_file_sync(full_path: Path) -> str | None:
        if not full_path.is_file():
            return None
        return full_path.read_text(encoding="utf-8")

    async def delete_file(self, path: str) -> bool:
        """Delete the file and return whether anything was removed."""
        full_path = self._resolve_safe_path(path)
        return await asyncio.to_thread(self._delete_file_sync, full_path)

    @staticmethod
    def _delete_file_sync(full_path: Path) -> bool:
        if not full_path.is_file():
            return False
        full_path.unlink()
        return True

    async def list_files(self, directory: str = "") -> list[str]:
        """Return the direct child files of ``directory``."""
        full_dir = self._resolve_safe_directory_path(directory)
        return await asyncio.to_thread(self._list_files_sync, full_dir)

    @staticmethod
    def _list_files_sync(full_dir: Path) -> list[str]:
        if not full_dir.is_dir():
            return []
        names: list[str] = []
        for entry in full_dir.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_file():
                names.append(entry.name)
        return names

    async def file_exists(self, path: str) -> bool:
        """Return whether the file exists."""
        full_path = self._resolve_safe_path(path)
        return await asyncio.to_thread(self._file_exists_sync, full_path)

    @staticmethod
    def _file_exists_sync(full_path: Path) -> bool:
        return full_path.is_file()

    async def search_files(
        self,
        directory: str,
        regex_pattern: str,
        file_pattern: str | None = None,
    ) -> list[FileSearchResult]:
        """Search file contents for ``regex_pattern`` matches."""
        full_dir = self._resolve_safe_directory_path(directory)
        regex = re.compile(regex_pattern, flags=re.IGNORECASE)
        return await asyncio.to_thread(self._search_files_sync, full_dir, regex, file_pattern)

    @staticmethod
    def _search_files_sync(full_dir: Path, regex: re.Pattern[str], file_pattern: str | None) -> list[FileSearchResult]:
        if not full_dir.is_dir():
            return []
        results: list[FileSearchResult] = []
        for entry in full_dir.iterdir():
            if entry.is_symlink() or not entry.is_file():
                continue
            file_name = entry.name
            if not _matches_glob(file_name, file_pattern):
                continue
            file_content = entry.read_text(encoding="utf-8")
            result = _search_file_content(file_name, file_content, regex)
            if result is not None:
                results.append(result)
        return results

    async def create_directory(self, path: str) -> None:
        """Ensure the directory at ``path`` exists, creating it if necessary."""
        full_path = self._resolve_safe_directory_path(path)
        await asyncio.to_thread(lambda: full_path.mkdir(parents=True, exist_ok=True))


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileAccessProvider(ContextProvider):
    """Context provider that gives an agent CRUD/search access to a shared file store.

    The provider exposes five tools to the agent via the per-invocation
    :class:`~agent_framework.SessionContext`:

    - ``file_access_save_file`` — Save a file (refuses to overwrite by default).
    - ``file_access_read_file`` — Read the content of a file by name.
    - ``file_access_delete_file`` — Delete a file by name.
    - ``file_access_list_files`` — List all file names at the store root.
    - ``file_access_search_files`` — Search file contents using a case-insensitive
      regex, optionally filtered by a glob pattern over file names.

    Unlike :class:`~agent_framework.MemoryContextProvider`, which provides
    session-scoped memory that may be isolated per session,
    :class:`FileAccessProvider` operates on a shared, persistent store whose
    contents are visible across sessions and agents. The store is passed in by
    the caller and should already be scoped to the desired folder or storage
    location.
    """

    def __init__(
        self,
        store: AgentFileStore,
        *,
        source_id: str = DEFAULT_FILE_ACCESS_SOURCE_ID,
        instructions: str | None = None,
    ) -> None:
        """Initialize the file access provider.

        Args:
            store: The file store implementation used for storage operations.
                The store should already be scoped to the desired folder or
                storage location.

        Keyword Args:
            source_id: Unique source ID for the provider.
            instructions: Optional instruction override. When ``None`` the
                default file-access instructions are used.
        """
        super().__init__(source_id)
        self.store = store
        self.instructions = instructions or DEFAULT_FILE_ACCESS_INSTRUCTIONS

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject file-access tools and instructions before the model runs."""
        del agent, session, state

        @tool(name="file_access_save_file", approval_mode="never_require")
        async def file_access_save_file(file_name: str, content: str, overwrite: bool = False) -> str:
            """Save a file with the given name and content. By default, does not overwrite an existing file unless overwrite is set to true."""  # noqa: E501
            normalized = _normalize_relative_path(file_name)
            if not overwrite and await self.store.file_exists(normalized):
                return f"File '{file_name}' already exists. To replace it, save again with overwrite set to true."
            await self.store.write_file(normalized, content)
            return f"File '{file_name}' saved."

        @tool(name="file_access_read_file", approval_mode="never_require")
        async def file_access_read_file(file_name: str) -> str:
            """Read the content of a file by name. Returns the file content or a message indicating the file was not found."""  # noqa: E501
            normalized = _normalize_relative_path(file_name)
            content = await self.store.read_file(normalized)
            return content if content is not None else f"File '{file_name}' not found."

        @tool(name="file_access_delete_file", approval_mode="never_require")
        async def file_access_delete_file(file_name: str) -> str:
            """Delete a file by name."""
            normalized = _normalize_relative_path(file_name)
            deleted = await self.store.delete_file(normalized)
            return f"File '{file_name}' deleted." if deleted else f"File '{file_name}' not found."

        @tool(name="file_access_list_files", approval_mode="never_require")
        async def file_access_list_files() -> list[str]:
            """List all file names."""
            return await self.store.list_files("")

        @tool(name="file_access_search_files", approval_mode="never_require")
        async def file_access_search_files(regex_pattern: str, file_pattern: str | None = None) -> list[dict[str, Any]]:
            """Search file contents using a regular expression pattern (case-insensitive). Optionally filter which files to search using a glob pattern (e.g., "*.md", "research*"). Returns matching file names, snippets, and matching lines with line numbers."""  # noqa: E501
            pattern = file_pattern if file_pattern and file_pattern.strip() else None
            results = await self.store.search_files("", regex_pattern, pattern)
            return [result.to_dict() for result in results]

        context.extend_instructions(self.source_id, [self.instructions])
        context.extend_tools(
            self.source_id,
            [
                file_access_save_file,
                file_access_read_file,
                file_access_delete_file,
                file_access_list_files,
                file_access_search_files,
            ],
        )


__all__ = [
    "DEFAULT_FILE_ACCESS_INSTRUCTIONS",
    "DEFAULT_FILE_ACCESS_SOURCE_ID",
    "AgentFileStore",
    "FileAccessProvider",
    "FileSearchMatch",
    "FileSearchResult",
    "FileSystemAgentFileStore",
    "InMemoryAgentFileStore",
]
