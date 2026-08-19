# Agent with MCP Tasks extension (transparent polling)

This sample demonstrates Microsoft Agent Framework's support for the MCP 2026-07-28 Tasks extension: an agent invokes an MCP tool whose execution takes too long for a single request/response cycle, and the framework polls it to completion behind the function-calling loop. From the agent's perspective the tool simply returns its result.

## What this sample shows

- Using `McpClient.ListAgentToolsWithTasksAsync(...)` (in `Microsoft.Agents.AI.Mcp`) to wrap MCP tools with task-aware behavior.
- Hosting a small MCP server (in this same executable, launched with `--server`) that enables `io.modelcontextprotocol/tasks` with `WithTasks(...)` and exposes a tool that sleeps for ~15 seconds.
- Allowing the server to return either an inline result or a task handle after the client opts into the extension.
- No application-level polling, continuation tokens, or `AllowBackgroundResponses` flag are required.

The decorator drives the lifecycle internally:

1. `tools/call` includes the Tasks extension capability.
2. The server returns either the ordinary tool result or a task handle.
3. `tasks/get` is polled until it carries the final result, which is returned to the function-calling loop.

The transparent adapter uses the MCP SDK's automatic poller. Cancelling the local invocation stops polling, but it does not automatically send `tasks/cancel` because the poller does not expose the created task ID. Applications that need task handles or explicit remote cancellation can use `ModelContextProtocol.Extensions.Tasks` directly.

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
