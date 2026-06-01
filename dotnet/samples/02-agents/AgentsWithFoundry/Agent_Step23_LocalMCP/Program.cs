// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to wrap MCP tools with a DelegatingAIFunction to add custom behavior (e.g., logging).
// Compare with Step09 which shows basic MCP tool usage without wrapping.
// The LoggingMcpTool pattern is useful for diagnostics, metering, or adding approval logic around tool calls.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;
using SampleApp;

const string AgentInstructions = "You are a helpful assistant that can help with Microsoft documentation questions. Use the Microsoft Learn MCP tool to search for documentation.";
const string AgentName = "DocsAgent-RAPI";

// Connect to the MCP server locally via HTTP (Streamable HTTP transport).
Console.WriteLine("Connecting to MCP server at https://learn.microsoft.com/api/mcp ...");

await using McpClient mcpClient = await McpClient.CreateAsync(new HttpClientTransport(new()
{
    Endpoint = new Uri("https://learn.microsoft.com/api/mcp"),
    Name = "Microsoft Learn MCP",
}));

// Retrieve the list of tools available on the MCP server (resolved locally).
IList<McpClientTool> mcpTools = await mcpClient.ListToolsAsync();
Console.WriteLine($"MCP tools available: {string.Join(", ", mcpTools.Select(t => t.Name))}");

// Wrap each MCP tool with a DelegatingAIFunction to log local invocations.
List<AITool> wrappedTools = mcpTools.Select(tool => (AITool)new LoggingMcpTool(tool)).ToList();

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create a AIAgent with the locally-resolved MCP tools.
AIAgent agent = aiProjectClient.AsAIAgent(deploymentName,
    instructions: AgentInstructions,
    name: AgentName,
    tools: wrappedTools);

Console.WriteLine($"Agent '{agent.Name}' created successfully.");

// First query
const string Prompt1 = "How does one create an Azure storage account using az cli?";
Console.WriteLine($"\nUser: {Prompt1}\n");
AgentResponse response1 = await agent.RunAsync(Prompt1);
Console.WriteLine($"Agent: {response1}");

Console.WriteLine("\n=======================================\n");

// Second query
const string Prompt2 = "What is Microsoft Agent Framework?";
Console.WriteLine($"User: {Prompt2}\n");
AgentResponse response2 = await agent.RunAsync(Prompt2);
Console.WriteLine($"Agent: {response2}");

namespace SampleApp
{
    /// <summary>
    /// Wraps an MCP tool to log when it is invoked locally,
    /// confirming that the MCP call is happening client-side.
    /// </summary>
    internal sealed class LoggingMcpTool(AIFunction innerFunction) : DelegatingAIFunction(innerFunction)
    {
        protected override ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, CancellationToken cancellationToken)
        {
            Console.WriteLine($"  >> [LOCAL MCP] Invoking tool '{this.Name}' locally...");
            return base.InvokeCoreAsync(arguments, cancellationToken);
        }
    }
}
