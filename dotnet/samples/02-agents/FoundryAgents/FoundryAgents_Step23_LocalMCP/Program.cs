// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a local MCP (Model Context Protocol) client with Azure Foundry Agents.
// The MCP tools are resolved locally by connecting directly to the MCP server via HTTP,
// and then passed to the Foundry agent as client-side tools.
// This sample uses the Microsoft Learn MCP endpoint to search documentation.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string AgentInstructions = "You are a helpful assistant that can help with Microsoft documentation questions. Use the Microsoft Learn MCP tool to search for documentation.";
const string AgentName = "DocsAgent";

// Connect to the MCP server locally via HTTP (Streamable HTTP transport).
// The MCP server is hosted at Microsoft Learn and provides documentation search capabilities.
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

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

// Create the agent with the locally-resolved MCP tools.
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(
    model: deploymentName,
    name: AgentName,
    instructions: AgentInstructions,
    tools: wrappedTools);

Console.WriteLine($"Agent '{agent.Name}' created successfully.");

try
{
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
}
finally
{
    // Cleanup by removing the agent when done
    await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
    Console.WriteLine($"\nAgent '{agent.Name}' deleted.");
}

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
