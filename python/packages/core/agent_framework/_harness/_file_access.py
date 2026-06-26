# Copyright (c) Microsoft. All rights reserved.

"""File-access harness provider exposing CRUD/search tools backed by an ``AgentFileStore``.

Unlike :class:`~agent_framework.MemoryContextProvider`, which provides
session-scoped memory that may be isolated per session, :class:`FileAccessProvider`
operates on a shared, persistent storage area whose contents are visible across
sessions and agents. The provider exposes six tools — ``file_access_save_file``,
``file_access_read_file``, ``file_access_delete_file``, ``file_access_list_files``,
``file_access_list_subdirectories``, and ``file_access_search_files`` — by
registering them on the per-invocation
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
from typing import Annotated, Any, cast

from pydantic import BaseModel, Field

from .._feature_stage import ExperimentalFeature, experimental
from .._serialization import SerializationMixin
from .._sessions import AgentSession, ContextProvider, SessionContext
from .._tools import tool
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
    "- Files may be organized into subdirectories. Use `file_access_list_files` "
    "and `file_access_list_subdirectories` to explore the tree level by level, "
    "or `file_access_search_files` to search file contents recursively across "
    "the whole store."
)

# Maximum number of characters of context to include on either side of the first
# regex match when building a result snippet.
_SEARCH_SNIPPET_RADIUS = 50

# Hard cap on the length of a user-supplied search regex. Python's ``re`` module
# has no built-in timeout, so a catastrophic-backtracking pattern (such as
# ``(a+)+$``) submitted by the model could spin the CPU indefinitely. The cap
# alone does not stop short pathological patterns, so :meth:`search_files`
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


def _matches_glob(file_name: str, pattern: str | None) -> bool:
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
        """Serialize this match to a JSON-compatible dictionary.

        Overrides :meth:`SerializationMixin.to_dict` because this DTO is
        declared with ``__slots__``: the base implementation iterates
        ``self.__dict__`` which is empty for slotted classes and would emit
        only the auto-injected ``type`` field. The ``exclude`` /
        ``exclude_none`` arguments are accepted (and discarded) so the
        signature remains drop-in compatible with the mixin — callers like
        :meth:`SerializationMixin.to_json` always forward them.
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
        """Serialize this result to a JSON-compatible dictionary.

        Overrides :meth:`SerializationMixin.to_dict` for the same reason as
        :meth:`FileSearchMatch.to_dict`: this DTO uses ``__slots__`` so the
        base implementation cannot introspect the payload. The ``exclude`` /
        ``exclude_none`` arguments are accepted and ignored to preserve
        signature compatibility with the mixin.
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
    async def write_file(self, path: str, content: str, *, overwrite: bool = True) -> None:
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
    async def list_directories(self, directory: str = "") -> list[str]:
        """List the direct child subdirectory names of ``directory``.

        Args:
            directory: The relative directory path to list. Use ``""`` for the root.

        Returns:
            The list of subdirectory names (not full paths) directly contained in
            the specified directory.
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
        *,
        recursive: bool = False,
    ) -> list[FileSearchResult]:
        """Search files in ``directory`` for content matching ``regex_pattern``.

        Args:
            directory: The relative directory to search. Use ``""`` for the root.
            regex_pattern: A regular expression matched against file contents
                (case-insensitive). For example, ``"error|warning"`` matches lines
                containing ``"error"`` or ``"warning"``.
            file_pattern: An optional glob pattern (case-insensitive) used to
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
        # also records the *original* normalized path so ``list_files`` and
        # ``search_files`` return display names that match what the caller
        # wrote, mirroring how :class:`FileSystemAgentFileStore` preserves the
        # on-disk casing.
        self._files: dict[str, tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(path: str) -> str:
        return _normalize_relative_path(path).lower()

    async def write_file(self, path: str, content: str, *, overwrite: bool = True) -> None:
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

    async def read_file(self, path: str) -> str | None:
        """Return the file content, or ``None`` if the file does not exist."""
        key = self._key(path)
        async with self._lock:
            entry = self._files.get(key)
        return entry[1] if entry is not None else None

    async def delete_file(self, path: str) -> bool:
        """Delete the file and return whether anything was removed."""
        key = self._key(path)
        async with self._lock:
            return self._files.pop(key, None) is not None

    async def list_files(self, directory: str = "") -> list[str]:
        """Return the direct child files of ``directory``.

        Returns the *original-case* file names that were written, so a caller
        that does ``write_file("Plan.MD", ...)`` then ``list_files()`` gets
        back ``["Plan.MD"]`` rather than ``["plan.md"]``. This matches the
        behaviour of :class:`FileSystemAgentFileStore` on case-preserving
        filesystems.
        """
        prefix = _normalize_relative_path(directory, is_directory=True).lower()
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        async with self._lock:
            entries = [(key, display) for key, (display, _) in self._files.items()]
        results: list[str] = []
        for key, display in entries:
            if not key.startswith(prefix):
                continue
            if "/" in key[len(prefix) :]:
                continue
            # ``display`` is the original-case normalized path; strip the
            # directory prefix using the same length we matched on ``key``.
            results.append(display[len(prefix) :])
        return results

    async def list_directories(self, directory: str = "") -> list[str]:
        """Return the direct child subdirectory names of ``directory``.

        A subdirectory is the first path segment of any stored key whose
        remainder (after the directory prefix) still contains a ``/`` separator.
        Distinct first segments are collected, preserving the *original-case*
        display name and de-duplicating case-insensitively, mirroring the
        case-preserving behaviour of :class:`FileSystemAgentFileStore`.
        """
        prefix = _normalize_relative_path(directory, is_directory=True).lower()
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        async with self._lock:
            entries = [(key, display) for key, (display, _) in self._files.items()]
        results: list[str] = []
        seen: set[str] = set()
        for key, display in entries:
            if not key.startswith(prefix):
                continue
            remainder = key[len(prefix) :]
            separator_index = remainder.find("/")
            if separator_index <= 0:
                continue
            segment_key = remainder[:separator_index]
            if segment_key in seen:
                continue
            seen.add(segment_key)
            # ``display`` is the original-case normalized path; take the matching
            # first segment after the (case-insensitive) prefix.
            results.append(display[len(prefix) : len(prefix) + separator_index])
        return results

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
                if not _matches_glob(relative_display, file_pattern):
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
        ``write_file`` (or ``create_directory``) call, so a store can be
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

    async def write_file(self, path: str, content: str, *, overwrite: bool = True) -> None:
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

    async def read_file(self, path: str) -> str | None:
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

    async def list_directories(self, directory: str = "") -> list[str]:
        """Return the direct child subdirectory names of ``directory``.

        Symlinked directories (and reparse points on Windows) are excluded so a
        listing cannot surface a path that escapes the root. An empty list is
        returned for a non-existent directory.
        """
        full_dir = self._resolve_safe_directory_path(directory)
        return await asyncio.to_thread(self._list_directories_sync, full_dir)

    @staticmethod
    def _list_directories_sync(full_dir: Path) -> list[str]:
        if not full_dir.is_dir():
            return []
        names: list[str] = []
        for entry in full_dir.iterdir():
            if entry.is_symlink():
                continue
            if entry.is_dir():
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
        return await _run_search_with_timeout(lambda: self._search_files_sync(full_dir, regex, file_pattern, recursive))

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
        full_dir: Path, regex: re.Pattern[str], file_pattern: str | None, recursive: bool
    ) -> list[FileSearchResult]:
        if not full_dir.is_dir():
            return []
        results: list[FileSearchResult] = []
        skipped: list[str] = []
        for relative_name, entry in FileSystemAgentFileStore._enumerate_search_files(full_dir, recursive):
            if not _matches_glob(relative_name, file_pattern):
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


class _SaveFileInput(BaseModel):
    """Input schema for ``file_access_save_file``."""

    file_name: Annotated[str, Field(description="Name (relative path) of the file to save.")]
    content: Annotated[str, Field(description="Full text content to write to the file.")]
    overwrite: Annotated[
        bool,
        Field(default=False, description="When true, replace an existing file; otherwise saving fails if it exists."),
    ] = False


class _ReadFileInput(BaseModel):
    """Input schema for ``file_access_read_file``."""

    file_name: Annotated[str, Field(description="Name (relative path) of the file to read.")]


class _DeleteFileInput(BaseModel):
    """Input schema for ``file_access_delete_file``."""

    file_name: Annotated[str, Field(description="Name (relative path) of the file to delete.")]


class _ListFilesInput(BaseModel):
    """Input schema for ``file_access_list_files``."""

    directory: Annotated[
        str | None,
        Field(default=None, description="Relative directory to list; omit or pass empty to list the root."),
    ] = None


class _ListSubdirectoriesInput(BaseModel):
    """Input schema for ``file_access_list_subdirectories``."""

    directory: Annotated[
        str | None,
        Field(default=None, description="Relative directory to list; omit or pass empty to list the root."),
    ] = None


class _SearchFilesInput(BaseModel):
    """Input schema for ``file_access_search_files``."""

    regex_pattern: Annotated[
        str,
        Field(description="Case-insensitive regex matched against file contents; 256 characters or fewer."),
    ]
    file_pattern: Annotated[
        str | None,
        Field(
            default=None,
            description='Optional glob to filter which files are searched (e.g. "*.md", "reports/*").',
        ),
    ] = None


@experimental(feature_id=ExperimentalFeature.HARNESS)
class FileAccessProvider(ContextProvider):
    """Context provider that gives an agent CRUD/search access to a shared file store.

    The provider exposes six tools to the agent via the per-invocation
    :class:`~agent_framework.SessionContext`:

    - ``file_access_save_file`` — Save a file (refuses to overwrite by default).
    - ``file_access_read_file`` — Read the content of a file by name.
    - ``file_access_delete_file`` — Delete a file by name.
    - ``file_access_list_files`` — List the direct child file names of a directory.
    - ``file_access_list_subdirectories`` — List the direct child subdirectory
      names of a directory.
    - ``file_access_search_files`` — Recursively search file contents from the
      store root using a case-insensitive regex, optionally filtered by a glob
      pattern over the store-root-relative file paths.

    Unlike :class:`~agent_framework.MemoryContextProvider`, which provides
    session-scoped memory that may be isolated per session,
    :class:`FileAccessProvider` operates on a shared, persistent store whose
    contents are visible across sessions and agents. The store is passed in by
    the caller and should already be scoped to the desired folder or storage
    location.

    All six tools always require approval: each is registered with
    ``approval_mode="always_require"`` so the host must approve every file
    operation the model proposes. In the auto-invocation flow this means the
    model's calls to these tools are converted into
    ``function_approval_request`` items and the tool does **not** execute until
    the host supplies a matching ``function_approval_response``. Consumers that
    use the base agent directly must install
    :class:`~agent_framework.ToolApprovalMiddleware` (or use
    :func:`~agent_framework.create_harness_agent`, which wires it in by default)
    to drive that handshake; otherwise these tools never run. To run unattended,
    supply one of the static auto-approval rules to
    :class:`~agent_framework.ToolApprovalMiddleware` via its
    ``auto_approval_rules``:

    - :meth:`read_only_tools_auto_approval_rule` — auto-approves only the
      read-only tools (read, list files, list subdirectories, search), while
      still prompting for the tools that modify the store (save and delete).
    - :meth:`all_tools_auto_approval_rule` — auto-approves every file-access
      tool, including save and delete.

    For example, to auto-approve only the read-only tools::

        create_harness_agent(
            chat_client,
            auto_approval_rules=[FileAccessProvider.read_only_tools_auto_approval_rule],
        )
    """

    #: Name of the tool that saves a file.
    SAVE_FILE_TOOL_NAME = "file_access_save_file"
    #: Name of the tool that reads a file.
    READ_FILE_TOOL_NAME = "file_access_read_file"
    #: Name of the tool that deletes a file.
    DELETE_FILE_TOOL_NAME = "file_access_delete_file"
    #: Name of the tool that lists the files in a directory.
    LIST_FILES_TOOL_NAME = "file_access_list_files"
    #: Name of the tool that lists the subdirectories of a directory.
    LIST_SUBDIRECTORIES_TOOL_NAME = "file_access_list_subdirectories"
    #: Name of the tool that searches file contents.
    SEARCH_FILES_TOOL_NAME = "file_access_search_files"

    #: Names of the tools that only read from (never modify) the file store.
    _READ_ONLY_TOOL_NAMES: frozenset[str] = frozenset({
        READ_FILE_TOOL_NAME,
        LIST_FILES_TOOL_NAME,
        LIST_SUBDIRECTORIES_TOOL_NAME,
        SEARCH_FILES_TOOL_NAME,
    })

    #: Names of all tools exposed by this provider.
    _ALL_TOOL_NAMES: frozenset[str] = frozenset({
        SAVE_FILE_TOOL_NAME,
        READ_FILE_TOOL_NAME,
        DELETE_FILE_TOOL_NAME,
        LIST_FILES_TOOL_NAME,
        LIST_SUBDIRECTORIES_TOOL_NAME,
        SEARCH_FILES_TOOL_NAME,
    })

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
        from the store (``file_access_read_file``, ``file_access_list_files``,
        ``file_access_list_subdirectories``, and ``file_access_search_files``),
        while still prompting for the tools that modify it
        (``file_access_save_file`` and ``file_access_delete_file``).

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
        including the tools that modify the store (``file_access_save_file`` and
        ``file_access_delete_file``).

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

        @tool(name=FileAccessProvider.SAVE_FILE_TOOL_NAME, schema=_SaveFileInput, approval_mode="always_require")
        async def file_access_save_file(file_name: str, content: str, overwrite: bool = False) -> str:
            """Save a file with the given name and content. By default, does not overwrite an existing file unless overwrite is set to true."""  # noqa: E501
            try:
                normalized = _normalize_relative_path(file_name)
                await self.store.write_file(normalized, content, overwrite=overwrite)
            except FileExistsError:
                return f"File '{file_name}' already exists. To replace it, save again with overwrite set to true."
            except ValueError as exc:
                return f"Could not save file '{file_name}': {exc}"
            except OSError as exc:
                return f"Could not save file '{file_name}': {exc.strerror or exc}"
            return f"File '{file_name}' saved."

        @tool(name=FileAccessProvider.READ_FILE_TOOL_NAME, schema=_ReadFileInput, approval_mode="always_require")
        async def file_access_read_file(file_name: str) -> str:
            """Read the content of a file by name. Returns the file content or a message indicating the file could not be read."""  # noqa: E501
            try:
                normalized = _normalize_relative_path(file_name)
                content = await self.store.read_file(normalized)
            except ValueError as exc:
                return f"Could not read file '{file_name}': {exc}"
            except OSError as exc:
                return f"Could not read file '{file_name}': {exc.strerror or exc}"
            return content if content is not None else f"File '{file_name}' not found."

        @tool(name=FileAccessProvider.DELETE_FILE_TOOL_NAME, schema=_DeleteFileInput, approval_mode="always_require")
        async def file_access_delete_file(file_name: str) -> str:
            """Delete a file by name."""
            try:
                normalized = _normalize_relative_path(file_name)
                deleted = await self.store.delete_file(normalized)
            except ValueError as exc:
                return f"Could not delete file '{file_name}': {exc}"
            except OSError as exc:
                return f"Could not delete file '{file_name}': {exc.strerror or exc}"
            return f"File '{file_name}' deleted." if deleted else f"File '{file_name}' not found."

        @tool(name=FileAccessProvider.LIST_FILES_TOOL_NAME, schema=_ListFilesInput, approval_mode="always_require")
        async def file_access_list_files(directory: str | None = None) -> list[str] | str:
            """List the direct child file names of a directory. Omit ``directory`` (or pass an empty string) to list the root. To enumerate files in a subdirectory, pass its relative path, for example ``"reports"`` or ``"reports/2024"``."""  # noqa: E501
            target = directory if directory and directory.strip() else ""
            try:
                return await self.store.list_files(target)
            except ValueError as exc:
                return f"Could not list directory '{directory or ''}': {exc}"
            except OSError as exc:
                return f"Could not list directory '{directory or ''}': {exc.strerror or exc}"

        @tool(
            name=FileAccessProvider.LIST_SUBDIRECTORIES_TOOL_NAME,
            schema=_ListSubdirectoriesInput,
            approval_mode="always_require",
        )
        async def file_access_list_subdirectories(directory: str | None = None) -> list[str] | str:
            """List the direct child subdirectory names of a directory.

            Omit ``directory`` (or pass an empty string) to list the root.
            To enumerate subdirectories of a subdirectory, pass its relative path, for example
            ``"reports"`` or ``"reports/2024"``.
            Use this together with file_access_list_files to explore the directory tree level by level.
            """
            target = directory if directory and directory.strip() else ""
            try:
                return await self.store.list_directories(target)
            except ValueError as exc:
                return f"Could not list directory '{directory or ''}': {exc}"
            except OSError as exc:
                return f"Could not list directory '{directory or ''}': {exc.strerror or exc}"

        @tool(name=FileAccessProvider.SEARCH_FILES_TOOL_NAME, schema=_SearchFilesInput, approval_mode="always_require")
        async def file_access_search_files(
            regex_pattern: str,
            file_pattern: str | None = None,
        ) -> list[dict[str, Any]] | str:
            """Search the contents of all files in the store using a case-insensitive regular expression.

            The search runs recursively across all subdirectories.
            Optionally filter which files to search using a glob pattern matched against each file's
            path relative to the store root.
            The glob uses fnmatch semantics where ``*`` matches any characters including ``/``: use
            ``"*.md"`` to match markdown files at any depth,
            or ``"reports/*"`` to restrict the search to the ``reports`` subtree.
            Leave empty or omit to search all files.
            Returns matching results whose file_name values are paths relative to the store root
            (usable with file_access_read_file),
            along with snippets and matching lines with line numbers. The regex_pattern must be
            256 characters or fewer.
            """
            pattern = file_pattern if file_pattern and file_pattern.strip() else None
            try:
                results = await self.store.search_files("", regex_pattern, pattern, recursive=True)
            except ValueError as exc:
                return f"Could not search files: {exc}"
            except OSError as exc:
                return f"Could not search files: {exc.strerror or exc}"
            return [result.to_dict() for result in results]

        context.extend_instructions(self.source_id, [self.instructions])
        context.extend_tools(
            self.source_id,
            [
                file_access_save_file,
                file_access_read_file,
                file_access_delete_file,
                file_access_list_files,
                file_access_list_subdirectories,
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
