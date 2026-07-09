# Working with your data, safely (Post 2) — .NET

The second runnable sample from the [**"Build your own claw and agent harness with Microsoft Agent Framework"** blog](https://devblogs.microsoft.com/agent-framework/build-your-own-claw-and-agent-harness-with-microsoft-agent-framework)
series ([Part 2 — Working with your data, safely](https://devblogs.microsoft.com/agent-framework/agent-harness-working-with-your-data-safely)).
It builds on Post 1's personal finance assistant and teaches it to work with *your* data safely.

## What this sample demonstrates

- **File access** — the agent reads a pre-populated `working/portfolio.csv` and writes reports
  (e.g. `reports/portfolio-review.md`) with the built-in `file_access_*` tools. A custom
  `FileAccessStore` roots those tools at the sample's `working/` folder.
- **Approvals** — file-access tools require approval by default, but the sample wires the built-in
  `FileAccessProvider.ReadOnlyToolsAutoApprovalRule` so reads/lists/searches are frictionless while
  saving and deleting still pause for approval. The `place_trade` tool is also wrapped in an
  `ApprovalRequiredAIFunction` (see `TradingTools.cs`), so the harness surfaces an approval prompt
  before any trade runs. The trade itself is simulated — no real order is placed.
- **Durable memory, two ways:**
  - **File memory** (coarse-grained, explicit) — the agent reads/writes files such as
    `watchlist.md`. File memory is on by default; its files live on disk under
    `{cwd}/agent-file-memory/<session-id>/`, so they persist across runs on this machine. A new
    session starts empty; use `/session-export` and `/session-import` to preserve the session id so a
    relaunch re-links to its memory files (no fixed folder required).
  - **Foundry memory** (fine-grained, automatic) — Microsoft Foundry extracts durable facts (e.g.
    your risk tolerance) from the conversation. Opt-in; see below.

## Prerequisites

1. A Microsoft Foundry project with a deployed model (e.g. `gpt-5.4`).
2. Azure CLI installed and authenticated (`az login`).
3. *(Optional, for Foundry memory)* a deployed embedding model and a memory store name.

## Environment variables

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
# Optional (defaults to gpt-5.4)
export FOUNDRY_MODEL="gpt-5.4"

# Optional — enable fine-grained Foundry memory (both must be set):
export FOUNDRY_MEMORY_STORE="claw-finance-memory"
export FOUNDRY_EMBEDDING_MODEL="text-embedding-3-small"
```

When the Foundry memory variables are not set, the sample runs with file memory only and prints a
note.

## Running

```bash
cd dotnet
dotnet run --project samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step02_WorkingWithData
```

## What to expect

The sample starts an interactive loop in **execute** mode (quick lookups don't need a plan). Try
these in order:

1. `What's in my portfolio?` — the agent reads `portfolio.csv` with the file_access tools.
2. `Write me a short report on my portfolio and save it.` — the agent writes a Markdown file
   under `working/`; saving is a write, so **you are prompted to approve** before it lands.
3. `I'm a conservative investor saving for a house in two years.` — a durable fact (recalled later
   by Foundry memory when enabled).
4. `Buy 10 shares of MSFT.` — the agent calls `place_trade`; **you are prompted to approve or
   deny** before it runs.
5. `Add SPY to my watchlist.` — saved to `watchlist.md` in file memory.

Restart the app to see memory persist across runs:

- **Foundry memory** (when enabled) recalls facts about you in any new session — it's scoped to you,
  not the session.
- **File memory** (the watchlist) lives on disk keyed by session id, so `/session-export` before you
  quit and `/session-import` after relaunching to re-link the relaunched session to its files.
