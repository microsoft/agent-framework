# Copyright (c) Microsoft. All rights reserved.

"""File-access harness provider exposing CRUD/search tools backed by an ``AgentFileStore``.

Unlike :class:`~agent_framework.MemoryContextProvider`, which provides
session-scoped memory that may be isolated per session, :class:`FileAccessProvider`
operates on a shared, persistent storage area whose contents are visible across
sessions and agents. The provider exposes tools — ``file_access_write``,
``file_access_read``, ``file_access_delete``, ``file_access_ls``,
``file_access_grep``, ``file_access_replace``, and ``file_access_replace_lines`` —
by registering them on the per-invocation
:class:`~agent_framework.SessionContext` in :meth:`FileAccessProvider.before_run`.

The store abstraction is generic so callers can plug in in-memory, local-disk, or
remote-blob backends. Two backends are shipped here:

* :class:`InMemoryAgentFileStore` — dict-backed, suitable for tests.
* :class:`FileSystemAgentFileStore` — disk-backed, with traversal and symlink
  protections.
"""

from __future__ import annotations

import asyncio
import errno
import fnmatch
import logging
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Annotated, Any, ClassVar, cast

from pydantic import BaseModel, Field

from .._feature_stage import ExperimentalFeature, experimental
from .._serialization import SerializationMixin
from .._sessions import AgentSession, ContextProvider, SessionContext
from .._tools import ApprovalMode, tool
from .._types import Content

logger = logging.getLogger(__name__)

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
    "asked you to do so.\n"
    "- Files may be organized into subdirectories. Use `file_access_ls` "
    "to explore the tree level by level, "
    "or `file_access_grep` to search file contents recursively across "
    "the whole store."
)

# Maximum number of characters of context to include on either side of the first
# regex match when building a result snippet.
_SEARCH_SNIPPET_RADIUS = 50

# Hard cap on the length of a user-supplied search regex. Python's ``re`` module
# has no built-in timeout, so a catastrophic-backtracking pattern (such as
# ``(a+)+$``) submitted by the model could spin the CPU indefinitely. The cap
# alone does not stop short pathological patterns, so :meth:`search`
# additionally executes the regex scan in a worker thread and bounds the wall
# clock with :data:`_SEARCH_TIMEOUT_SECONDS`. The thread itself cannot be
# safely interrupted from Python, so a runaway scan continues until the
# regex engine returns, but the caller and event loop stay responsive.
_MAX_SEARCH_PATTERN_LENGTH = 256
_SEARCH_TIMEOUT_SECONDS = 10.0

# Errno raised by POSIX ``open`` when ``O_NOFOLLOW`` was requested and the
# leaf path component is a symbolic link. Used to translate the kernel-level
# refusal into the same :class:`ValueError` the static probe raises so the
# caller can treat the two cases uniformly.
_ELOOP = errno.ELOOP


def _compile_search_regex(pattern: str) -> re.Pattern[str]:
    """Compile a case-insensitive search regex, enforcing the length cap.

    An invalid ``pattern`` raises :class:`re.error` unchanged so the search
    tools surface it to the calling model, which can correct the pattern and
    retry.

    Raises:
        ValueError: When ``pattern`` exceeds ``_MAX_SEARCH_PATTERN_LENGTH``
            characters.
        re.error: When ``pattern`` is not a valid regular expression.
    """
    if len(pattern) > _MAX_SEARCH_PATTERN_LENGTH:
        raise ValueError(
            f"Regex pattern is too long ({len(pattern)} characters). "
            f"Maximum supported length is {_MAX_SEARCH_PATTERN_LENGTH} characters."
        )
    return re.compile(pattern, flags=re.IGNORECASE)


async def _run_search_with_timeout(
    fn: Callable[[], list[FileSearchResult]],
) -> list[FileSearchResult]:
    """Run ``fn`` in a worker thread with a bounded wall-clock timeout.

    Raises:
        ValueError: When the search does not complete within
            :data:`_SEARCH_TIMEOUT_SECONDS` seconds.
    """
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout=_SEARCH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        # On Python 3.10 ``asyncio.wait_for`` raises ``asyncio.TimeoutError``
        # which is distinct from the builtin ``TimeoutError`` (the two were
        # unified in 3.11). Catching the asyncio alias works on every
        # supported version.
        raise ValueError(
            f"Regex search did not complete within {_SEARCH_TIMEOUT_SECONDS:g} seconds. "
            "Use a more specific pattern (avoid nested quantifiers such as '(a+)+')."
        ) from exc


def _normalize_relative_path(path: str, *, is_directory: bool = False) -> str:
    """Normalize and validate a relative store path.

    Trims surrounding whitespace, replaces backslashes with forward slashes,
    collapses repeated separators, and rejects rooted paths, drive letters, and
    ``.``/``..`` segments. When ``is_directory`` is True, an empty result is
    allowed and represents the root; otherwise an empty result is rejected and
    trailing separators are not accepted (so ``"foo/"`` does not silently
    become the file path ``"foo"``).

    Args:
        path: The relative path to normalize.

    Keyword Args:
        is_directory: Whether the path represents a directory (allows empty
            results and trailing separators) or a file (rejects empty results
            and trailing separators).

    Returns:
        The normalized forward-slash relative path.

    Raises:
        ValueError: When the path is rooted, starts with a drive letter, contains
            ``.``/``..`` segments, is empty for a file path, or ends with a
            separator for a file path.
    """
    if not path or not path.strip():
        if not is_directory:
            raise ValueError("A file path must not be empty or whitespace-only.")
        return ""

    # Trim surrounding whitespace so spaces never leak into file segments.
    path = path.strip()
    converted = path.replace("\\", "/")

    # For file paths reject trailing separators so a directory-shaped string
    # such as ``"foo/"`` is never silently treated as the file ``"foo"``.
    if not is_directory and converted.endswith("/"):
        raise ValueError(f"Invalid path: {path!r}. A file path must not end with a path separator.")

    normalized = converted.strip("/")

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


def _matches_glob(file_name: str, glob_pattern: str | None) -> bool:
    """Return whether ``file_name`` matches the optional glob pattern (case-insensitive).

    ``file_name`` is the forward-slash path of a file relative to the search
    directory (for a direct child this is just its basename; for a recursive
    search it may contain ``/`` separators). When ``pattern`` is ``None`` or blank
    this returns True so callers can skip filtering by passing nothing. Matching
    uses :func:`fnmatch.fnmatchcase` over a lowercased pattern/name pair to give
    consistent results across operating systems (``fnmatch.fnmatch`` is
    case-sensitive on POSIX but not on Windows). Note that with ``fnmatch`` a
    ``*`` matches any characters **including** ``/``, so ``"*.md"`` matches
    markdown files at any depth and ``"reports/*"`` matches everything under
    ``reports``.
    """
    if glob_pattern is None or not glob_pattern.strip():
        return True
    return fnmatch.fnmatchcase(file_name.lower(), glob_pattern.lower())


