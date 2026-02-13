# Security Warning

**This sample executes real shell commands on your system.** Before running:

1. **Review the code** to understand what commands may be executed
2. **Run in an isolated environment** (container, VM, or sandbox) when possible
3. **Configure strict security options** to limit what the agent can do
4. **Always use human-in-the-loop approval** for shell command execution
5. **Never run with elevated privileges** (root/administrator)

The ShellTool includes security controls, but defense-in-depth is essential when executing arbitrary commands.

---

## What this sample demonstrates

This sample demonstrates how to use the ShellTool with an AI agent to execute shell commands with security controls and human-in-the-loop approval.

Key features:

- Configuring ShellTool security options (allowlist, denylist, path restrictions)
- Blocking dangerous patterns, command chaining, and privilege escalation
- Using ApprovalRequiredAIFunction for human-in-the-loop command approval
- Cross-platform support (Windows and Unix/Linux)

## Environment Variables

Set the following environment variables on Windows:

```powershell
# Required: Your OpenAI API key
$env:OPENAI_API_KEY="sk-..."

# Optional: Model to use (defaults to gpt-4o-mini)
$env:OPENAI_MODEL="gpt-4o-mini"

# Optional: Working directory for shell commands (defaults to temp folder)
$env:SHELL_WORKING_DIR="C:\path\to\working\directory"
```

Or on Unix/Linux:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
export SHELL_WORKING_DIR="/path/to/working/directory"
```

## Running in Docker (Recommended for Safety)

For safer testing, run the sample in a Docker container:

```bash
# Build the container
docker build -t shell-tool-sample .

# Run interactively
docker run -it --rm -e OPENAI_API_KEY="sk-..." shell-tool-sample
```

## Security Configuration

The sample demonstrates several security options:

| Option | Default | Description |
|--------|---------|-------------|
| `AllowedCommands` | null | Regex patterns for allowed commands |
| `DeniedCommands` | null | Regex patterns for blocked commands |
| `AllowedPaths` | null | Paths commands can access |
| `BlockedPaths` | null | Paths commands cannot access |
| `BlockDangerousPatterns` | true | Block fork bombs, rm -rf /, etc. |
| `BlockCommandChaining` | true | Block ; \| && \|\| $() operators |
| `BlockPrivilegeEscalation` | true | Block sudo, su, runas, etc. |
| `TimeoutInMilliseconds` | 60000 | Command execution timeout |
| `MaxOutputLength` | 51200 | Maximum output size in bytes |

## Example Interaction

```
You: Create a folder called test and list its contents

[APPROVAL REQUIRED] The agent wants to execute: shell
Commands: ["mkdir test"]
Approve? (Y/N): Y

[APPROVAL REQUIRED] The agent wants to execute: shell
Commands: ["ls test"]
Approve? (Y/N): Y

Agent: I created the "test" folder and listed its contents. The folder is currently empty.
```
