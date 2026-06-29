# Build your own agent harness and claw — Python samples

Runnable Python samples for the [**"Build your own agent harness and claw with Microsoft Agent Framework"** blog](https://devblogs.microsoft.com/agent-framework/build-your-own-claw-and-agent-harness-with-microsoft-agent-framework)
series. Each step builds a personal finance / investing assistant on top of
`create_harness_agent`, reusing the shared harness `console` package in the parent `harness/`
directory.

- **Part 1 — `claw_step01_meet_your_claw.py`** — the minimal harness.

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

