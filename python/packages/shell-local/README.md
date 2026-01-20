# Get Started with Microsoft Agent Framework Shell Local

Local shell executor for Microsoft Agent Framework.

## Installation

```bash
pip install agent-framework-shell-local --pre
```

## Usage

```python
from agent_framework import ShellTool
from agent_framework.shell_local import LocalShellExecutor

executor = LocalShellExecutor()
shell_tool = ShellTool(executor=executor)

result = await shell_tool.execute("echo hello")
print(result.stdout)  # "hello\n"
```

## Features

- Async subprocess execution using `asyncio.create_subprocess_shell`
- Configurable timeout with graceful process termination
- Output truncation with UTF-8 boundary handling
- Working directory support
- Separate stdout/stderr capture

## Configuration

```python
executor = LocalShellExecutor(
    default_encoding="utf-8",
    encoding_errors="replace",
)
```

## Security Considerations

`ShellTool` includes security controls to prevent dangerous command execution:

### Default Protections

- **Privilege escalation blocking**: Commands like `sudo`, `su`, `doas`, `runas` are blocked by default
- **Dangerous pattern detection**: Fork bombs, destructive commands (`rm -rf /`, `format C:`), and permission abuse are blocked
- **Path validation**: Optionally restrict commands to specific directories

### Allowlist Patterns

Use `allowlist_patterns` to restrict which commands can be executed:

```python
from agent_framework import ShellTool

shell_tool = ShellTool(
    executor=executor,
    options={
        "allowlist_patterns": ["ls", "cat", "git"],
    }
)
```

**String patterns** match the command name exactly and block command chaining:
- `"ls"` allows `ls -la` but blocks `ls; rm file` and `ls && curl evil.com`
- Shell metacharacters (`;`, `|`, `&`, etc.) in arguments cause the match to fail

**Regex patterns** provide full control for complex scenarios:
```python
import re

options = {
    "allowlist_patterns": [
        re.compile(r"^git\s+(status|log|diff|branch)"),
        re.compile(r"^npm\s+(install|test|run)"),
    ]
}
```

### Path Restrictions

Control file system access using `allowed_paths` and `blocked_paths`:

```python
options = {
    "allowed_paths": ["/home/user/project"],
    "blocked_paths": ["/home/user/project/.env"],
}
```

Blocked paths take precedence over allowed paths.
