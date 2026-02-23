# Workflow Loop Sample

This sample demonstrates how to run a **cyclic workflow** (containing loops / back-edges) as a durable orchestration. The workflow iteratively improves a slogan based on AI feedback until it meets quality criteria.

## Key Concepts Demonstrated

- **Cyclic workflow support** — back-edges in the graph (A → B → A)
- **Multi-type executor handlers** — SloganWriter handles both `string` and `FeedbackResult` inputs
- **Message routing via `SendMessageAsync`** — FeedbackProvider sends messages back to SloganWriter
- **Workflow termination via `YieldOutputAsync`** — FeedbackProvider yields output when the slogan is accepted

## Overview

```
                  ┌──────────────────────┐
                  │                      │
     input ──→ SloganWriter ──→ FeedbackProvider
                  ▲                      │
                  │    (FeedbackResult)   │
                  └──────────────────────┘
                       back-edge
```

| Executor | Description |
|----------|-------------|
| SloganWriter | Generates slogans from user input; refines them based on feedback |
| FeedbackProvider | Evaluates slogans — accepts (YieldOutput) or loops (SendMessage) |

### Loop Behavior

1. **SloganWriter** generates a slogan based on user input
2. **FeedbackProvider** evaluates the slogan and provides a rating
3. If the rating is below the threshold (default: 9), feedback is sent back to SloganWriter
4. SloganWriter improves the slogan based on feedback
5. The loop continues until the slogan is accepted or max attempts (default: 3) are reached

## Environment Setup

See the [README.md](../README.md) file in the parent directory for information on configuring the environment, including how to install and run the Durable Task Scheduler.

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI deployment name |
| `AZURE_OPENAI_KEY` | (Optional) Azure OpenAI API key. If not set, uses Azure CLI credential |
| `DURABLE_TASK_SCHEDULER_CONNECTION_STRING` | (Optional) DTS connection string. Defaults to local emulator |

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/ConsoleApps/08_WorkflowLoop
dotnet run --framework net10.0
```

### Sample Output

```text
Workflow Loop Demo - Enter a topic for slogan generation (or 'exit'):
> sustainable energy
Started run: abc123...
  [FeedbackProvider] Rating 6/9 - sending back for refinement (attempt 1/3)
  [FeedbackProvider] Rating 8/9 - sending back for refinement (attempt 2/3)
  Event: WorkflowOutputEvent
  Completed: The following slogan was accepted:

Power the future, preserve the planet.
```
