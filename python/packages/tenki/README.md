# agent-framework-tenki

[Tenki Sandbox](https://tenki.cloud) integration for Microsoft Agent Framework.

## Installation

```bash
pip install agent-framework-tenki --pre
```

You also need a Tenki API key. Follow the [Tenki Sandbox quick start](https://tenki.cloud/docs/sandbox/quick-start-sandbox)
to create a workspace and generate a key, then export it before running your agent:

```bash
export TENKI_API_KEY="tk_..."
```

## Quick start

### Context provider (recommended)

Use `TenkiCodeActProvider` to inject an `execute_code` tool into every agent run. Each
run shares the same underlying Tenki sandbox until the provider is closed.

```python
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_tenki import TenkiCodeActProvider

async with TenkiCodeActProvider() as codeact:
    agent = Agent(
        client=OpenAIChatClient(),
        context_providers=[codeact],
    )
    result = await agent.run("Compute the 42nd Fibonacci number.")
```

### Standalone tool

Use `TenkiExecuteCodeTool` directly when you want full control over how the tool is
attached to the agent.

```python
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from agent_framework_tenki import TenkiExecuteCodeTool

async with TenkiExecuteCodeTool() as execute_code:
    agent = Agent(
        client=OpenAIChatClient(),
        tools=[execute_code],
    )
    result = await agent.run("Print the SHA-256 of 'hello world'.")
```

Remember to `close()` (or use `async with`) so the sandbox is terminated when you're
done — otherwise it lives until your Tenki workspace timeout expires.

## Configuration

| Kwarg | Default | Description |
|---|---|---|
| `sandbox_name` | `agent-framework-<8-hex>` | Sandbox identifier used when creating the sandbox on Tenki. |
| `api_key` | `os.environ["TENKI_API_KEY"]` | Overrides the environment variable. |
| `image` | Tenki default | Custom base image identifier. |
| `project_id` / `workspace_id` | `os.environ["TENKI_PROJECT_ID"]` / `os.environ["TENKI_WORKSPACE_ID"]` | Required when your API key has access to multiple projects. Constructor args override the env vars. |
| `cpu_cores` / `memory_mb` / `disk_size_gb` | Tenki defaults | Optional resource overrides. |
| `max_duration_seconds` | `None` | Server-side cost kill-switch. Recommended for production agent loops. |
| `exec_timeout_seconds` | `60` | Per-`execute_code` invocation timeout in seconds. |
| `extra_create_kwargs` | `{}` | Passed straight to `tenki_sandbox.Sandbox.create` for Tenki-specific options — see the section below. |

### Tenki-specific options via `extra_create_kwargs`

The Tenki SDK exposes platform features beyond the ones surfaced directly on
`TenkiExecuteCodeTool`. Anything you pass through `extra_create_kwargs` is
forwarded verbatim to `tenki_sandbox.Sandbox.create`. Common ones:

| Kwarg | Type | Purpose |
|---|---|---|
| `snapshot_id` | `str` | Restore the sandbox from a previously created Tenki snapshot instead of provisioning a fresh image — preserves filesystem state across sessions. |
| `clone_repo_url` | `str` | Git-clone the URL into the sandbox on create. Pair with `github_token` for private repos. |
| `github_token` | `str` | Auth token consumed by `clone_repo_url`. |
| `env` | `dict[str, str]` | Environment variables passed into the sandbox at creation time (agent secrets, config, etc.). |
| `allow_inbound` / `allow_outbound` | `bool` | Sandbox network policy. Enable `allow_inbound` for inbound exposure workflows; disable `allow_outbound` for stricter isolation. Both default to `True`. |
| `metadata` | `dict[str, str]` | Attach arbitrary key-value tags for filtering, billing attribution, or upstream job-ID tracking. |
| `tags` | `list[str]` | Attach labels for organization/filtering in the Tenki dashboard. |
| `volumes` | `list[dict]` | Attach persistent [Tenki volumes](https://tenki.cloud/docs/sandbox/volumes) that survive sandbox termination. Each entry: `{"volume_id": str, "mount_path": str, "read_only": bool (optional)}`. Volumes are workspace-scoped and must be reattached explicitly on future sandboxes. |

Example:

```python
async with TenkiExecuteCodeTool(
    extra_create_kwargs={
        "clone_repo_url": "https://github.com/myorg/myrepo",
        "github_token": os.environ["GITHUB_TOKEN"],
        "env": {"OPENAI_API_KEY": os.environ["OPENAI_API_KEY"]},
    },
) as tool:
    ...
```

See the [Tenki sandbox sessions](https://tenki.cloud/docs/sandbox/sessions#create-a-session)
and [Tenki volumes](https://tenki.cloud/docs/sandbox/volumes) reference for the
complete option list and semantics.

## Lifecycle

The sandbox is provisioned lazily on the first `execute_code` call and reused for every
subsequent call on the same tool or provider instance. Before each call the tool
reconciles remote sandbox state, so callers never need to track pause/terminate
transitions manually. Each call runs `python3 -c <code>` inside the sandbox, which
means:

- **Sandbox filesystem persists** across calls — files written to `/tmp` or the user
  home in one call are visible in the next.
- **Installed packages persist** — packages installed via pip or apt in one call are
  available in subsequent calls (subject to the sandbox's outbound network policy).
  See [Tenki's sandbox quick start](https://tenki.cloud/docs/sandbox/quick-start-sandbox)
  for the recommended installation workflow (the default image ships `python3-venv`).
- **Python interpreter state does not persist** — each call is a fresh `python3`
  process, so variables defined in one call are not reachable in the next. Persist
  intermediate state through files or environment variables when a later call needs
  it.
- **Paused sandboxes auto-resume** — if the sandbox transitions to `PAUSED` between
  calls (Tenki's server-side idle policies, `idle_timeout_minutes` supplied via
  `extra_create_kwargs`, or an external `tenki sandbox pause`), the next
  `execute_code` call transparently resumes it before running. Filesystem and
  installed packages carry across the pause unchanged.
- **Terminated sandboxes are replaced** — if the sandbox transitions to
  `TERMINATING`/`TERMINATED` (workspace timeout, `max_duration_seconds`, or an
  external `tenki sandbox terminate`), the next call provisions a fresh sandbox.
  Filesystem and installed packages from the previous sandbox are **not** carried
  over — snapshot the sandbox (via `extra_create_kwargs={"snapshot_id": ...}` on a
  new tool) if you need to preserve state across a termination.

Call `close()` on the tool or provider (or use `async with`) to terminate the sandbox
and release the underlying microVM. Different agents that share a single
`TenkiCodeActProvider` share the same sandbox — create a separate provider per agent
when isolation matters.

## Notes

- In-sandbox tool callbacks are not supported — code executing inside the sandbox
  cannot invoke host-side tools (Tenki's SDK does not expose a callback bridge).
- File mounts and outbound network allow-lists are not modeled by this package. Bake
  dependencies into a custom Tenki image, or pass extra configuration through
  `extra_create_kwargs`.