def _apply_replace(content: str, old_string: str, new_string: str, replace_all: bool) -> tuple[str, int]:
    """Replace ``old_string`` with ``new_string`` in ``content``.

    Returns the new content and the number of replacements made. Raises
    :class:`ValueError` when ``old_string`` is not found, or when more than one
    occurrence exists and ``replace_all`` is ``False``.
    """
    if not old_string:
        raise ValueError("old_string must not be empty.")
    count = content.count(old_string)
    if count == 0:
        raise ValueError(f"old_string not found: {old_string!r}.")
    if count > 1 and not replace_all:
        raise ValueError(
            f"old_string occurs {count} times; pass replace_all=true to replace all, "
            "or provide a more specific old_string."
        )
    return content.replace(old_string, new_string), count


def _split_lines_keepends(content: str) -> list[str]:
    r"""Split ``content`` into lines on ``\n`` only, keeping the terminator attached.

    Splits solely on ``\n`` (a trailing ``\r`` stays as line content), reproducing
    :func:`_search_file_content`'s ``content.split("\n")`` enumeration exactly, so a
    ``line_number`` obtained from ``grep`` always targets the same line here and stays
    in range. This means the result has ``len(content.split("\n"))`` elements: a
    trailing ``\n`` yields a final empty (editable) line, and empty content yields a
    single empty line. ``"".join(...)`` reproduces ``content`` verbatim.
    """
    segments = content.split("\n")
    lines = [segment + "\n" for segment in segments[:-1]]
    lines.append(segments[-1])
    return lines


def _apply_replace_lines(content: str, edits: list[tuple[int, str]]) -> str:
    r"""Apply literal 1-based line replacements to ``content``.

    Each ``new_line`` is written **verbatim** in place of the target line,
    including any trailing newline the caller wants to keep — the editor never
    adds a separator. An empty ``new_line`` deletes the line entirely (content
    and its terminator), and a ``new_line`` containing embedded newlines expands
    one line into several.

    Raises :class:`ValueError` when no edits are provided, when any line number
    is out of range, or when a line number is targeted more than once.
    """
    if not edits:
        raise ValueError("At least one line edit must be provided.")
    lines = _split_lines_keepends(content)
    seen: set[int] = set()
    for line_number, _ in edits:
        if line_number in seen:
            raise ValueError(f"Duplicate line_number {line_number} in edits.")
        seen.add(line_number)
        if line_number < 1 or line_number > len(lines):
            raise ValueError(f"line_number {line_number} is out of range (file has {len(lines)} lines).")
    for line_number, new_line in edits:
        lines[line_number - 1] = new_line
    return "".join(lines)


