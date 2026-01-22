# Copyright (c) Microsoft. All rights reserved.

import os
import platform
import re
import shlex
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, NamedTuple, TypedDict

from ._tools import BaseTool

if TYPE_CHECKING:
    from ._tools import AIFunction
    from ._types import Content

__all__ = [
    "DEFAULT_DENYLIST_PATTERNS",
    "DEFAULT_SHELL_MAX_OUTPUT_BYTES",
    "DEFAULT_SHELL_TIMEOUT_SECONDS",
    "ShellExecutor",
    "ShellTool",
    "ShellToolOptions",
]

# Type alias for command patterns: str for prefix matching, Pattern for regex
CommandPattern = str | re.Pattern[str]

# Default configuration values
DEFAULT_SHELL_TIMEOUT_SECONDS = 60
DEFAULT_SHELL_MAX_OUTPUT_BYTES = 50 * 1024  # 50 KB

# Default denylist of dangerous command patterns
DEFAULT_DENYLIST_PATTERNS: list[CommandPattern] = [
    # Recursive deletion of root or important directories
    re.compile(r"rm\s+(-[rf]+\s+)*/\s*$"),
    re.compile(r"rm\s+(-[rf]+\s+)*(~|/home|/root|/etc|/var|/usr)\s*$"),
    re.compile(r"rmdir\s+/s\s+/q\s+[A-Za-z]:\\$", re.IGNORECASE),
    re.compile(r"del\s+/f\s+/s\s+/q\s+[A-Za-z]:\\$", re.IGNORECASE),
]


_SHELL_METACHAR_PATTERN = re.compile(r"[;|&`$()]")


def _matches_pattern(pattern: CommandPattern, command: str) -> bool:
    """Check if a command matches a pattern.

    For regex patterns, uses full regex matching.
    For string patterns, extracts the first command token and checks if it
    matches the pattern exactly.
    """
    if isinstance(pattern, re.Pattern):
        return bool(pattern.search(command))

    # First, get the first whitespace-delimited token
    parts = command.split(None, 1)  # Split on whitespace, max 1 split
    if not parts:
        return False
    first_part = parts[0]

    # Strip any trailing shell metacharacters from the first part
    first_cmd = first_part.rstrip(";|&")

    # If the first part contained shell metacharacters, the command is
    # attempting chaining - don't match
    if first_cmd != first_part:
        # The command has a metacharacter attached (e.g., "ls;")
        # Check if base command matches but still block due to chaining
        base_cmd = os.path.basename(first_cmd)
        if base_cmd == pattern or first_cmd == pattern:
            # Would match, but has chaining - reject
            return False

    # Check for shell metacharacters in the rest of the command
    # These indicate command chaining which should not be allowlisted
    remaining = parts[1] if len(parts) > 1 else ""
    if remaining and _SHELL_METACHAR_PATTERN.search(remaining):
        return False

    # Handle paths like /usr/bin/ls -> ls
    base_cmd = os.path.basename(first_cmd)

    # Check if the base command matches the pattern exactly
    if base_cmd == pattern or first_cmd == pattern:
        return True

    # Also allow pattern as a prefix of the command name (e.g., "git" matches "git-upload-pack")
    return bool(base_cmd.startswith(pattern + "-") or first_cmd.startswith(pattern + "-"))


def _contains_privilege_command(command: str, privilege_commands: frozenset[str]) -> bool:
    """Check if command contains privilege escalation using token-based parsing."""
    try:
        tokens = shlex.split(command)
        for token in tokens:
            # Check the token itself and handle paths like /usr/bin/sudo
            base_name = os.path.basename(token)
            if base_name in privilege_commands or token in privilege_commands:
                return True
    except ValueError:
        # shlex.split can fail on malformed input; fall through to pattern matching
        pass
    return False


class _ValidationResult(NamedTuple):
    """Internal result of command validation."""

    is_valid: bool
    error_message: str | None = None

    def __bool__(self) -> bool:
        return self.is_valid


class ShellToolOptions(TypedDict, total=False):
    """Configuration options for ShellTool.

    Attributes:
        working_directory: Default working directory for command execution.
        timeout_seconds: Command execution timeout in seconds. Defaults to 60.
        max_output_bytes: Maximum output size before truncation. Defaults to 50KB.
        approval_mode: Human-in-the-loop approval mode. Defaults to "always_require".
        allowlist_patterns: List of allowed command patterns (str for prefix, re.Pattern for regex).
        denylist_patterns: List of denied command patterns.
        allowed_paths: Paths that commands can access.
        blocked_paths: Paths that commands cannot access (takes precedence).
        block_privilege_escalation: Block sudo/runas commands. Defaults to True.
        capture_stderr: Capture stderr output. Defaults to True.
    """

    working_directory: str | None
    timeout_seconds: int
    max_output_bytes: int
    approval_mode: Literal["always_require", "never_require"]
    allowlist_patterns: list[CommandPattern]
    denylist_patterns: list[CommandPattern]
    allowed_paths: list[str]
    blocked_paths: list[str]
    block_privilege_escalation: bool
    capture_stderr: bool


