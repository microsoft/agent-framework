# FIDES security samples

This folder contains runnable FIDES samples. Keep this README as the quick
entry point for choosing and running a sample; use
[FIDES_DEVELOPER_GUIDE.md](FIDES_DEVELOPER_GUIDE.md) for the architecture,
security model, middleware behavior, and API reference.

## What each sample demonstrates

| Sample | Focus | Demonstrates |
|--------|-------|--------------|
| `email_security_example.py` | Prompt injection defense | `SecureAgentConfig`, Foundry-backed email handling, `quarantined_llm`, and approval on policy violations |
| `repo_confidentiality_example.py` | Data exfiltration prevention | Confidentiality labels, Foundry-backed repository access, `max_allowed_confidentiality`, and approval before leaking private data |
| `github_mcp_example.py` | Remote MCP URL with local FIDES enforcement | `SecureMCPToolProxy(url=...)`, direct GitHub MCP access, tool auto-labeling, and post-tool-call policy enforcement |

## Prerequisites

Run these samples from the `python/` directory with the repo development
environment available.

- Azure CLI authentication: `az login`
- `FOUNDRY_PROJECT_ENDPOINT` set in your environment
- `FOUNDRY_MODEL` set in your environment for the main agent deployment
- Local dev environment installed (for example, `uv sync --dev`)

These samples use Foundry for the main agent and keep the quarantine
client pinned to `gpt-4o-mini` where applicable.

For `github_mcp_example.py`, set:

- `GITHUB_PAT` (GitHub Personal Access Token)
- `FOUNDRY_PROJECT_ENDPOINT` (Foundry project endpoint)
- `FOUNDRY_MODEL` (optional model override)

## Suppressing the experimental warning

The FIDES APIs in these samples are still experimental. Each sample includes a
short commented `warnings.filterwarnings(...)` snippet near the imports.
Uncomment it if you want to suppress the FIDES warning before using the
experimental APIs locally.

## Running the samples

### `email_security_example.py`

This sample simulates an inbox containing trusted and untrusted emails,
including prompt-injection attempts that try to force a privileged `send_email`
tool call.

Run it with:

```bash
uv run samples/02-agents/security/email_security_example.py --cli
uv run samples/02-agents/security/email_security_example.py --devui
uv run samples/02-agents/security/email_security_example.py --cli --debug
```

When you run the DevUI variant, the sample prints the active DevUI bearer token
before starting the server.

Add `--debug` to enable verbose tool and security middleware logging.

What to look for:

- Untrusted email bodies are handled through the FIDES security flow
- `quarantined_llm` processes hidden content in isolation
- DevUI requests approval if the agent tries a blocked privileged action

### `repo_confidentiality_example.py`

This sample simulates a public issue that tries to trick the agent into reading
private repository secrets and posting them to a public channel.

Run it with:

```bash
uv run samples/02-agents/security/repo_confidentiality_example.py --cli
uv run samples/02-agents/security/repo_confidentiality_example.py --devui
```

When you run the DevUI variant, the sample prints the active DevUI bearer token
before starting the server.

What to look for:

- Reading public content keeps the context public
- Reading private content taints the context as private
- Posting private data to a public destination triggers an approval request

### `github_mcp_example.py`

This sample connects directly to `https://api.githubcopilot.com/mcp/` through
`MCPStreamableHTTPTool`, then wraps the MCP client in `SecureMCPToolProxy` so
FIDES middleware can inspect tool results and enforce policy locally. The
`X-MCP-Features: ifc_labels` header is passed to opt in to server-side IFC label
emission in tool result `_meta`.

Run it with:

```bash
uv run samples/02-agents/security/github_mcp_example.py --cli
uv run samples/02-agents/security/github_mcp_example.py --cli --attack
uv run samples/02-agents/security/github_mcp_example.py --devui
uv run samples/02-agents/security/github_mcp_example.py --devui --debug
```

What to look for:

- MCP tools are auto-labeled from remote annotations
- Untrusted tool output is tracked by FIDES label middleware
- Attack-mode write attempts can trigger policy enforcement or approval

## Where to find the details

For the full FIDES design and API details, see
[FIDES_DEVELOPER_GUIDE.md](FIDES_DEVELOPER_GUIDE.md), which covers:

- integrity and confidentiality labels
- label propagation and auto-hiding behavior
- policy enforcement middleware
- security tools such as `quarantined_llm` and `inspect_variable`
- `SecureAgentConfig` and manual integration patterns
