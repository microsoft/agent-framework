# Build your own claw and agent harness — Python samples

Runnable Python samples for the [**"Build your own claw and agent harness with Microsoft Agent Framework"** blog](https://devblogs.microsoft.com/agent-framework/build-your-own-claw-and-agent-harness-with-microsoft-agent-framework)
series. Each step builds a personal finance / investing assistant on top of
`create_harness_agent`, reusing the shared harness `console` package in the parent `harness/`
directory.

- **Part 1 — `claw_step01_meet_your_claw.py`** — the minimal harness.
- **Part 2 — `claw_step02_working_with_data.py`** — file access, approvals, and durable memory.
- **Part 3 — `claw_step03_scaling_capabilities.py`** — skills, shell, CodeAct, and background agents.

## Prerequisites

1. A Microsoft Foundry project with a deployed model.
2. Azure CLI installed and authenticated (`az login`).

## Environment variables

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
export FOUNDRY_MODEL="your-model-deployment-name"
```

---

## Part 1 — Meet your claw

Builds the foundation of the assistant on top of `create_harness_agent`.

### What this sample demonstrates

- **`create_harness_agent`** — a factory that builds a batteries-included agent: function
  invocation, per-service-call history persistence, planning (`TodoProvider` +
  `AgentModeProvider`), and web search.
- **A custom function tool** — `get_stock_price`, exposing local data to the agent. Prices are
  illustrative mock data, not real quotes.
- **Web search** — provided automatically by the harness for market news and commentary.
- **Planning & modes** — the agent breaks a multi-step request ("review my watchlist") into a todo
  list and switches between *plan* and *execute* modes.
- **Shared harness console** — interactive streaming UI (reused from the parent `harness/console`
  package) with `/todos`, `/mode`, and `/exit` commands.

### Running

```bash
# From the repository root, using a PEP 723 compatible runner:
uv run python/samples/02-agents/harness/build_your_own_claw/claw_step01_meet_your_claw.py
```

### What to expect

The sample starts an interactive loop. Try these in order:

1. `/mode execute` — switch out of the default plan mode; quick lookups don't need a plan.
2. `What's the price of MSFT?` — the agent calls the `get_stock_price` tool.
3. `Any recent news on NVDA?` — the agent uses web search.
4. `Add MSFT, NVDA and SPY to my watch list` — saved to `watchlist.md` in the session's memory.
5. `/mode plan` — switch back to plan mode for a bigger, multi-step task.
6. `Review my watchlist and recommend some stocks to add` — the agent plans, then executes. Type
   `/todos` to see the list and `/mode` to inspect the current mode.

---

## Part 2 — Working with your data, safely

Teaches the assistant to work with *your* data safely.

### What this sample demonstrates

- **File access** — the agent reads a pre-populated `working/portfolio.csv` and writes reports
  with the `file_access_*` tools. File access is opt-in; the sample enables it by pointing its
  store at the sample's `working/` folder via `create_harness_agent(file_access_store=...)`.
- **Approvals** — file-access tools require approval by default, but the sample wires the built-in
  `read_only_tools_auto_approval_rule` so reads/lists/searches are frictionless while saving and
  deleting still pause for approval. The `place_trade` tool is marked
  `approval_mode="always_require"`, so the harness asks you to approve or deny before any trade
  runs. The trade is simulated.

  > ⚠️ **Security — avoid tool-name collisions:** `read_only_tools_auto_approval_rule`
  > approves local file-access tools by tool name only (`file_access_read`,
  > `file_access_ls`, `file_access_grep`). Auto-approval rules may match by name,
  > so any other local tool registered under one of these names — for example a
  > tool with a caller-configurable name such as the shell tool — may also be
  > auto-approved, bypassing the human approval boundary. Ensure no other tool
  > collides with these reserved names.
- **Durable memory, two ways:**
  - **File memory** (coarse-grained, explicit) — the agent reads/writes files such as
    `watchlist.md`. File memory is on by default; its files live on disk under
    `{cwd}/agent-file-memory/<session-id>/`, so they persist across runs on this machine. A new
    session starts empty; use `/session-export` and `/session-import` to preserve the session id so a
    relaunch re-links to its memory files (no fixed folder or owner id required).
  - **Foundry memory** (fine-grained, automatic) — Microsoft Foundry extracts durable facts from
    the conversation. Opt-in; see below.

### Additional environment variables (optional — enable Foundry memory)

```bash
export FOUNDRY_MEMORY_STORE="claw-finance-memory"
export FOUNDRY_EMBEDDING_MODEL="text-embedding-3-small"
```

When these are not set, the sample runs with file memory only and prints a note.

### Running

```bash
uv run python/samples/02-agents/harness/build_your_own_claw/claw_step02_working_with_data.py
```

### What to expect

Try these in order (the sample starts in **execute** mode — quick lookups don't need a plan):

1. `What's in my portfolio?` — the agent reads `portfolio.csv` with the file_access tools.
2. `Write me a short report on my portfolio and save it.` — the agent writes a Markdown file under
   `working/`; saving is a write, so **you are prompted to approve** before the file is created.
3. `I'm a conservative investor saving for a house in two years.` — a durable fact (recalled later
   by Foundry memory when enabled).
4. `Buy 10 shares of MSFT.` — the agent calls `place_trade`; **you are prompted to approve or
   deny** before it runs.
5. `Add SPY to my watchlist.` — saved to `watchlist.md` in file memory.

Foundry memory (when enabled) recalls facts about you in any new session. File memory (the
watchlist) lives on disk keyed by session id, so `/session-export` before you quit and
`/session-import` after relaunching to re-link the relaunched session to its files, then ask
*"What's on my watchlist?"* or *"What do you know about me?"*.

## Part 3 — Scaling its capabilities

Makes the assistant *more capable* along four axes.

### What this sample demonstrates

- **Skills** — finance know-how (`valuation`, `risk-scoring`) is packaged as discoverable
  `SKILL.md` files under `skills/`, which the agent loads on demand. The sample builds a
  `FileSkillsSource(..., script_runner=subprocess_script_runner)` so the skills' Python
  scripts can run. Optionally folds in centrally-managed **Foundry skills** served from a
  Foundry Toolbox MCP endpoint via `MCPSkillsSource` (opt-in; see below).
- **Shell** — a `LocalShellTool` confined to the trade-confirmation vault
  (`working/confirmations/`) lets the agent tidy the accumulated confirmation files (reorganize into
  `year/month`, rename to `YYYY-MM-DD_TICKER_BUY|SELL.txt`). Guarded by a `ShellPolicy` deny-list
  **and** a confined working directory; left at the default
  `approval_mode="always_require"` so each command is surfaced for approval.
- **CodeAct** — a `MontyCodeActProvider` gives the agent a sandboxed, cross-platform Python
  interpreter to crunch portfolio numbers by writing and running code.
- **Background agents** — a lean, web-search-only `TickerResearchAgent` is registered via
  `create_harness_agent(background_agents=[...])`, so the main agent can fan out per-ticker research
  concurrently and aggregate the findings.

### Additional environment variables (optional)

```bash
# Enable centrally-managed Foundry skills (Foundry Toolbox MCP endpoint URL):
export FOUNDRY_TOOLBOX_MCP_SERVER_URL="https://<your-project>.services.ai.azure.com/.../toolboxes/<toolbox>/mcp?api-version=v1"
```

When this is not set, the sample runs with the local file skills only, and prints a note.

### Running

```bash
uv run python/samples/02-agents/harness/build_your_own_claw/claw_step03_scaling_capabilities.py
```

### What to expect

Try these in order (the sample starts in **execute** mode — quick lookups don't need a plan):

1. `Value MSFT for me.` — the agent loads the `valuation` skill and follows its instructions
   (reading references and running its script).
2. `Score the risk of my portfolio.` — the agent reads `portfolio.csv` and loads the `risk-scoring`
   skill.
3. `/mode plan`, then `Tidy up my trade confirmations.` — switching to plan mode first makes the
   agent inspect `working/confirmations/` and propose a reorganization plan before touching anything;
   once you approve it switches to execute and uses the shell to reorganize and rename the files,
   **prompting you to approve** each command.
4. `Work out the total value of my portfolio.` — the agent writes and runs Python via CodeAct.
5. `Research MSFT, NVDA and SPY and summarize the latest news.` — the agent fans the tickers out to
   the background research agent and aggregates the results.
6. `What's the capital of France?` — with a `financial-agent-rules` skill published to your Foundry
   toolbox and Foundry skills enabled (`FOUNDRY_TOOLBOX_MCP_SERVER_URL`), the agent loads it,
   recognizes the question is off-topic, and politely declines, steering you back to finance.

See the [Part 3 blog post](https://devblogs.microsoft.com/agent-framework/agent-harness-scaling-the-claw-or-harness-capabilities/)
for more on the `financial-agent-rules` skill — including the SKILL.md to publish to your Foundry toolbox.