def _line_edits(edits: list[Any]) -> list[tuple[int, str]]:
    """Normalize ``replace_lines`` edits (pydantic models or dicts) to ``(line_number, new_line)``."""
    normalized: list[tuple[int, str]] = []
    for edit in edits:
        if isinstance(edit, Mapping):
            mapping = cast("Mapping[str, Any]", edit)
            normalized.append((int(mapping["line_number"]), str(mapping["new_line"])))
        else:
            normalized.append((int(edit.line_number), str(edit.new_line)))
    return normalized


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileSearchMatch(SerializationMixin):
    """Represent one line within a file that matched a search pattern."""

    line_number: int
    line: str

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
        """Serialize this match to a JSON-compatible dictionary.

        Overrides :meth:`SerializationMixin.to_dict` to emit an explicit,
        stable payload without the auto-injected ``type`` identifier field.
        The ``exclude`` / ``exclude_none`` arguments are accepted (and
        discarded) so the signature remains drop-in compatible with the
        mixin — callers like :meth:`SerializationMixin.to_json` always
        forward them.
        """
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
        """Serialize this result to a JSON-compatible dictionary.

        Overrides :meth:`SerializationMixin.to_dict` for the same reason as
        :meth:`FileSearchMatch.to_dict`: to emit an explicit payload without
        the auto-injected ``type`` field. The ``exclude`` / ``exclude_none``
        arguments are accepted and ignored to preserve signature
        compatibility with the mixin.
        """
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
        matching_lines: list[FileSearchMatch] = []
        for item in cast(list[object], raw_matching_lines):
            if not isinstance(item, Mapping):
                raise ValueError("FileSearchResult.matching_lines elements must be mappings.")
            matching_lines.append(FileSearchMatch.from_dict(cast(MutableMapping[str, Any], item)))
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


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileStoreEntry(SerializationMixin):
    """Represent one entry in a directory listing: a file or a subdirectory."""

    #: ``type`` value for a file entry.
    FILE: ClassVar[str] = "file"
    #: ``type`` value for a subdirectory entry.
    DIRECTORY: ClassVar[str] = "directory"

    name: str
    type: str

    def __init__(self, name: str, type: str) -> None:
        """Initialize one directory-listing entry.

        Args:
            name: The entry's name (not a full path), relative to the directory
                being listed.
            type: Either ``"file"`` or ``"directory"`` (see :attr:`FILE` and
                :attr:`DIRECTORY`).
        """
        if type not in (FileStoreEntry.FILE, FileStoreEntry.DIRECTORY):
            raise ValueError(f"type must be {FileStoreEntry.FILE!r} or {FileStoreEntry.DIRECTORY!r}, got {type!r}.")
        self.name = name
        self.type = type

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Serialize this entry to a JSON-compatible dictionary.

        Overrides :meth:`SerializationMixin.to_dict` for the same reason as
        :meth:`FileSearchResult.to_dict`: to emit an explicit payload without
        the auto-injected ``type`` field. The ``exclude`` / ``exclude_none``
        arguments are accepted and ignored to preserve signature
        compatibility with the mixin.
        """
        del exclude, exclude_none
        return {"name": self.name, "type": self.type}

    @classmethod
    def from_dict(
        cls, raw_entry: MutableMapping[str, Any], /, *, dependencies: MutableMapping[str, Any] | None = None
    ) -> FileStoreEntry:
        """Parse one directory-listing entry from its dict representation."""
        del dependencies
        name = raw_entry.get("name", "")
        entry_type = raw_entry.get("type")
        if not isinstance(name, str):
            raise ValueError("FileStoreEntry.name must be a string.")
        if not isinstance(entry_type, str):
            raise ValueError("FileStoreEntry.type must be a string.")
        return cls(name=name, type=entry_type)

    def __eq__(self, other: object) -> bool:
        """Return whether two entries have the same values."""
        return isinstance(other, FileStoreEntry) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        """Return a helpful debug representation."""
        return f"FileStoreEntry(name={self.name!r}, type={self.type!r})"


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

    for line_number, line in enumerate(lines, start=1):
        match = regex.search(line)
        if match is not None:
            matching_lines.append(FileSearchMatch(line_number=line_number, line=line.rstrip("\r")))
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
    async def write(self, path: str, content: str, *, overwrite: bool = True) -> None:
        """Write ``content`` to the file at ``path``.

        Args:
            path: The relative path of the file to write.
            content: The content to write to the file.

        Keyword Args:
            overwrite: When ``True`` (default) any existing file is replaced.
                When ``False`` the implementation must perform an atomic
                exclusive create and raise :class:`FileExistsError` if a file
                already exists at ``path``.

        Raises:
            FileExistsError: When ``overwrite`` is ``False`` and a file already
                exists at ``path``.
        """

    @abstractmethod
    async def read(self, path: str) -> str | None:
        """Read the content of the file at ``path``.

        Args:
            path: The relative path of the file to read.

        Returns:
            The file content, or ``None`` if the file does not exist.
        """

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete the file at ``path``.

        Args:
            path: The relative path of the file to delete.

        Returns:
            ``True`` if the file was deleted; ``False`` if it did not exist.
        """

    @abstractmethod
    async def list_children(self, directory: str = "") -> list[FileStoreEntry]:
        """List the direct child files and subdirectories of ``directory``.

        Args:
            directory: The relative directory path to list. Use ``""`` for the root.

        Returns:
            The direct children of ``directory`` as :class:`FileStoreEntry`
            instances (names only, not full paths), each tagged as a file or a
            directory. Implementations should return subdirectories before files.
        """

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Return whether a file exists at ``path``.

        Args:
            path: The relative path of the file to check.
        """

    @abstractmethod
    async def search(
        self,
        directory: str,
        regex_pattern: str,
        glob_pattern: str | None = None,
        *,
        recursive: bool = False,
    ) -> list[FileSearchResult]:
        """Search files in ``directory`` for content matching ``regex_pattern``.

        Args:
            directory: The relative directory to search. Use ``""`` for the root.
            regex_pattern: A regular expression matched against file contents
                (case-insensitive). For example, ``"error|warning"`` matches lines
                containing ``"error"`` or ``"warning"``.
            glob_pattern: An optional glob pattern (case-insensitive) used to
                filter which files are searched. The pattern is matched against
                each file's path **relative to** ``directory`` (forward slashes).
                When ``None`` or blank, every file in scope is searched.

        Keyword Args:
            recursive: When ``False`` (default) only the direct children of
                ``directory`` are searched. When ``True`` every descendant file is
                searched.

        Returns:
            The list of files whose content matched, with snippet and matching
            line metadata. Each result's ``file_name`` is the path relative to
            ``directory`` (forward slashes).
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
        # Keys are case-insensitive (normalized + lowercased) so the store
        # behaves consistently on case-insensitive deployments. Each entry
        # also records the *original* normalized path so ``list_children`` and
        # ``search`` return display names that match what the caller
        # wrote, mirroring how :class:`FileSystemAgentFileStore` preserves the
        # on-disk casing.
        self._files: dict[str, tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(path: str) -> str:
        return _normalize_relative_path(path).lower()

    async def write(self, path: str, content: str, *, overwrite: bool = True) -> None:
        """Write ``content`` to the file at ``path``.

        When ``overwrite`` is ``False`` the check-and-write happens under the
        store lock so concurrent callers cannot both observe a missing file
        and race to create it.
        """
        display = _normalize_relative_path(path)
        key = display.lower()
        async with self._lock:
            if not overwrite and key in self._files:
                raise FileExistsError(f"File already exists: {path!r}")
            self._files[key] = (display, content)

    async def read(self, path: str) -> str | None:
        """Return the file content, or ``None`` if the file does not exist."""
        key = self._key(path)
        async with self._lock:
            entry = self._files.get(key)
        return entry[1] if entry is not None else None

    async def delete(self, path: str) -> bool:
        """Delete the file and return whether anything was removed."""
        key = self._key(path)
        async with self._lock:
            return self._files.pop(key, None) is not None

    async def list_children(self, directory: str = "") -> list[FileStoreEntry]:
        """Return the direct child files and subdirectories of ``directory``.

        Subdirectories are returned before files. Entry names preserve the
        *original-case* paths that were written, so a caller that does
        ``write("Plan.MD", ...)`` then ``list_children()`` gets back ``"Plan.MD"``
        rather than ``"plan.md"``. This matches the behaviour of
        :class:`FileSystemAgentFileStore` on case-preserving filesystems.

        A subdirectory is the first path segment of any stored key whose
        remainder (after the directory prefix) still contains a ``/`` separator;
        distinct first segments are de-duplicated case-insensitively.
        """
        prefix = _normalize_relative_path(directory, is_directory=True).lower()
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        async with self._lock:
            entries = [(key, display) for key, (display, _) in self._files.items()]
        files: list[str] = []
        directories: list[str] = []
        seen_dirs: set[str] = set()
        for key, display in entries:
            if not key.startswith(prefix):
                continue
            remainder = key[len(prefix) :]
            separator_index = remainder.find("/")
            if separator_index == -1:
                # ``display`` is the original-case normalized path; strip the
                # directory prefix using the same length we matched on ``key``.
                files.append(display[len(prefix) :])
            elif separator_index > 0:
                segment_key = remainder[:separator_index]
                if segment_key in seen_dirs:
                    continue
                seen_dirs.add(segment_key)
                directories.append(display[len(prefix) : len(prefix) + separator_index])
        results: list[FileStoreEntry] = [FileStoreEntry(name, FileStoreEntry.DIRECTORY) for name in directories]
        results.extend(FileStoreEntry(name, FileStoreEntry.FILE) for name in files)
        return results

    async def file_exists(self, path: str) -> bool:
        """Return whether the file exists."""
        key = self._key(path)
        async with self._lock:
            return key in self._files

    async def search(
        self,
        directory: str,
        regex_pattern: str,
        glob_pattern: str | None = None,
        *,
        recursive: bool = False,
    ) -> list[FileSearchResult]:
        """Search file contents for ``regex_pattern`` matches.

        Snapshots the entries under the store lock and offloads the regex scan
        to a worker thread with a bounded timeout so a pathological pattern
        cannot stall the event loop. Returned :class:`FileSearchResult`
        instances use the *original-case* file names so the result mirrors
        what :class:`FileSystemAgentFileStore` would produce. The glob and each
        result's ``file_name`` are relative to ``directory``; when ``recursive``
        is ``True`` all descendants are searched and the relative path may
        contain ``/`` separators.
        """
        prefix = _normalize_relative_path(directory, is_directory=True).lower()
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        regex = _compile_search_regex(regex_pattern)

        async with self._lock:
            entries = [(key, display, content) for key, (display, content) in self._files.items()]

        def scan() -> list[FileSearchResult]:
            results: list[FileSearchResult] = []
            for key, display, file_content in entries:
                if not key.startswith(prefix):
                    continue
                relative_key = key[len(prefix) :]
                if not recursive and "/" in relative_key:
                    continue
                relative_display = display[len(prefix) :]
                if not _matches_glob(relative_display, glob_pattern):
                    continue
                result = _search_file_content(relative_display, file_content, regex)
                if result is not None:
                    results.append(result)
            return results

        return await _run_search_with_timeout(scan)

    async def create_directory(self, path: str) -> None:
        """No-op: directories are implicit from file paths in the in-memory store."""
        del path


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileSystemAgentFileStore(AgentFileStore):
    """A disk-backed :class:`AgentFileStore` rooted under a configurable directory.

    All paths are resolved relative to the root directory provided at
    construction time. Lexical path traversal attempts (for example, via ``..``
    segments or absolute paths) are rejected with :class:`ValueError`. The root
    directory is created lazily on the first write (or ``create_directory``)
    rather than at construction, so constructing a store never touches the
    filesystem and is safe in read-only working directories.

    Symbolic links and reparse points anywhere along the resolved path are
    rejected on read, write, delete, list, and existence checks. The check is
    a probe followed by an open: on POSIX the open also passes ``O_NOFOLLOW``
    so the kernel refuses if the leaf segment becomes a symlink between the
    probe and the open. On Windows the protection is best-effort: it covers
    the static case (a symlink already exists when the call is made) but
    cannot cover an adversarial caller that swaps a parent directory for a
    symlink between the probe and the file open. This store is designed for
    single-tenant or co-operating-tenant use; it is not a sandbox against a
    hostile process that shares the root directory.
    """

    def __init__(self, root_directory: str | os.PathLike[str]) -> None:
        """Initialize the file-system store.

        The root directory is **not** created here; construction performs no
        filesystem writes. The directory is created lazily on the first
        ``write`` (or ``create_directory``) call, so a store can be
        constructed in a read-only working directory and only fails if a write
        is actually attempted.

        Args:
            root_directory: The directory under which all files are stored.
                Created lazily on first write if it does not exist.
        """
        raw_root = os.fspath(root_directory)
        if not raw_root or not raw_root.strip():
            raise ValueError("root_directory must not be empty or whitespace-only.")
        root_path = Path(raw_root).resolve()
        self._root_path = root_path

    @property
    def root_path(self) -> Path:
        """Return the resolved root directory."""
        return self._root_path

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """Resolve a relative file path safely under the root directory.

        Symbolic links and reparse points are detected on the *unresolved* path
        before any call to :meth:`~pathlib.Path.resolve`. ``Path.resolve``
        collapses symbolic links, so probing for them on a resolved path would
        either silently follow in-root symlinks or produce a misleading
        "escapes the root" error for out-of-root targets. Checking the
        unresolved candidate first keeps the rejection deterministic and gives
        the caller the specific symlink error.

        The probe is followed by the actual open, so there is an unavoidable
        race window in which a concurrent writer on the host can swap an
        intermediate path segment for a symlink. The open path mitigates the
        common case by passing ``O_NOFOLLOW`` on POSIX so the kernel refuses
        if the *leaf* segment becomes a symlink between the probe and the
        open. The Windows ``open`` API has no equivalent flag and intermediate
        directory swaps cannot be closed from user space on either platform.
        """
        normalized = _normalize_relative_path(relative_path)
        candidate = self._root_path / normalized
        self._throw_if_contains_symlink(candidate)
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self._root_path)
        except ValueError as exc:
            raise ValueError(f"Invalid path: {relative_path!r}. The resolved path escapes the root directory.") from exc
        return resolved

    def _resolve_safe_directory_path(self, relative_directory: str) -> Path:
        """Resolve a relative directory path safely under the root directory.

        Empty and whitespace-only inputs both resolve to the root directory,
        matching the behavior of ``_normalize_relative_path(..., is_directory=True)``
        and the convention used by :class:`InMemoryAgentFileStore`.
        """
        normalized = _normalize_relative_path(relative_directory, is_directory=True)
        if not normalized:
            return self._root_path
        return self._resolve_safe_path(normalized)

    def _throw_if_contains_symlink(self, candidate: Path) -> None:
        """Reject any segment between the root and ``candidate`` that is a symlink/reparse point.

        Walks each ancestor down from the root on the *unresolved* candidate so
        ``Path.is_symlink`` observes the on-disk entries instead of their
        canonical targets. Stops once a segment does not exist on disk so write
        scenarios remain allowed. ``Path.is_symlink`` detects both POSIX
        symlinks and Windows reparse points (junctions).
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
                is_link = current.is_symlink()
            except OSError as exc:
                # Fail closed: if we cannot verify whether a segment is a
                # symlink/reparse point we refuse the operation rather than
                # silently allow access that may escape the root.
                raise ValueError(
                    f"Invalid path: unable to verify whether '{segment}' is a symbolic link or reparse point."
                ) from exc
            if is_link:
                raise ValueError("Invalid path: the resolved path contains a symbolic link or reparse point.")
            if not current.exists():
                break

    async def write(self, path: str, content: str, *, overwrite: bool = True) -> None:
        """Write ``content`` to the file at ``path``.

        When ``overwrite`` is ``False`` the file is created using
        ``O_CREAT | O_EXCL`` so the underlying ``open`` call performs an
        atomic exclusive create and raises :class:`FileExistsError` if a file
        already exists. On POSIX the open additionally passes ``O_NOFOLLOW``
        so the kernel refuses to overwrite or replace a leaf symlink, closing
        the obvious probe-then-open race for the file itself.
        """
        full_path = self._resolve_safe_path(path)
        await asyncio.to_thread(self._write_file_sync, full_path, content, overwrite)

    @staticmethod
    def _write_file_sync(full_path: Path, content: str, overwrite: bool) -> None:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT
        if overwrite:
            flags |= os.O_TRUNC
        else:
            flags |= os.O_EXCL
        # ``O_NOFOLLOW`` is POSIX-only; on Windows ``Path.is_symlink`` /
        # reparse-point detection in :meth:`_throw_if_contains_symlink` is the
        # only line of defence for the leaf segment.
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        flags |= nofollow
        try:
            fd = os.open(full_path, flags, 0o644)
        except OSError as exc:
            if not overwrite and isinstance(exc, FileExistsError):
                raise
            # ``ELOOP`` (POSIX): the open refused because the leaf is a
            # symlink. Surface the same message as the static symlink probe so
            # the caller's exception-handling path is uniform.
            if nofollow and getattr(exc, "errno", None) == _ELOOP:
                raise ValueError("Invalid path: the resolved path contains a symbolic link or reparse point.") from exc
            raise
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)

    async def read(self, path: str) -> str | None:
        """Return the file content, or ``None`` if the file does not exist.

        Raises :class:`ValueError` if the file exists but its bytes are not
        valid UTF-8. Tooling that calls this on possibly-binary content should
        catch :class:`ValueError` and present the failure to the agent as a
        recoverable string response rather than a stack trace.
        """
        full_path = self._resolve_safe_path(path)
        return await asyncio.to_thread(self._read_file_sync, full_path)

    @staticmethod
    def _read_file_sync(full_path: Path) -> str | None:
        if not full_path.is_file():
            return None
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(full_path, os.O_RDONLY | nofollow)
        except OSError as exc:
            if nofollow and getattr(exc, "errno", None) == _ELOOP:
                raise ValueError("Invalid path: the resolved path contains a symbolic link or reparse point.") from exc
            raise
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"File '{full_path.name}' is not UTF-8 text and cannot be read.") from exc

    async def delete(self, path: str) -> bool:
        """Delete the file and return whether anything was removed."""
        full_path = self._resolve_safe_path(path)
        return await asyncio.to_thread(self._delete_file_sync, full_path)

    @staticmethod
    def _delete_file_sync(full_path: Path) -> bool:
        if not full_path.is_file():
            return False
        full_path.unlink()
        return True

    async def list_children(self, directory: str = "") -> list[FileStoreEntry]:
        """Return the direct child files and subdirectories of ``directory``.

        Subdirectories are returned before files. Symlinked entries (and reparse
        points on Windows) are excluded so a listing cannot surface a path that
        escapes the root. An empty list is returned for a non-existent directory.
        """
        full_dir = self._resolve_safe_directory_path(directory)
        return await asyncio.to_thread(self._list_sync, full_dir)

    @staticmethod
    def _list_sync(full_dir: Path) -> list[FileStoreEntry]:
        if not full_dir.is_dir():
            return []
        directories: list[FileStoreEntry] = []
        files: list[FileStoreEntry] = []
        for entry in full_dir.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_dir():
                directories.append(FileStoreEntry(entry.name, FileStoreEntry.DIRECTORY))
            elif entry.is_file():
                files.append(FileStoreEntry(entry.name, FileStoreEntry.FILE))
        return directories + files

    async def file_exists(self, path: str) -> bool:
        """Return whether the file exists."""
        full_path = self._resolve_safe_path(path)
        return await asyncio.to_thread(self._file_exists_sync, full_path)

    @staticmethod
    def _file_exists_sync(full_path: Path) -> bool:
        return full_path.is_file()

    async def search(
        self,
        directory: str,
        regex_pattern: str,
        glob_pattern: str | None = None,
        *,
        recursive: bool = False,
    ) -> list[FileSearchResult]:
        """Search file contents for ``regex_pattern`` matches.

        Files whose bytes are not valid UTF-8 are skipped (so a single binary
        file does not abort the whole directory search). Each skip is logged at
        ``WARNING`` level and a summary is logged at ``INFO`` so operators can
        tell the difference between "no matches" and "the corpus was largely
        not searchable". The glob and each result's ``file_name`` are the file's
        path relative to ``directory`` (forward slashes); when ``recursive`` is
        ``True`` all descendant files are searched, otherwise only the direct
        children.
        """
        full_dir = self._resolve_safe_directory_path(directory)
        regex = _compile_search_regex(regex_pattern)
        return await _run_search_with_timeout(lambda: self._search_files_sync(full_dir, regex, glob_pattern, recursive))

    @staticmethod
    def _enumerate_search_files(full_dir: Path, recursive: bool) -> list[tuple[str, Path]]:
        """Enumerate ``(relative_name, path)`` for files to search under ``full_dir``.

        Symlinked files and symlinked directories (reparse points on Windows)
        are skipped so the search cannot read or descend outside the root.
        ``relative_name`` is the file's path relative to ``full_dir`` using
        forward slashes.
        """
        found: list[tuple[str, Path]] = []
        directories: list[Path] = [full_dir]
        while directories:
            current = directories.pop()
            for entry in current.iterdir():
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if recursive:
                        directories.append(entry)
                    continue
                if entry.is_file():
                    relative_name = entry.relative_to(full_dir).as_posix()
                    found.append((relative_name, entry))
        return found

    @staticmethod
    def _search_files_sync(
        full_dir: Path, regex: re.Pattern[str], glob_pattern: str | None, recursive: bool
    ) -> list[FileSearchResult]:
        if not full_dir.is_dir():
            return []
        results: list[FileSearchResult] = []
        skipped: list[str] = []
        for relative_name, entry in FileSystemAgentFileStore._enumerate_search_files(full_dir, recursive):
            if not _matches_glob(relative_name, glob_pattern):
                continue
            try:
                file_content = entry.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Skip binary or otherwise non-UTF-8 files so a single
                # un-decodable entry doesn't abort the whole directory search.
                # Log per file so operators can audit which files were skipped.
                logger.warning("Skipping non-UTF-8 file during search: %s", entry)
                skipped.append(relative_name)
                continue
            result = _search_file_content(relative_name, file_content, regex)
            if result is not None:
                results.append(result)
        if skipped:
            logger.info(
                "Search under %s skipped %d non-UTF-8 file(s) (matched %d).",
                full_dir,
                len(skipped),
                len(results),
            )
        return results

    async def create_directory(self, path: str) -> None:
        """Ensure the directory at ``path`` exists, creating it if necessary."""
        full_path = self._resolve_safe_directory_path(path)
        await asyncio.to_thread(lambda: full_path.mkdir(parents=True, exist_ok=True))


class _WriteFileInput(BaseModel):
    """Input schema for ``file_access_write``."""

    file_name: Annotated[str, Field(description="Name (relative path) of the file to write.")]
    content: Annotated[str, Field(description="Full text content to write to the file.")]
    overwrite: Annotated[
        bool,
        Field(default=False, description="When true, replace an existing file; otherwise writing fails if it exists."),
    ] = False


class _ReadFileInput(BaseModel):
    """Input schema for ``file_access_read``."""

    file_name: Annotated[str, Field(description="Name (relative path) of the file to read.")]


class _DeleteFileInput(BaseModel):
    """Input schema for ``file_access_delete``."""

    file_name: Annotated[str, Field(description="Name (relative path) of the file to delete.")]


class _ListInput(BaseModel):
    """Input schema for ``file_access_ls``."""

    directory: Annotated[
        str | None,
        Field(default=None, description="Relative directory to list; omit or pass empty to list the root."),
    ] = None
    glob_pattern: Annotated[
        str | None,
        Field(
            default=None,
            description='Optional glob (e.g. "*.md") matched against entry names to filter the listing.',
        ),
    ] = None


class _ReplaceInput(BaseModel):
    """Input schema for ``file_access_replace``."""

    file_name: Annotated[str, Field(description="Name (relative path) of the file to modify.")]
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
    """A single literal line replacement for ``file_access_replace_lines``."""

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
    """Input schema for ``file_access_replace_lines``."""

    file_name: Annotated[str, Field(description="Name (relative path) of the file to modify.")]
    edits: Annotated[
        list[_LineEdit],
        Field(description="List of 1-based line numbers and their literal replacement text."),
    ]


class _SearchFilesInput(BaseModel):
    """Input schema for ``file_access_grep``."""

    regex_pattern: Annotated[
        str,
        Field(description="Case-insensitive regex matched against file contents; 256 characters or fewer."),
    ]
    glob_pattern: Annotated[
        str | None,
        Field(
            default=None,
            description='Optional glob to filter which files are searched (e.g. "*.md", "reports/*").',
        ),
    ] = None
    directory: Annotated[
        str | None,
        Field(default=None, description="Optional relative directory to search; omit or pass empty for the root."),
    ] = None


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileAccessProvider(ContextProvider):
    """Context provider that gives an agent CRUD/search access to a shared file store.

    The provider exposes the following tools to the agent via the per-invocation
    :class:`~agent_framework.SessionContext`:

    - ``file_access_write`` — Write a file (refuses to overwrite by default).
    - ``file_access_read`` — Read the content of a file by name.
    - ``file_access_delete`` — Delete a file by name.
    - ``file_access_ls`` — List the direct child files and subdirectories of a
      directory, optionally filtered by a glob pattern.
    - ``file_access_grep`` — Recursively search file contents using a
      case-insensitive regex, optionally filtered by a glob pattern and base directory.
    - ``file_access_replace`` — Replace occurrences of a substring within a file.
    - ``file_access_replace_lines`` — Replace whole lines within a file.

    When ``disable_write_tools`` is set, only the read-only tools (``file_access_read``,
    ``file_access_ls``, ``file_access_grep``) are advertised.

    Unlike :class:`~agent_framework.MemoryContextProvider`, which provides
    session-scoped memory that may be isolated per session,
    :class:`FileAccessProvider` operates on a shared, persistent store whose
    contents are visible across sessions and agents. The store is passed in by
    the caller and should already be scoped to the desired folder or storage
    location.

    By default all tools require approval: each is registered with
    ``approval_mode="always_require"`` so the host must approve every file
    operation the model proposes. In the auto-invocation flow this means the
    model's calls to these tools are converted into
    ``function_approval_request`` items and the tool does **not** execute until
    the host supplies a matching ``function_approval_response``. Consumers that
    use the base agent directly must install
    :class:`~agent_framework.ToolApprovalMiddleware` (or use
    :func:`~agent_framework.create_harness_agent`, which wires it in by default)
    to drive that handshake; otherwise these tools never run.

    To run unattended you can disable approval at the source with
    ``disable_readonly_tool_approval`` (read, ls, grep) and/or
    ``disable_write_tool_approval`` (write, delete, replace, replace_lines),
    which register the affected tools with ``approval_mode="never_require"``.
    Alternatively, keep approval on and supply one of the static auto-approval
    rules to :class:`~agent_framework.ToolApprovalMiddleware` via its
    ``auto_approval_rules``:

    - :meth:`read_only_tools_auto_approval_rule` — auto-approves only the
      read-only tools (read, ls, grep), while still prompting for the tools that
      modify the store (write, delete, replace, replace_lines).
    - :meth:`all_tools_auto_approval_rule` — auto-approves every file-access
      tool, including the write tools.

    For example, to auto-approve only the read-only tools::

        create_harness_agent(
            chat_client,
            auto_approval_rules=[FileAccessProvider.read_only_tools_auto_approval_rule],
        )
    """

    #: Name of the tool that writes a file.
    WRITE_TOOL_NAME = "file_access_write"
    #: Name of the tool that reads a file.
    READ_TOOL_NAME = "file_access_read"
    #: Name of the tool that deletes a file.
    DELETE_TOOL_NAME = "file_access_delete"
    #: Name of the tool that lists the files and subdirectories of a directory.
    LS_TOOL_NAME = "file_access_ls"
    #: Name of the tool that searches file contents.
    GREP_TOOL_NAME = "file_access_grep"
    #: Name of the tool that replaces a substring in a file.
    REPLACE_TOOL_NAME = "file_access_replace"
    #: Name of the tool that replaces whole lines in a file.
    REPLACE_LINES_TOOL_NAME = "file_access_replace_lines"

    #: Names of the tools that only read from (never modify) the file store.
    _READ_ONLY_TOOL_NAMES: frozenset[str] = frozenset({
        READ_TOOL_NAME,
        LS_TOOL_NAME,
        GREP_TOOL_NAME,
    })

    #: Names of the tools that modify the file store.
    _WRITE_TOOL_NAMES: frozenset[str] = frozenset({
        WRITE_TOOL_NAME,
        DELETE_TOOL_NAME,
        REPLACE_TOOL_NAME,
        REPLACE_LINES_TOOL_NAME,
    })

    #: Names of all tools exposed by this provider.
    _ALL_TOOL_NAMES: frozenset[str] = _READ_ONLY_TOOL_NAMES | _WRITE_TOOL_NAMES

    def __init__(
        self,
        store: AgentFileStore,
        *,
        source_id: str = DEFAULT_FILE_ACCESS_SOURCE_ID,
        instructions: str | None = None,
        disable_write_tools: bool = False,
        disable_readonly_tool_approval: bool = False,
        disable_write_tool_approval: bool = False,
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
            disable_write_tools: When ``True``, only the read-only tools
                (``file_access_read``, ``file_access_ls``, ``file_access_grep``)
                are advertised; the write tools (``file_access_write``,
                ``file_access_delete``, ``file_access_replace``,
                ``file_access_replace_lines``) are hidden from the model.
            disable_readonly_tool_approval: When ``True``, the read-only tools
                (``file_access_read``, ``file_access_ls``, ``file_access_grep``)
                are registered with ``approval_mode="never_require"`` so they run
                without host approval. Defaults to ``False`` (approval required).
            disable_write_tool_approval: When ``True``, the write tools
                (``file_access_write``, ``file_access_delete``,
                ``file_access_replace``, ``file_access_replace_lines``) are
                registered with ``approval_mode="never_require"`` so they run
                without host approval. Defaults to ``False`` (approval required).
        """
        super().__init__(source_id)
        self.store = store
        self.instructions = instructions or DEFAULT_FILE_ACCESS_INSTRUCTIONS
        self.disable_write_tools = disable_write_tools
        self.disable_readonly_tool_approval = disable_readonly_tool_approval
        self.disable_write_tool_approval = disable_write_tool_approval
        # Serializes mutating tool operations (write/delete/replace/replace_lines).
        # The provider is shared across sessions/agents, so read-modify-write tools
        # (replace/replace_lines) could otherwise interleave and lose updates. Note
        # this only serializes within a single event loop/process, not across
        # processes sharing a FileSystemAgentFileStore on disk.
        self._write_lock = asyncio.Lock()

    @staticmethod
    def _is_local_tool_call(function_call: Content) -> bool:
        """Return whether a function call targets this provider's local tools.

        Hosted-tool calls carry a ``server_label`` in their
        ``additional_properties`` and are a separate server-scoped approval
        boundary that must be passed through untouched (see
        :func:`agent_framework._tools._is_hosted_tool_approval`). These rules
        only ever auto-approve the provider's own local tools, so any call that
        carries a ``server_label`` is rejected even if its name collides with a
        file-access tool name.
        """
        return not function_call.additional_properties.get("server_label")

    @staticmethod
    def read_only_tools_auto_approval_rule(function_call: Content) -> bool:
        """Auto-approval rule that approves only the read-only file-access tools.

        The tools exposed by :class:`FileAccessProvider` always require approval.
        Pass this rule to :class:`~agent_framework.ToolApprovalMiddleware` (via
        ``auto_approval_rules``) to automatically approve the tools that read
        from the store (``file_access_read``, ``file_access_ls``, and
        ``file_access_grep``), while still prompting for the tools that modify it
        (``file_access_write``, ``file_access_delete``, ``file_access_replace``,
        and ``file_access_replace_lines``).

        Hosted-tool calls (those carrying a ``server_label``) are never
        auto-approved, even when their name matches a file-access tool, so the
        rule stays scoped to this provider's local tools.

        Args:
            function_call: The pending ``function_call`` content.

        Returns:
            ``True`` for read-only file-access tools, ``False`` otherwise so that
            subsequent rules continue to be evaluated.
        """
        return (
            FileAccessProvider._is_local_tool_call(function_call)
            and function_call.name in FileAccessProvider._READ_ONLY_TOOL_NAMES
        )

    @staticmethod
    def all_tools_auto_approval_rule(function_call: Content) -> bool:
        """Auto-approval rule that approves every file-access tool.

        The tools exposed by :class:`FileAccessProvider` always require approval.
        Pass this rule to :class:`~agent_framework.ToolApprovalMiddleware` (via
        ``auto_approval_rules``) to automatically approve every file-access tool,
        including the tools that modify the store (``file_access_write``,
        ``file_access_delete``, ``file_access_replace``, and
        ``file_access_replace_lines``).

        Hosted-tool calls (those carrying a ``server_label``) are never
        auto-approved, even when their name matches a file-access tool, so the
        rule stays scoped to this provider's local tools.

        Args:
            function_call: The pending ``function_call`` content.

        Returns:
            ``True`` for any file-access tool, ``False`` otherwise so that
            subsequent rules continue to be evaluated.
        """
        return (
            FileAccessProvider._is_local_tool_call(function_call)
            and function_call.name in FileAccessProvider._ALL_TOOL_NAMES
        )

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject file-access tools and instructions before the model runs."""
        readonly_approval: ApprovalMode = "never_require" if self.disable_readonly_tool_approval else "always_require"
        write_approval: ApprovalMode = "never_require" if self.disable_write_tool_approval else "always_require"

        @tool(name=FileAccessProvider.WRITE_TOOL_NAME, schema=_WriteFileInput, approval_mode=write_approval)
        async def file_access_write(file_name: str, content: str, overwrite: bool = False) -> str:
            """Write a file with the given name and content. By default, does not overwrite an existing file unless overwrite is set to true."""  # noqa: E501
            try:
                normalized = _normalize_relative_path(file_name)
                async with self._write_lock:
                    await self.store.write(normalized, content, overwrite=overwrite)
            except FileExistsError:
                return f"File '{file_name}' already exists. To replace it, write again with overwrite set to true."
            except ValueError as exc:
                return f"Could not write file '{file_name}': {exc}"
            except OSError as exc:
                return f"Could not write file '{file_name}': {exc.strerror or exc}"
            return f"File '{file_name}' written."

        @tool(name=FileAccessProvider.READ_TOOL_NAME, schema=_ReadFileInput, approval_mode=readonly_approval)
        async def file_access_read(file_name: str) -> str:
            """Read the content of a file by name. Returns the file content or a message indicating the file could not be read."""  # noqa: E501
            try:
                normalized = _normalize_relative_path(file_name)
                content = await self.store.read(normalized)
            except ValueError as exc:
                return f"Could not read file '{file_name}': {exc}"
            except OSError as exc:
                return f"Could not read file '{file_name}': {exc.strerror or exc}"
            return content if content is not None else f"File '{file_name}' not found."

        @tool(name=FileAccessProvider.DELETE_TOOL_NAME, schema=_DeleteFileInput, approval_mode=write_approval)
        async def file_access_delete(file_name: str) -> str:
            """Delete a file by name."""
            try:
                normalized = _normalize_relative_path(file_name)
                async with self._write_lock:
                    deleted = await self.store.delete(normalized)
            except ValueError as exc:
                return f"Could not delete file '{file_name}': {exc}"
            except OSError as exc:
                return f"Could not delete file '{file_name}': {exc.strerror or exc}"
            return f"File '{file_name}' deleted." if deleted else f"File '{file_name}' not found."

        @tool(name=FileAccessProvider.LS_TOOL_NAME, schema=_ListInput, approval_mode=readonly_approval)
        async def file_access_ls(
            directory: str | None = None,
            glob_pattern: str | None = None,
        ) -> list[dict[str, str]] | str:
            """List the direct child files and subdirectories of a directory. Omit ``directory`` (or pass an empty string) to list the root. To enumerate a subdirectory, pass its relative path, for example ``"reports"`` or ``"reports/2024"``. Optionally filter entries with a ``glob_pattern`` (e.g. ``"*.md"``). Subdirectories are listed before files, and each entry is ``{"name": <name>, "type": "file"|"directory"}``."""  # noqa: E501
            target = directory if directory and directory.strip() else ""
            try:
                listed = await self.store.list_children(target)
            except ValueError as exc:
                return f"Could not list directory '{directory or ''}': {exc}"
            except OSError as exc:
                return f"Could not list directory '{directory or ''}': {exc.strerror or exc}"
            return [
                {"name": entry.name, "type": entry.type} for entry in listed if _matches_glob(entry.name, glob_pattern)
            ]

        @tool(name=FileAccessProvider.REPLACE_TOOL_NAME, schema=_ReplaceInput, approval_mode=write_approval)
        async def file_access_replace(
            file_name: str,
            old_string: str,
            new_string: str,
            replace_all: bool = False,
        ) -> str:
            """Replace occurrences of old_string with new_string in a file. Fails if old_string is not found, or if it occurs more than once and replace_all is false. Returns the number of occurrences replaced."""  # noqa: E501
            try:
                normalized = _normalize_relative_path(file_name)
                async with self._write_lock:
                    content = await self.store.read(normalized)
                    if content is None:
                        return f"File '{file_name}' not found."
                    new_content, count = _apply_replace(content, old_string, new_string, replace_all)
                    await self.store.write(normalized, new_content, overwrite=True)
            except ValueError as exc:
                return f"Could not replace in file '{file_name}': {exc}"
            except OSError as exc:
                return f"Could not replace in file '{file_name}': {exc.strerror or exc}"
            return f"Replaced {count} occurrence(s) in '{file_name}'."

        @tool(
            name=FileAccessProvider.REPLACE_LINES_TOOL_NAME,
            schema=_ReplaceLinesInput,
            approval_mode=write_approval,
        )
        async def file_access_replace_lines(file_name: str, edits: list[_LineEdit]) -> str:
            """Replace lines in a file. Provide a list of edits, each with a 1-based line_number and a literal new_line (include your own trailing newline); an empty new_line deletes the line, including its line break. Fails on out-of-range or duplicate line numbers."""  # noqa: E501
            try:
                normalized = _normalize_relative_path(file_name)
                async with self._write_lock:
                    content = await self.store.read(normalized)
                    if content is None:
                        return f"File '{file_name}' not found."
                    new_content = _apply_replace_lines(content, _line_edits(edits))
                    await self.store.write(normalized, new_content, overwrite=True)
            except ValueError as exc:
                return f"Could not edit file '{file_name}': {exc}"
            except OSError as exc:
                return f"Could not edit file '{file_name}': {exc.strerror or exc}"
            return f"Replaced {len(edits)} line(s) in '{file_name}'."

        @tool(name=FileAccessProvider.GREP_TOOL_NAME, schema=_SearchFilesInput, approval_mode=readonly_approval)
        async def file_access_grep(
            regex_pattern: str,
            glob_pattern: str | None = None,
            directory: str | None = None,
        ) -> list[dict[str, Any]] | str:
            """Search the contents of files in the store using a case-insensitive regular expression.

            The search runs recursively across all subdirectories. Optionally restrict the search to a
            ``directory`` (relative path), and filter which files to search using a glob ``glob_pattern``
            matched against each file's path relative to that directory.
            The glob uses fnmatch semantics where ``*`` matches any characters including ``/``: use
            ``"*.md"`` to match markdown files at any depth,
            or ``"reports/*"`` to restrict the search to the ``reports`` subtree.
            Leave empty or omit to search all files.
            Returns matching results whose file_name values are paths relative to the store root
            (directly usable with file_access_read), along with snippets and matching lines with line numbers.
            The regex_pattern must be 256 characters or fewer.
            """
            glob_filter = glob_pattern if glob_pattern and glob_pattern.strip() else None
            target = directory if directory and directory.strip() else ""
            try:
                results = await self.store.search(target, regex_pattern, glob_filter, recursive=True)
            except ValueError as exc:
                return f"Could not search files: {exc}"
            except OSError as exc:
                return f"Could not search files: {exc.strerror or exc}"
            # ``store.search`` returns ``file_name`` relative to ``target``; re-root it to the store
            # root so the names compose directly with file_access_read/replace/delete.
            prefix = target.strip("/")
            output: list[dict[str, Any]] = []
            for result in results:
                entry = result.to_dict()
                if prefix:
                    entry["file_name"] = f"{prefix}/{entry['file_name']}"
                output.append(entry)
            return output

        context.extend_instructions(self.source_id, [self.instructions])
        tools = [file_access_read, file_access_ls, file_access_grep]
        if not self.disable_write_tools:
            tools.extend([file_access_write, file_access_delete, file_access_replace, file_access_replace_lines])
        context.extend_tools(self.source_id, tools)


__all__ = [
    "DEFAULT_FILE_ACCESS_INSTRUCTIONS",
    "DEFAULT_FILE_ACCESS_SOURCE_ID",
    "AgentFileStore",
    "FileAccessProvider",
    "FileSearchMatch",
    "FileSearchResult",
    "FileStoreEntry",
    "FileSystemAgentFileStore",
    "InMemoryAgentFileStore",
]
