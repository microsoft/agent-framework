// Copyright (c) Microsoft. All rights reserved.

// Foundry Toolbox MCP Skills.
//
// Uses AgentSkillsProviderBuilder to discover MCP-based skills from a Foundry
// Toolbox endpoint and inject them as AIContextProviders so the agent can
// discover and use them at runtime.

using System.Net.Http.Headers;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using ModelContextProtocol.Client;

// --- Configuration ---
string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";
string toolboxMcpServerUrl = Environment.GetEnvironmentVariable("FOUNDRY_TOOLBOX_MCP_SERVER_URL")
    ?? throw new InvalidOperationException("FOUNDRY_TOOLBOX_MCP_SERVER_URL is not set.");

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
TokenCredential credential = new DefaultAzureCredential();

using var httpClient = new HttpClient(new BearerTokenHandler(credential, "https://ai.azure.com/.default")
{
    InnerHandler = new HttpClientHandler(),
});

// --- Connect to the Foundry Toolbox MCP endpoint ---
await using McpClient mcpClient = await McpClient.CreateAsync(
    new HttpClientTransport(
        new HttpClientTransportOptions
        {
            Endpoint = new Uri(toolboxMcpServerUrl),
            Name = "foundry_toolbox",
            TransportMode = HttpTransportMode.StreamableHttp,
            AdditionalHeaders = new Dictionary<string, string>
            {
                ["Foundry-Features"] = "Toolboxes=V1Preview",
            },
        },
        httpClient));

// --- Discover MCP-based skills ---
var skillsProvider = new AgentSkillsProviderBuilder()
    .UseMcpSkills(mcpClient)
    .Build();

// --- Create the agent ---
AIProjectClient aiProjectClient = new(new Uri(endpoint), credential);

AIAgent agent = aiProjectClient.AsAIAgent(
    options: new ChatClientAgentOptions
    {
        Name = "ToolboxMcpSkillsAgent",
        ChatOptions = new()
        {
            ModelId = deploymentName,
            Instructions = "You are a helpful assistant. Use available skills to answer the user.",
        },
        AIContextProviders = [skillsProvider],
    });

// --- Interactive prompt ---
Console.Write("User: ");
string? query = Console.ReadLine();

if (string.IsNullOrWhiteSpace(query))
{
    Console.WriteLine("No input provided.");
    return;
}

Console.WriteLine($"Assistant: {await agent.RunAsync(query)}");

// ---------------------------------------------------------------------------
// DelegatingHandler: attaches a fresh Foundry bearer token to every request
// ---------------------------------------------------------------------------
internal sealed class BearerTokenHandler(TokenCredential credential, string scope) : DelegatingHandler
{
    private readonly TokenRequestContext _tokenContext = new([scope]);

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        AccessToken token = await credential.GetTokenAsync(this._tokenContext, cancellationToken).ConfigureAwait(false);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
        return await base.SendAsync(request, cancellationToken).ConfigureAwait(false);
    }
}
