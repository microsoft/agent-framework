// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a local MCP (Model Context Protocol) client with Microsoft Foundry Agents.
// The MCP tools are resolved locally by connecting directly to the MCP server via HTTP,
// and then passed to the Foundry agent as client-side tools.
// This sample uses the Microsoft Learn MCP endpoint to search documentation.

using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;
using OpenAI.Responses;
using SampleApp;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string AgentInstructions = "You are a helpful assistant that can help with Microsoft documentation questions. Use the Microsoft Learn MCP tool to search for documentation.";
const string AgentName = "DocsAgent";
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());

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

PromptAgentDefinition agentDefinition = new(model: deploymentName)
{
    Instructions = AgentInstructions
};

foreach (AITool tool in wrappedTools)
{
    agentDefinition.Tools.Add(tool.GetService<ResponseTool>() ?? tool.AsOpenAIResponseTool() ?? throw new InvalidOperationException("Unable to convert MCP tool to a ResponseTool."));
}

// Create the agent with the locally-resolved MCP tools.
AgentVersion agentVersion = await aiProjectClient.Agents.CreateAgentVersionAsync(
    AgentName,
    new AgentVersionCreationOptions(agentDefinition));
ChatClientAgent agent = aiProjectClient.AsAIAgent(agentVersion, wrappedTools);

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
