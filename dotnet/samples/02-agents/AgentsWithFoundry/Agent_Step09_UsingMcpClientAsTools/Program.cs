// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use MCP client tools with an agent.
// It connects to the Microsoft Learn MCP server via HTTP and uses its tools.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// Connect to the Microsoft Learn MCP server via HTTP (Streamable HTTP transport).
Console.WriteLine("Connecting to MCP server at https://learn.microsoft.com/api/mcp ...");

await using McpClient mcpClient = await McpClient.CreateAsync(new HttpClientTransport(new()
{
    Endpoint = new Uri("https://learn.microsoft.com/api/mcp"),
    Name = "Microsoft Learn MCP",
}));

// Retrieve the list of tools available on the MCP server.
IList<McpClientTool> mcpTools = await mcpClient.ListToolsAsync();
Console.WriteLine($"MCP tools available: {string.Join(", ", mcpTools.Select(t => t.Name))}");

List<AITool> agentTools = [.. mcpTools.Cast<AITool>()];

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

AIAgent agent = aiProjectClient.AsAIAgent(deploymentName,
    instructions: "You are a helpful assistant that can help with Microsoft documentation questions. Use the Microsoft Learn MCP tool to search for documentation.",
    name: "DocsAgent",
    tools: agentTools);

Console.WriteLine($"Agent '{agent.Name}' created. Asking a question...\n");

const string Prompt = "How does one create an Azure storage account using az cli?";
Console.WriteLine($"User: {Prompt}\n");
Console.WriteLine($"Agent: {await agent.RunAsync(Prompt)}");
