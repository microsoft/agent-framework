// Copyright (c) Microsoft. All rights reserved.

// Connect to a published Copilot Studio agent and reuse its conversation across streaming turns.

using System.Net.Http.Headers;
using System.Text.Json;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.CopilotStudio;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Agents.CopilotStudio.Client.Discovery;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;

var settings = new ConnectionSettings
{
    Cloud = PowerPlatformCloud.Prod,
    CopilotAgentType = AgentType.Published,
    DirectConnectUrl = Environment.GetEnvironmentVariable("COPILOT_STUDIO_DIRECT_CONNECT_URL")
        ?? throw new InvalidOperationException("COPILOT_STUDIO_DIRECT_CONNECT_URL is not set."),
};
var credential = new InteractiveBrowserCredential(new InteractiveBrowserCredentialOptions
{
    TenantId = Environment.GetEnvironmentVariable("COPILOT_STUDIO_TENANT_ID")
        ?? throw new InvalidOperationException("COPILOT_STUDIO_TENANT_ID is not set."),
    ClientId = Environment.GetEnvironmentVariable("COPILOT_STUDIO_CLIENT_ID")
        ?? throw new InvalidOperationException("COPILOT_STUDIO_CLIENT_ID is not set."),
    RedirectUri = new Uri("http://localhost"),
});

// Derive the token scope from the trusted, operator-configured connection settings.
string scope = CopilotClient.ScopeFromSettings(settings);
ServiceCollection services = new();
services.AddHttpClient("copilot-studio")
    .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false })
    .AddHttpMessageHandler(() => new CopilotStudioTokenHandler(credential, scope));
using ServiceProvider provider = services.BuildServiceProvider();
CopilotClient client = new(settings, provider.GetRequiredService<IHttpClientFactory>(), NullLogger.Instance, "copilot-studio");
CopilotStudioAgent agent = new(client);
AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine("Ask your Copilot Studio agent a question. Enter /exit to finish.");
while (true)
{
    Console.Write("You: ");
    string? input = Console.ReadLine();
    if (input is null || string.Equals(input, "/exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    if (string.IsNullOrWhiteSpace(input))
    {
        continue;
    }

    Console.Write("Agent: ");
    await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(input, session))
    {
        Console.Write(update.Text);
    }

    Console.WriteLine();

    // Round-trip the session in memory. A real host can persist this JSON in caller-scoped storage.
    JsonElement savedSession = await agent.SerializeSessionAsync(session);
    session = await agent.DeserializeSessionAsync(savedSession);
}

internal sealed class CopilotStudioTokenHandler(TokenCredential credential, string scope) : DelegatingHandler
{
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        AccessToken token = await credential.GetTokenAsync(new TokenRequestContext([scope]), cancellationToken);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
        return await base.SendAsync(request, cancellationToken);
    }
}
