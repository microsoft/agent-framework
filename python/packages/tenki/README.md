# agent-framework-tenki

[Tenki Sandbox](https://tenki.cloud) integration for Microsoft Agent Framework.

> [!WARNING]
> This package is in **alpha**. APIs may change without notice. It is not part of
> `agent-framework[all]` yet; install it explicitly with `--pre`.

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

Use `TenkiCodeActProvider` to inject an `execute_code` tool into every agent run.
**Each agent run gets its own fresh sandbox**, which is terminated automatically
when the run completes — state does not leak across runs.

```python
from agent_framework import Agent
from agent_framework_tenki import TenkiCodeActProvider

async with TenkiCodeActProvider() as codeact:
    agent = Agent(
        client=client,  # any agent-framework chat client
        context_providers=[codeact],
    )
    result = await agent.run("Compute the 42nd Fibonacci number.")
```

### Standalone tool

Use `TenkiExecuteCodeTool` directly when you want to share a single sandbox
across many agent runs (bypassing the per-run isolation of the provider):

```python
from agent_framework import Agent
from agent_framework_tenki import TenkiExecuteCodeTool

async with TenkiExecuteCodeTool() as execute_code:
    agent = Agent(
        client=client,  # any agent-framework chat client
        tools=[execute_code],
    )
    result = await agent.run("Print the SHA-256 of 'hello world'.")
```

Remember to `close()` (or use `async with`) so the sandbox is terminated when you're
done — otherwise it keeps running (and billing) until Tenki's `max_duration` or idle
policies stop it.

## Configuration

| Kwarg | Default | Description |
|---|---|---|
| `sandbox_name` | `agent-framework-<8-hex>` | Literal sandbox identifier for the standalone tool; **prefix** for run-scoped names when used through `TenkiCodeActProvider` (each run gets `<prefix>-<8-hex>`). |
| `api_key` | `os.environ.get("TENKI_API_KEY")` | Overrides the environment variable. |
| `image` | Tenki default | Custom base image identifier. |
| `project_id` / `workspace_id` | `os.environ.get("TENKI_PROJECT_ID")` / `os.environ.get("TENKI_WORKSPACE_ID")` | Required when your API key has access to multiple projects. Constructor args override the env vars. |
| `cpu_cores` / `memory_mb` / `disk_size_gb` | Tenki defaults | Optional resource overrides. |
| `max_duration_seconds` | `900` (15 min) | Server-side duration cap. On expiry, project/workspace-scoped sandboxes are **paused** and unscoped ones are **terminated**; in both cases compute billing stops, including when the parent process crashed before calling `close()`. Pass a larger value for longer evals, or `None` to opt out (not recommended). |
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
import os

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

The `execute_code` tool provisions a Tenki sandbox lazily on its first invocation.
Before each subsequent call it reconciles remote sandbox state, resuming or
re-provisioning as described below. Each call runs `python3 -c
<code>` inside the sandbox, which means:

- **Sandbox filesystem persists** across calls within the same tool instance —
  files written to `/tmp` or the user home in one call are visible in the next.
- **Installed packages persist** — packages installed via pip or apt in one call are
  available in subsequent calls (subject to the sandbox's outbound network policy).
  See [Tenki's sandbox quick start](https://tenki.cloud/docs/sandbox/quick-start-sandbox)
  for the recommended installation workflow (the default image ships `python3-venv`).
- **Python interpreter state does not persist** — each call is a fresh `python3`
  process, so variables defined in one call are not reachable in the next. Persist
  intermediate state through files or environment variables when a later call needs
  it.
- **Paused sandboxes auto-resume** — if the sandbox transitions to `PAUSED`
  between calls (Tenki's server-side idle policies, `max_duration_seconds`
  expiring on a project/workspace-scoped sandbox, `idle_timeout_minutes`
  supplied via `extra_create_kwargs`, or an external `tenki sandbox pause`),
  the next `execute_code` call transparently resumes it and polls until it
  reaches `RUNNING` before executing. The same applies to `USER_SHUTDOWN`
  (the guest OS was shut down from inside the VM) — note that this resume can
  take a minute or more, since Tenki captures the shutdown sandbox's disk
  asynchronously and the resume waits for that capture to complete. Filesystem
  and installed packages carry across the pause unchanged.
- **Terminated sandboxes are replaced** — if the sandbox transitions to
  `TERMINATING`/`TERMINATED` (workspace timeout, `max_duration_seconds`
  expiring on an unscoped sandbox, or an external `tenki sandbox terminate`),
  the next call provisions a fresh sandbox.
  Filesystem and installed packages from the previous sandbox are **not** carried
  over — snapshot the sandbox (via `extra_create_kwargs={"snapshot_id": ...}` on a
  new tool) if you need to preserve state across a termination.

### Provider vs standalone lifetime

- **`TenkiCodeActProvider` mints a fresh tool per agent run** (`before_run` →
  `create_run_tool()`), and terminates its sandbox in `after_run`. Within a
  single run, every `execute_code` call in the agentic loop shares that run's
  sandbox — files written by one call are visible to the next. Two agent
  runs never share filesystem state, secrets, or a Python interpreter through
  the tool. Every run that executes code pays the sandbox-provisioning cost
  (a few seconds of startup latency — ~2s measured with the default image —
  plus Tenki credits for the run's duration); a run where the model never
  calls `execute_code` provisions no sandbox at all.
- **`TenkiExecuteCodeTool` used standalone** reuses the same sandbox across
  every agent run until you `close()` it. Cheaper (one provision) and stateful
  (files persist across runs) — appropriate when isolation between runs is not
  required.

The provider's per-run scoping suits **one-shot task runs**: execute a task,
return the answer, discard the environment. In a **multi-turn conversation**
(several `agent.run()` calls on one session), each message starts from a blank
filesystem — files and installed packages from earlier messages are gone, and
each code-executing message pays a fresh provision. If state should carry
across the messages of a conversation, use the standalone tool (one shared
sandbox, no per-run isolation).

Call `close()` on the tool or provider (or use `async with`) to terminate the sandbox
and release the underlying microVM. `close()` preserves the sandbox handle if the
terminate call itself fails, so a transient error does not leak a running microVM —
the caller can retry.

## Notes

- In-sandbox tool callbacks are not supported — code executing inside the sandbox
  cannot invoke host-side tools (Tenki's SDK does not expose a callback bridge).
- File mounts and outbound network allow-lists are not surfaced as first-class
  kwargs on this package. Pass them through `extra_create_kwargs` (see the table
  above for `allow_inbound` / `allow_outbound` / `volumes`), or bake dependencies
  into a custom Tenki image.
