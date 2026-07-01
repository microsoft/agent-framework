# Scaling its capabilities (Post 3) — .NET

The third runnable sample from the [**"Build your own claw and agent harness with Microsoft Agent Framework"** blog](https://devblogs.microsoft.com/agent-framework/build-your-own-claw-and-agent-harness-with-microsoft-agent-framework)
series ([Part 3 — Scaling its capabilities](https://devblogs.microsoft.com/agent-framework/agent-harness-scaling-its-capabilities)).
It builds on Post 2's personal finance assistant and makes it *more capable* along four axes.

## What this sample demonstrates

- **Skills** — finance know-how (`valuation`, `risk-scoring`) is packaged as discoverable `SKILL.md`
  files under `skills/`, which the agent loads on demand. The sample builds its own provider with
  `AgentSkillsProviderBuilder.UseFileSkills([skillsDir], scriptRunner: new SubprocessScriptRunner().RunAsync)`
  so the skills' Python scripts can run, and sets `DisableAgentSkillsProvider = true` to replace the
  harness default. Optionally folds in centrally-managed **Foundry skills** discovered live from a
  Foundry **Toolbox MCP** endpoint via `FoundrySkills.ConnectAsync(...)` + `UseMcpSkills(...)`
  (opt-in; see below).
- **Shell** — a `LocalShellExecutor` confined to the trade-confirmation vault
  (`working/confirmations/`) lets the agent tidy the accumulated confirmation files (reorganize into
  `year/month`, rename to `YYYY-MM-DD_TICKER_BUY|SELL.txt`). `ConfineWorkingDirectory` re-anchors
  every command to the vault and a `ShellPolicy` deny-list pre-filters obviously destructive
  commands. Exposed as the `run_shell` tool, which prompts for approval before each command runs.
  (The deny-list is a UX guardrail, not a security boundary — for hard isolation use a
  `DockerShellExecutor`.)
- **CodeAct** — a `HyperlightCodeActProvider` gives the agent a sandboxed Python interpreter to
  crunch portfolio numbers by writing and running code. It runs on Hyperlight (a micro-VM), so it
  requires hardware virtualization. The guest module path is resolved automatically from the
  `Hyperlight.HyperlightSandbox.Guest.Python` NuGet package via `PythonGuestModule.GetModulePath()`.
- **Background agents** — a lean, web-search-only `ResearchAgent` is registered via
  `HarnessAgentOptions.BackgroundAgents`, exposing the `background_agents_*` tools so the main agent
  can fan out per-ticker research concurrently and aggregate the findings.

## Prerequisites

1. A Microsoft Foundry project with a deployed model (e.g. `gpt-5.4`).
2. Azure CLI installed and authenticated (`az login`).
3. *(For CodeAct)* a host with hardware virtualization enabled (Hyperlight runs the Python
   interpreter in a micro-VM).

## Environment variables

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
# Optional (defaults to gpt-5.4)
export FOUNDRY_MODEL="gpt-5.4"

# Optional — enable centrally-managed Foundry skills (Foundry Toolbox MCP endpoint URL):
export FOUNDRY_TOOLBOX_MCP_SERVER_URL="https://your-project.services.ai.azure.com/.../toolboxes/your-toolbox/mcp?api-version=v1"
```

When `FOUNDRY_TOOLBOX_MCP_SERVER_URL` is not set, the sample runs with the local file skills only and
prints a note.

## Running

```bash
cd dotnet
dotnet run --project samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step03_ScalingCapabilities
```

## What to expect

The sample starts an interactive loop in **execute** mode (quick lookups don't need a plan). Try
these in order:

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

See the [Part 3 blog post](https://devblogs.microsoft.com/agent-framework/agent-harness-scaling-its-capabilities)
for more on the `financial-agent-rules` skill — including the SKILL.md to publish to your Foundry toolbox.
