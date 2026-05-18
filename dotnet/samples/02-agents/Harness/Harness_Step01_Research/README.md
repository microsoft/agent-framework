# What this sample demonstrates

This sample demonstrates how to use a `HarnessAgent` with the Harness `AIContextProviders` (`TodoProvider` and `AgentModeProvider`) for interactive research tasks with web search capabilities powered by Azure AI Foundry. The `HarnessAgent` pre-configures function invocation, per-service-call chat history persistence, and context-window compaction.

Key features showcased:

- **HarnessAgent** — a pre-configured agent that wraps a `ChatClientAgent` with function invocation, per-service-call persistence, and context-window compaction
- **ToolApproval** — the agent is wrapped with `UseToolApproval()` to allow auto-approving tools once confirmed
- **Web Search** — the agent can search the web for current information via `ResponseTool.CreateWebSearchTool()`
- **TodoProvider** — the agent creates and manages a todo list to track research questions
- **AgentModeProvider** — the agent switches between "plan" mode (breaking down the topic) and "execute" mode (answering each research question)
- **Interactive conversation** — you can review the agent's plan, provide feedback, and approve before execution begins
- **Streaming output** — responses are streamed token-by-token for a natural experience
- **`/todos` command** — view the current todo list at any time without invoking the agent
- **Mode-based coloring** — console output is colored based on the agent's current mode (cyan for plan, green for execute)

## Prerequisites

Before running this sample, ensure you have:

1. An Azure AI Foundry project with a deployed model (e.g., `gpt-5.4`)
2. Azure CLI installed and authenticated (`az login`)

## Environment Variables

Set the following environment variables:

```bash
# Required: Your Azure AI Foundry OpenAI endpoint
export AZURE_FOUNDRY_OPENAI_ENDPOINT="https://your-project.services.ai.azure.com/openai/v1/"

# Optional: Model deployment name (defaults to gpt-5.4)
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4"
```

## Running the Sample

```bash
cd dotnet
dotnet run --project samples/02-agents/Harness/Harness_Step01_Research
```

## What to Expect

The sample starts an interactive conversation loop. You can:

1. **Enter a research topic** — the agent will analyze it and create a plan with todos
2. **Review and adjust** — provide feedback on the plan, ask for changes, or approve it
3. **Type `/todos`** — to see the current todo list at any time
4. **Watch execution** — once approved, tell the agent to proceed and it will work through each todo
5. **Type `exit`** — to end the session

The prompt and agent output are colored by the current mode: **cyan** during planning, **green** during execution.
