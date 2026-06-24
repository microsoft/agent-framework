# What this sample demonstrates

This sample demonstrates how to wrap a `HarnessAgent` with the **`LoopAgent`** decorator to re-invoke the agent until a configured **`LoopEvaluator`** decides to stop. A single decorator covers the common looping patterns — you just plug in a different evaluator (and optionally switch on fresh-context mode).

The `HarnessAgent` pre-configures function invocation, per-service-call chat history persistence, and in-loop compaction, so each demo only supplies the chat client, token limits, and instructions, then wraps the result with a `LoopAgent`.

## Looping patterns showcased

The program runs four demos sequentially, each driven by a different evaluator:

| # | Pattern | Evaluator | Notes |
| --- | --- | --- | --- |
| 1 | Completion-marker ("Ralph"-style) loop | `CompletionMarkerLoopEvaluator` | Re-invokes until the agent emits `<promise>COMPLETE</promise>`. Uses `FreshContextPerIteration = true` to restart each pass from the original task plus the aggregated feedback log on a new session, and includes the `{last_response}` placeholder in the feedback template so the agent sees its previous suggestion even though each pass starts fresh. |
| 2 | Delegate predicate (todos remaining) | `DelegateLoopEvaluator` | Loops while the built-in `TodoProvider` still has open items. The provider is fetched from the agent via `GetService<TodoProvider>()` and queried against the loop's current session. |
| 3 | AI judge | `AIJudgeLoopEvaluator` | A second `IChatClient` judges whether the original request was fully answered and continues while the answer is "no", injecting its gap analysis as the next input. |
| 4 | Approval heuristics + loop | `DelegateLoopEvaluator` + `ToolApprovalAgent` | Combines the `ToolApprovalAgent` auto-approval heuristics (`AutoApprovalRules`) with the loop, so a looped agent auto-approves tool calls instead of stalling on a pending approval. |

`MaxIterations` caps every loop so it always terminates even if the evaluator never stops.

### Evaluator mapping (Python → .NET)

The Python sample in [microsoft/agent-framework#6174](https://github.com/microsoft/agent-framework/pull/6174) exposes several distinct loop classes. In .NET these collapse into one `LoopAgent` that consumes evaluators:

| Python | .NET |
| --- | --- |
| Ralph loop (completion marker) | `LoopAgent` + `CompletionMarkerLoopEvaluator` |
| Ralph loop (fresh context each pass) | `LoopAgent` + `CompletionMarkerLoopEvaluator` + `FreshContextPerIteration = true` |
| Callable / predicate loop | `LoopAgent` + `DelegateLoopEvaluator` |
| AI judge loop | `LoopAgent` + `AIJudgeLoopEvaluator` |

## Prerequisites

Before running this sample, ensure you have:

1. An Azure AI Foundry project with a deployed model (e.g., `gpt-5.4`)
2. Azure CLI installed and authenticated (`az login`)

## Environment Variables

Set the following environment variables:

```bash
# Required: Your Azure AI Foundry project endpoint
export AZURE_AI_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"

# Optional: Model deployment name (defaults to gpt-5.4)
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4"
```

## Running the Sample

```bash
cd dotnet
dotnet run --project samples/02-agents/Harness/Harness_Step05_Loop
```

## What to Expect

The program runs the four demos in order. Each loop is executed with `RunStreamingAsync`, so output is printed live and every re-invocation of the inner agent is marked with a `--- run N ---` header (detected via a change in the streamed `ResponseId`) — this lets you see exactly when the `LoopAgent` loops. Each streamed message is prefixed with `User:` or `Agent:` based on its role, so the loop's on-behalf-of feedback messages (surfaced as `User` turns) are visually distinct from the agent's responses (`Agent`). Each demo finishes by printing its aggregated final response. Demo 4 also prints an `Auto-approving: ...` line each time the `ToolApprovalAgent` heuristic approves the `DeployService` tool call, showing how approval-aware agents integrate with the loop.