class ShellExecutor(ABC):
    """Abstract base class for shell command executors."""

    @abstractmethod
    async def execute(
        self,
        commands: list[str],
        *,
        working_directory: str | None = None,
        timeout_seconds: int = DEFAULT_SHELL_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_SHELL_MAX_OUTPUT_BYTES,
        capture_stderr: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute shell commands.

        Args:
            commands: List of commands to execute.

        Keyword Args:
            working_directory: Working directory for the commands.
            timeout_seconds: Timeout in seconds per command.
            max_output_bytes: Maximum output size in bytes per command.
            capture_stderr: Whether to capture stderr.

        Returns:
            List of output dictionaries containing the command outputs.
        """
        ...


# Unix privilege escalation commands
_UNIX_PRIVILEGE_COMMANDS = frozenset({"sudo", "su", "doas", "pkexec"})

# Unix privilege escalation patterns
_UNIX_PRIVILEGE_PATTERNS: list[CommandPattern] = [
    re.compile(r"^sudo\s"),
    re.compile(r"^su\s"),
    re.compile(r"^doas\s"),
    re.compile(r"^pkexec\s"),
    re.compile(r"\|\s*sudo\s"),
    re.compile(r"&&\s*sudo\s"),
    re.compile(r";\s*sudo\s"),
    # Shell wrapper patterns to prevent bypass via sh -c 'sudo ...', eval, etc.
    re.compile(r"\b(sh|bash|dash|zsh|ksh|csh|tcsh)\s+(-\w+\s+)*-c\s+['\"].*\b(sudo|su|doas|pkexec)\b"),
    re.compile(r"\beval\s+['\"].*\b(sudo|su|doas|pkexec)\b"),
    re.compile(r"\bexec\s+(sudo|su|doas|pkexec)\b"),
    # Command substitution patterns
    re.compile(r"\$\(.*\b(sudo|su|doas|pkexec)\b"),
    re.compile(r"`.*\b(sudo|su|doas|pkexec)\b"),
    # Environment variable prefix
    re.compile(r"^\w+=\S*\s+sudo\s"),
    # Utility wrappers
    re.compile(r"\b(env|nohup|time)\s+sudo\b"),
    re.compile(r"\bxargs\s+.*\bsudo\b"),
    re.compile(r"\bfind\b.*-exec\s+sudo\b"),
]

# Windows privilege escalation commands
_WINDOWS_PRIVILEGE_COMMANDS = frozenset({"runas", "gsudo"})

# Windows privilege escalation patterns
_WINDOWS_PRIVILEGE_PATTERNS: list[CommandPattern] = [
    re.compile(r"^runas\s+/"),
    re.compile(r"Start-Process\s+.*-Verb\s+RunAs"),
    re.compile(r"^gsudo\s"),
    # PowerShell/cmd wrapper patterns
    re.compile(r"\b(cmd|powershell|pwsh)\s+.*(/c|-c|-Command)\s+.*\b(runas|gsudo)\b", re.IGNORECASE),
]

# Dangerous patterns blocked on all platforms
_DANGEROUS_PATTERNS: list[CommandPattern] = [
    # Destructive Unix commands
    re.compile(r"rm\s+-rf\s+/\s*$"),
    re.compile(r"rm\s+-rf\s+/\*"),
    re.compile(r"^mkfs\s"),
    re.compile(r"dd\s+.*of=/dev/"),
    # Destructive Windows commands
    re.compile(r"^format\s+[A-Za-z]:"),
    re.compile(r"del\s+/f\s+/s\s+/q\s+[A-Za-z]:\\"),
    # Fork bombs
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\}\s*;:"),
    re.compile(r"%0\|%0"),
    # Permission abuse
    re.compile(r"chmod\s+777\s+/\s*$"),
    re.compile(r"icacls\s+.*\s+/grant\s+Everyone:F"),
    # System control commands
    re.compile(r"^(shutdown|poweroff|reboot|halt)\b"),
    re.compile(r"^init\s+0"),
    # Remote script execution (pipe to shell)
    re.compile(r"\bcurl\b.*\|\s*(ba)?sh"),
    re.compile(r"\bwget\b.*-O\s*-.*\|\s*(ba)?sh"),
]

# Path extraction pattern for detecting paths in commands
# Captures both absolute and relative paths to prevent path traversal bypass
_PATH_PATTERN = re.compile(
    r"(?:"
    # Unix absolute paths
    r'(?:^|\s)(/[^\s"\']+)'
    # Windows absolute paths
    r'|(?:^|\s)([A-Za-z]:\\[^\s"\']+)'
    # Relative paths starting with ./ or ../
    r'|(?:^|\s)(\.\.?/[^\s"\']*)'
    # Path traversal patterns (../ anywhere in argument)
    r'|(?:^|\s)([^\s"\']*\.\./[^\s"\']*)'
    # Quoted Unix absolute paths
    r'|"(/[^"]+)"'
    # Quoted Windows absolute paths
    r'|"([A-Za-z]:\\[^"]+)"'
    # Quoted relative paths
    r'|"(\.\.?/[^"]*)"'
    r"|'(\.\.?/[^']*)'"
    # Quoted path traversal
    r'|"([^"]*\.\./[^"]*)"'
    r"|'([^']*\.\./[^']*)'"
    # Single-quoted Unix absolute paths
    r"|'(/[^']+)'"
    # Single-quoted Windows absolute paths
    r"|'([A-Za-z]:\\[^']+)'"
    r")"
)


class ShellTool(BaseTool):
    """Tool for executing shell commands with security controls.

    Requires an executor to be provided at construction time.

    Attributes:
        executor: The shell executor to use for command execution.
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"executor", "additional_properties"}
    INJECTABLE: ClassVar[set[str]] = {"executor"}

    def __init__(
        self,
        *,
        executor: ShellExecutor,
        options: ShellToolOptions | None = None,
        name: str = "shell",
        description: str = "Execute shell commands",
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the ShellTool.

        Keyword Args:
            executor: The shell executor to use for command execution.
            options: Configuration options for the shell tool.
            name: The name of the tool. Defaults to "shell".
            description: A description of the tool.
            additional_properties: Additional properties for the tool.
            **kwargs: Additional keyword arguments passed to BaseTool.
        """
        super().__init__(
            name=name,
            description=description,
            additional_properties=additional_properties,
            **kwargs,
        )
        self.executor = executor
        self._options = options or {}

        # Extract options with defaults
        self.working_directory = self._options.get("working_directory")
        self.timeout_seconds = self._options.get("timeout_seconds", DEFAULT_SHELL_TIMEOUT_SECONDS)
        self.max_output_bytes = self._options.get("max_output_bytes", DEFAULT_SHELL_MAX_OUTPUT_BYTES)
        self.approval_mode: Literal["always_require", "never_require"] = self._options.get(
            "approval_mode", "always_require"
        )
        self.allowlist_patterns = self._options.get("allowlist_patterns", [])
        self.denylist_patterns = self._options.get("denylist_patterns", DEFAULT_DENYLIST_PATTERNS.copy())
        self.allowed_paths = self._options.get("allowed_paths", [])
        self.blocked_paths = self._options.get("blocked_paths", [])
        self.block_privilege_escalation = self._options.get("block_privilege_escalation", True)
        self.capture_stderr = self._options.get("capture_stderr", True)
        self._cached_ai_function: "AIFunction[Any, Content] | None" = None

    def _validate_command(self, command: str) -> _ValidationResult:
        """Validate a command against all security policies."""
        if self.block_privilege_escalation:
            result = self._validate_privilege_escalation(command)
            if not result.is_valid:
                return result

        result = self._validate_dangerous_patterns(command)
        if not result.is_valid:
            return result

        result = self._validate_denylist(command)
        if not result.is_valid:
            return result

        result = self._validate_allowlist(command)
        if not result.is_valid:
            return result

        result = self._validate_paths(command)
        if not result.is_valid:
            return result

        return _ValidationResult(is_valid=True)

    def _validate_privilege_escalation(self, command: str) -> _ValidationResult:
        """Check if command attempts privilege escalation."""
        system = platform.system().lower()

        if system in ("linux", "darwin"):
            # Pattern-based detection
            for pattern in _UNIX_PRIVILEGE_PATTERNS:
                if _matches_pattern(pattern, command):
                    return _ValidationResult(
                        is_valid=False,
                        error_message="Privilege escalation not allowed",
                    )
            # Token-based detection for shell wrapper bypasses
            if _contains_privilege_command(command, _UNIX_PRIVILEGE_COMMANDS):
                return _ValidationResult(
                    is_valid=False,
                    error_message="Privilege escalation not allowed",
                )

        if system == "windows":
            # Pattern-based detection
            for pattern in _WINDOWS_PRIVILEGE_PATTERNS:
                if _matches_pattern(pattern, command):
                    return _ValidationResult(
                        is_valid=False,
                        error_message="Privilege escalation not allowed",
                    )
            # Token-based detection for shell wrapper bypasses
            if _contains_privilege_command(command, _WINDOWS_PRIVILEGE_COMMANDS):
                return _ValidationResult(
                    is_valid=False,
                    error_message="Privilege escalation not allowed",
                )

        return _ValidationResult(is_valid=True)

    def _validate_dangerous_patterns(self, command: str) -> _ValidationResult:
        """Check if command matches dangerous patterns."""
        for pattern in _DANGEROUS_PATTERNS:
            if _matches_pattern(pattern, command):
                return _ValidationResult(
                    is_valid=False,
                    error_message=f"Dangerous command blocked: {command[:50]}...",
                )
        return _ValidationResult(is_valid=True)

    def _validate_denylist(self, command: str) -> _ValidationResult:
        """Check if command matches denylist patterns."""
        for pattern in self.denylist_patterns:
            if _matches_pattern(pattern, command):
                pattern_str = pattern.pattern if isinstance(pattern, re.Pattern) else pattern
                return _ValidationResult(
                    is_valid=False,
                    error_message=f"Command matches denylist pattern '{pattern_str}'",
                )
        return _ValidationResult(is_valid=True)

    def _validate_allowlist(self, command: str) -> _ValidationResult:
        """Check if command matches allowlist patterns."""
        if not self.allowlist_patterns:
            return _ValidationResult(is_valid=True)

        for pattern in self.allowlist_patterns:
            if _matches_pattern(pattern, command):
                return _ValidationResult(is_valid=True)

        return _ValidationResult(
            is_valid=False,
            error_message="Command does not match any allowlist pattern",
        )

    def _validate_paths(self, command: str) -> _ValidationResult:
        """Check if command accesses allowed paths.

        Note: Path validation is advisory. Sandboxed execution is recommended for untrusted input.
        """
        paths = self._extract_paths(command)
        if not paths:
            return _ValidationResult(is_valid=True)

        # Pre-compute normalized blocked/allowed paths
        blocked_normalized = [os.path.realpath(p).replace("\\", "/").rstrip("/") for p in self.blocked_paths]
        allowed_normalized = [os.path.realpath(p).replace("\\", "/").rstrip("/") for p in self.allowed_paths]

        for path in paths:
            try:
                if not os.path.isabs(path) and self.working_directory:
                    path = os.path.join(self.working_directory, path)
                resolved = os.path.realpath(path)
            except (OSError, ValueError):
                resolved = path
            normalized = resolved.replace("\\", "/").rstrip("/")

            for blocked in blocked_normalized:
                if normalized.startswith(blocked):
                    return _ValidationResult(
                        is_valid=False,
                        error_message=f"Access to blocked path not allowed: {path}",
                    )

            if allowed_normalized and not any(normalized.startswith(allowed) for allowed in allowed_normalized):
                return _ValidationResult(
                    is_valid=False,
                    error_message=f"Path not in allowed paths: {path}",
                )

        return _ValidationResult(is_valid=True)

    def _extract_paths(self, command: str) -> list[str]:
        """Extract file paths from a command string."""
        paths: list[str] = []
        for match in _PATH_PATTERN.finditer(command):
            path = next((g for g in match.groups() if g is not None), None)
            if path:
                paths.append(path)
        return paths

    async def execute(self, commands: list[str]) -> "Content":
        """Execute shell commands after validation.

        Args:
            commands: List of commands to execute.

        Returns:
            Content with type 'shell_result' containing the command outputs.

        Raises:
            ValueError: If any command fails validation.
        """
        from ._types import Content

        for cmd in commands:
            validation = self._validate_command(cmd)
            if not validation.is_valid:
                raise ValueError(validation.error_message)

        outputs = await self.executor.execute(
            commands,
            working_directory=self.working_directory,
            timeout_seconds=self.timeout_seconds,
            max_output_bytes=self.max_output_bytes,
            capture_stderr=self.capture_stderr,
        )
        return Content.from_shell_result(outputs=outputs)

    def as_ai_function(self) -> "AIFunction[Any, Content]":
        """Convert this ShellTool to an AIFunction.

        Returns:
            An AIFunction that wraps the shell command execution.
        """
        from ._tools import AIFunction
        from ._types import Content

        if self._cached_ai_function is not None:
            return self._cached_ai_function

        shell_tool = self

        async def execute_shell_commands(
            commands: Annotated[list[str], "List of shell commands to execute"],
        ) -> Content:
            try:
                return await shell_tool.execute(commands)
            except ValueError as e:
                return Content.from_shell_result(outputs=[{"error": True, "message": str(e), "exit_code": -1}])
            except Exception as e:
                return Content.from_shell_result(
                    outputs=[{"error": True, "message": f"Execution failed: {e}", "exit_code": -1}]
                )

        ai_function: AIFunction[Any, Content] = AIFunction(
            name=self.name,
            description=self.description,
            func=execute_shell_commands,
            approval_mode=self.approval_mode,
        )

        self._cached_ai_function = ai_function
        return self._cached_ai_function
