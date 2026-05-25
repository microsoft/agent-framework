# Agent with MCP long-running task (transparent polling)

This sample demonstrates Microsoft Agent Framework's MCP long-running task support: an agent invokes an MCP tool whose execution takes too long for a single request/response cycle, and the framework polls it to completion behind the function-calling loop. From the agent's perspective the tool simply returns its result.

## What this sample shows

- Using `McpClient.ListAgentToolsWithTaskSupportAsync(...)` (in `Microsoft.Agents.AI.Mcp`) to wrap MCP tools with task-aware behavior.
- Configuring `McpTaskOptions.DefaultTimeToLive` to bound the server-side task.
- Hosting a small MCP server (in this same executable, launched with `--server`) that advertises `execution.taskSupport=required` on a tool that sleeps for ~15 seconds.
- No application-level polling, continuation tokens, or `AllowBackgroundResponses` flag are required.

The decorator drives the lifecycle internally:

1. `tools/call` augmented with task metadata (`CallToolAsTaskAsync`)
2. `tasks/get` polled until terminal (`PollTaskUntilCompleteAsync`)
3. `tasks/result` retrieved (`GetTaskResultAsync`) and returned to the function-calling loop

The sample exercises both invocation styles against the same wrapper:

- `agent.RunAsync(...)` blocks until the tool completes (~15 seconds in this sample) and returns the final response.
- `agent.RunStreamingAsync(...)` returns immediately and yields `AgentResponseUpdate` chunks as the model emits them; in this scenario the model only begins streaming its answer once the wrapped tool's task reaches the `Completed` state, so the perceived "pause" before tokens arrive reflects tool execution time, not stream-channel latency.

# Prerequisites

- .NET 10 SDK or later
- Azure OpenAI service endpoint and a chat-completions deployment
- Azure CLI installed and authenticated (`az login`)

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"  # optional; defaults to gpt-5.4-mini
```

# Running

```powershell
cd Agent_MCP_LongRunningTask_Client
dotnet run
```

You should see output similar to:

```
=== Transparent long-running MCP task (RunAsync) ===
Asking the agent to analyze a dataset; the tool takes ~15s to complete.
RunAsync blocks while the wrapper polls the task to completion.

Agent response (after 15.4s):
The 'sales-2025-q1' dataset contains 12,403 rows ...

=== Transparent long-running MCP task (RunStreamingAsync) ===
Same request via the streaming API. Updates only begin to arrive after the
tool's task reaches the Completed state, since the model needs the tool result
before it can produce its final answer.

The 'sales-2025-q1' dataset contains 12,403 rows ...
(Streaming completed after 15.7s.)
```
