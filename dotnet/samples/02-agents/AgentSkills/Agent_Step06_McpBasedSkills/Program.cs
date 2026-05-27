// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to discover Agent Skills served over MCP.
//
// It connects an McpClient to an external MCP server that exposes skill
// resources following the SEP-2640 convention (skill://<skill-path>/<file-path>),
// plus a canonical "skill://index.json" discovery document. The skills provider
// reads the index, constructs skills from the entries, and injects them into
// the agent — exactly as for filesystem-backed skills.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using ModelContextProtocol.Client;
using OpenAI.Responses;

// --- Configuration ---
string openAiEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

string mcpEndpoint = Environment.GetEnvironmentVariable("MCP_SKILLS_ENDPOINT")
    ?? throw new InvalidOperationException("MCP_SKILLS_ENDPOINT is not set.");

// --- MCP client + skill discovery ---
Console.WriteLine($"Connecting to MCP skills endpoint: {mcpEndpoint}");

await using McpClient client = await McpClient.CreateAsync(
    new HttpClientTransport(
        new HttpClientTransportOptions
        {
            Endpoint = new Uri(mcpEndpoint),
            Name = "skills-server",
            TransportMode = HttpTransportMode.StreamableHttp,
        }));

var skillsProvider = new AgentSkillsProviderBuilder()
    .UseMcpSkills(client)
    .Build();

// --- Agent ---
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIAgent agent = new AzureOpenAIClient(new Uri(openAiEndpoint), new DefaultAzureCredential())
    .GetResponsesClient()
    .AsAIAgent(new ChatClientAgentOptions
    {
        Name = "SkillsAgent",
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant. Use available skills to answer the user.",
        },
        AIContextProviders = [skillsProvider],
    },
    model: deploymentName);

// --- Run ---
Console.WriteLine("\nType a message (or press Enter to quit):\n");

while (true)
{
    Console.Write("User: ");
    string? input = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(input))
    {
        break;
    }

    AgentResponse response = await agent.RunAsync(input);
    Console.WriteLine($"Agent: {response.Text}\n");
}
