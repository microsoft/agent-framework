# Meet your claw (Post 1) — .NET

The first runnable sample from the [**"Build your own agent harness and claw with Microsoft Agent Framework"** blog](https://devblogs.microsoft.com/agent-framework/build-your-own-claw-and-agent-harness-with-microsoft-agent-framework)
series. It builds the foundation of a personal finance / investing assistant on top of a
`HarnessAgent`.

## What this sample demonstrates

- **`AsHarnessAgent`** — turns an `IChatClient` into a batteries-included agent: function
  invocation, per-service-call history persistence, planning
  (`TodoProvider` + `AgentModeProvider`), and web search.
- **A custom function tool** — `get_stock_price` (see `StockTools.cs`), exposing local data to the
  agent. Prices are illustrative mock data, not real quotes.
- **Web search** — provided automatically by the harness for market news and commentary.
- **Planning & modes** — the agent breaks a multi-step request ("Review my watchlist and recommend some stocks to add") into a todo
  list and switches between *plan* and *execute* modes.
- **Shared harness console** — interactive streaming UI with `/todos`, `/mode`, and `/exit`
  commands.

## Prerequisites

1. A Microsoft Foundry project with a deployed model (e.g. `gpt-5.4`).
2. Azure CLI installed and authenticated (`az login`).

## Environment variables

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
# Optional (defaults to gpt-5.4)
export FOUNDRY_MODEL="gpt-5.4"
```

## Running

```bash
cd dotnet
dotnet run --project samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step01_MeetYourClaw
```

## What to expect

The sample starts an interactive loop. Try these in order:

1. `/mode execute` — switch out of the default plan mode; quick lookups don't need a plan.
2. `What's the price of MSFT?` — the agent calls the `get_stock_price` tool.
3. `Any recent news on NVDA?` — the agent uses web search.
4. `Add MSFT, NVDA and SPY to my watch list` — saved to `watchlist.md` in the session's memory.
5. `/mode plan` — switch back to plan mode for a bigger, multi-step task.
6. `Review my watchlist and recommend some stocks to add` — the agent plans, then executes. Type
   `/todos` to see the list and `/mode` to inspect the current mode.

Output is colored by mode: **cyan** during planning, **green** during execution.
