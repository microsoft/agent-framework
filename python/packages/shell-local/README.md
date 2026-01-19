# Get Started with Microsoft Agent Framework Shell Local

Local shell executor for Microsoft Agent Framework.

## Installation

```bash
pip install agent-framework-shell-local --pre
```

## Usage

```python
from agent_framework import ShellTool
from agent_framework_shell_local import LocalShellExecutor

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
