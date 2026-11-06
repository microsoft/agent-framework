# Windows Command Line Tokenization for LocalShellTool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Windows shell path and argument tokenization in `LocalShellTool` and `AGENT_FRAMEWORK_SHELL` by replacing POSIX `shlex.split` with a Windows-native `CommandLineToArgvW` tokenizer when running on or targeting Windows.

**Architecture:** Implement a specialized `_split_windows_command_line(cmd: str) -> list[str]` tokenizer in `_resolve.py` that preserves literal backslashes, double-quoted substrings with embedded whitespace, escaped quotes (`\"`), and explicit empty arguments (`""`). Route string-based shell resolution through this tokenizer when `sys.platform == "win32"` while preserving standard POSIX `shlex.split` behavior on Unix platforms.

**Tech Stack:** Python 3.10+, `pytest`, `agent_framework_tools.shell`.

**Spec:** GitHub Issue #9819 (https://github.com/microsoft/agent-framework/issues/9819), maintainer review on closed PR #9858.

## Global Constraints

- Never alter POSIX shell parsing on Linux or macOS (`shlex.split` remains active).
- Never add new external dependencies; use standard library parsing logic.
- Must satisfy `CommandLineToArgvW` rules: $2N$ backslashes before a quote yield $N$ backslashes without escaping the quote; $2N+1$ backslashes before a quote yield $N$ backslashes plus a literal quote. Backslashes elsewhere are literal.
- Explicit empty quoted arguments (e.g. `""`) must produce an empty string element `""` in argv.
- Regression tests must run deterministically on Linux/macOS CI using `monkeypatch.setattr(resolve_module.sys, "platform", "win32")`.

## Review Focus

- Unquoted Windows paths containing spaces and backslashes (e.g., `C:\Program Files\PowerShell\7\pwsh.exe`).
- Adjacent quoted and unquoted fragments (e.g., `--rcfile="C:\Program Files\bash.rc"`).
- Explicit empty argument tokens (e.g., `--flag "" -v`).
- Escaped quotation marks within quoted parameters (e.g., `--opt="val\"ue"`).
- Network UNC paths with consecutive leading backslashes (e.g., `\\server\share\tool.exe`).

---

### Task 1: Add Reproducing Regression Tests in `test_shell_resolve.py`

**Files:**
- Modify: `python/packages/tools/tests/test_shell_resolve.py`

**Interfaces:**
- Consumes: `agent_framework_tools.shell._resolve.resolve_shell`
- Produces: Test functions validating Windows path preservation and argument tokenization.

- [ ] **Step 1: Write the failing tests**

```python
def test_win32_shell_override_preserves_backslashes(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "win32")
    path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    argv = resolve_shell(path, interactive=False)
    assert argv == [path, "-Command"]


def test_win32_env_shell_override_preserves_backslashes(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "win32")
    path = r"C:\msys64\usr\bin\bash.exe"
    monkeypatch.setenv("AGENT_FRAMEWORK_SHELL", path)
    argv = resolve_shell(None, interactive=False)
    assert argv == [path, "-c"]


def test_win32_quoted_shell_with_spaces_and_empty_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._resolve as resolve_module

    monkeypatch.setattr(resolve_module.sys, "platform", "win32")
    cmd = r'"C:\Program Files\PowerShell\7\pwsh.exe" -NoProfile "" --opt="val\"ue"'
    argv = resolve_shell(cmd, interactive=False)
    assert argv[0] == r"C:\Program Files\PowerShell\7\pwsh.exe"
    assert argv[1] == "-NoProfile"
    assert argv[2] == ""
    assert argv[3] == r'--opt=val"ue'
    assert argv[-1] == "-Command"
```

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest packages/tools/tests/test_shell_resolve.py -k "win32"`
Expected: FAIL with backslashes stripped or tokenization mismatch.

---

### Task 2: Implement Windows `CommandLineToArgvW` Tokenizer in `_resolve.py`

**Files:**
- Modify: `python/packages/tools/agent_framework_tools/shell/_resolve.py`

**Interfaces:**
- Consumes: `shell: str | Sequence[str] | None`, `AGENT_FRAMEWORK_SHELL`
- Produces: `_split_windows_command_line(cmd: str) -> list[str]` and updated `resolve_shell` routing.

- [ ] **Step 1: Write `_split_windows_command_line` implementation**

```python
def _split_windows_command_line(cmd: str) -> list[str]:
    """Parse a Windows command line string into argv following CommandLineToArgvW rules."""
    args: list[str] = []
    buf: list[str] = []
    in_quotes = False
    has_token = False
    i = 0
    n = len(cmd)

    while i < n:
        c = cmd[i]
        if c in " \t" and not in_quotes:
            if has_token:
                args.append("".join(buf))
                buf = []
                has_token = False
            i += 1
            continue

        if c == "\\":
            num_slashes = 0
            while i < n and cmd[i] == "\\":
                num_slashes += 1
                i += 1
            if i < n and cmd[i] == '"':
                buf.append("\\" * (num_slashes // 2))
                if num_slashes % 2 == 1:
                    buf.append('"')
                    has_token = True
                    i += 1
                else:
                    in_quotes = not in_quotes
                    has_token = True
                    i += 1
            else:
                buf.append("\\" * num_slashes)
                has_token = True
        elif c == '"':
            in_quotes = not in_quotes
            has_token = True
            i += 1
        else:
            buf.append(c)
            has_token = True
            i += 1

    if has_token:
        args.append("".join(buf))
    return args
```

- [ ] **Step 2: Update `resolve_shell` and `is_powershell` in `_resolve.py`**

In `_split_shell_override(value: str) -> list[str]`:
Route to `_split_windows_command_line(value)` if `sys.platform == "win32"`, else `shlex.split(value)`.
In `is_powershell`:
Normalize backslashes via `argv[0].replace("\\", "/")` before `os.path.basename` to ensure win32 paths detect properly when tested on POSIX platforms.

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest packages/tools/tests/test_shell_resolve.py`
Expected: ALL PASS.

- [ ] **Step 4: Run repo linting and typing checks**

Run: `uv run ruff check packages/tools` and `uv run pyright packages/tools`
Expected: 0 errors.
