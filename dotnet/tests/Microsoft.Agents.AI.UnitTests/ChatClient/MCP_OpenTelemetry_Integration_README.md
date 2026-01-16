# MCP + OpenTelemetry Integration Test

This directory contains tests for validating Activity/TraceId preservation when using MCP (Model Context Protocol) tools with OpenTelemetry distributed tracing.

## Tests

### 1. OpenTelemetryAgent_WithMockedMcpTool_PreservesTraceId

**Type**: Unit Test (Runnable)  
**Location**: `ChatClientAgent_McpOpenTelemetryIntegrationTests.cs`

This test validates the Activity/TraceId preservation pattern using mocked dependencies. It runs automatically in the test suite and requires no special setup.

**What it tests**:
- Creates a mock MCP tool that simulates async operations
- Wraps ChatClientAgent with OpenTelemetryAgent
- Verifies TraceId is preserved throughout the operation

**Run command**:
```bash
dotnet test --filter "FullyQualifiedName~OpenTelemetryAgent_WithMockedMcpTool" --framework net10.0
```

### 2. Full Integration Tests (Commented Out)

The full integration tests with real Azure OpenAI and MCP servers are commented out in the code to avoid compilation issues with missing dependencies in the unit test project.

**To run the full integration tests manually**:

1. **Create a test application** (recommended approach):
   - Use the sample code below or modify an existing MCP sample
   - Add OpenTelemetry instrumentation
   - Configure Azure OpenAI credentials

2. **Set environment variables**:
   ```bash
   export AZURE_OPENAI_ENDPOINT="https://your-instance.openai.azure.com"
   export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
   ```

3. **Ensure Azure CLI authentication**:
   ```bash
   az login
   ```

4. **Run the test application** and verify:
   - TraceId is preserved across all operations
   - MCP tool calls maintain the same TraceId
   - Streaming responses maintain TraceId in consumer code

## Manual Integration Test Sample

Here's a standalone sample that demonstrates the MCP + OpenTelemetry integration working correctly:

```csharp
using System.Diagnostics;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;
using OpenTelemetry;
using OpenTelemetry.Trace;

const string sourceName = "MCPIntegrationTest";

// Setup OpenTelemetry
using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .AddSource(sourceName)
    .AddSource("*Microsoft.Agents.AI")
    .AddConsoleExporter()  // Outputs to console for verification
    .Build();

using var activitySource = new ActivitySource(sourceName);
using var parentActivity = activitySource.StartActivity("MCP_Integration_Test");

Console.WriteLine($"Starting test with TraceId: {parentActivity?.TraceId}");

// Get Azure OpenAI configuration
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT not set");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Setup MCP client
await using var mcpClient = await McpClient.CreateAsync(new StdioClientTransport(new()
{
    Name = "TestMCPServer",
    Command = "npx",
    Arguments = ["-y", "@modelcontextprotocol/server-everything"],
}));

var mcpTools = await mcpClient.ListToolsAsync();
Console.WriteLine($"Found {mcpTools.Tools.Count} MCP tools");

// Create chat client
var azureClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());
var chatClient = azureClient.GetChatClient(deploymentName).AsIChatClient();

// Create inner agent with MCP tools
var innerAgent = new ChatClientAgent(
    chatClient,
    "You are a helpful assistant.",
    "MCPTestAgent",
    tools: [.. mcpTools.Tools.Cast<AITool>()]);

// Wrap with OpenTelemetryAgent to enable Activity preservation
using var agent = new OpenTelemetryAgent(innerAgent, sourceName);

// Invoke agent and verify TraceId is preserved
Console.WriteLine($"TraceId before invocation: {Activity.Current?.TraceId}");

var response = await agent.RunAsync("Add numbers 5 and 3");

Console.WriteLine($"TraceId after invocation: {Activity.Current?.TraceId}");
Console.WriteLine($"Response: {response.Messages[0].Text}");

// Verify TraceId was preserved
if (Activity.Current?.TraceId == parentActivity?.TraceId)
{
    Console.WriteLine("✅ SUCCESS: TraceId was preserved!");
}
else
{
    Console.WriteLine("❌ FAIL: TraceId was lost!");
}
```

## Expected Behavior

When the integration test runs successfully:

1. **Parent TraceId is created** at the start of the test
2. **TraceId is preserved** through:
   - Agent invocation
   - MCP tool execution (HTTP calls)
   - LLM API calls
   - Response processing
3. **All activities share the same TraceId**, creating a correlated trace
4. **Consumer code** (await foreach loops) has access to the same TraceId

## Troubleshooting

### TraceId is null or changes

- **Symptom**: TraceId becomes null or changes to a new value during execution
- **Cause**: Activity.Current is not being preserved across async boundaries
- **Solution**: Ensure OpenTelemetryAgent is wrapping the ChatClientAgent

### MCP server not found

- **Symptom**: Error about npx or MCP server not found
- **Cause**: Node.js or npx not installed
- **Solution**: Install Node.js and ensure npx is available in PATH

### Azure OpenAI authentication fails

- **Symptom**: Authentication errors when calling Azure OpenAI
- **Cause**: Azure CLI not configured or credentials expired
- **Solution**: Run `az login` and ensure proper access to Azure OpenAI resource

## Related Documentation

- [OpenTelemetry Sample](../../samples/GettingStarted/AgentOpenTelemetry/)
- [MCP Samples](../../samples/GettingStarted/ModelContextProtocol/)
- [Activity/TraceId Preservation Implementation](../../src/Microsoft.Agents.AI/OpenTelemetryAgent.cs)
