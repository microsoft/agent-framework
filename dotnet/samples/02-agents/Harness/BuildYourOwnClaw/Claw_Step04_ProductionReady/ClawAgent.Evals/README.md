# ClawAgent.Evals

Evaluation host for the production-ready claw.

It builds the shared agent with `ClawAgentFactory`, runs local finance checks with `LocalEvaluator` and `FunctionEvaluator.Create(...)`, and prints `Passed`/`Total`. When `FOUNDRY_PROJECT_ENDPOINT` is available, it also runs Foundry quality evals (`FoundryEvals.Relevance` and `FoundryEvals.Coherence`).

The eval host auto-approves only Agent Skills tools so the trusted scripts bundled with this sample
can produce complete answers. Trades, shell commands, file writes, and unrelated tools remain subject
to their normal approval behavior.

## Run

```bash
cd dotnet
dotnet run --project samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step04_ProductionReady/ClawAgent.Evals
```
