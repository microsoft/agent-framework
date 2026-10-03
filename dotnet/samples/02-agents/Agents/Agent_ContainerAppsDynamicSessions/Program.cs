// Copyright (c) Microsoft. All rights reserved.

// Expose Azure Container Apps Dynamic Sessions as an agent function tool.

using System.ComponentModel;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Azure.AI.Projects;
using Azure.Core;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string projectEndpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
    ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
string model = Environment.GetEnvironmentVariable("FOUNDRY_MODEL")
    ?? throw new InvalidOperationException("FOUNDRY_MODEL is not set.");
string poolEndpoint = Environment.GetEnvironmentVariable("POOL_MANAGEMENT_ENDPOINT")
    ?? throw new InvalidOperationException("POOL_MANAGEMENT_ENDPOINT is not set.");
Uri poolUri = new(poolEndpoint);
if (poolUri.Scheme != Uri.UriSchemeHttps || poolUri.UserInfo.Length != 0 || poolUri.Query.Length != 0 || poolUri.Fragment.Length != 0)
{
    throw new InvalidOperationException("POOL_MANAGEMENT_ENDPOINT must be a trusted HTTPS pool URL without credentials or a query.");
}

// One application-owned session per run. Reuse it for this agent's tool calls only.
string sessionId = Guid.NewGuid().ToString("N");
Uri executionUri = new($"{poolEndpoint.TrimEnd('/')}/executions?api-version=2025-10-02-preview&identifier={sessionId}");
AzureCliCredential credential = new();
using HttpClient httpClient = new(new HttpClientHandler { AllowAutoRedirect = false, CheckCertificateRevocationList = true }) { Timeout = TimeSpan.FromSeconds(70) };

AIAgent agent = new AIProjectClient(new Uri(projectEndpoint), credential).AsAIAgent(
    model: model,
    instructions: "Use ExecutePython for calculations. Check its status and errors before reporting a result.",
    tools: [AIFunctionFactory.Create(ExecutePythonAsync, "ExecutePython")]);

Console.WriteLine(await agent.RunAsync("Use Python to calculate the total of 19.95, 42.50, and 8.75, then add 8% tax."));

[Description("Run Python in the conversation's cloud sandbox and return its output and execution status.")]
async Task<JsonElement> ExecutePythonAsync([Description("Python code to execute in the remote session.")] string code, CancellationToken cancellationToken)
{
    AccessToken token = await credential.GetTokenAsync(new TokenRequestContext(["https://dynamicsessions.io/.default"]), cancellationToken);
    using HttpRequestMessage request = new(HttpMethod.Post, executionUri);
    request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
    request.Content = JsonContent.Create(new
    {
        codeInputType = "Inline",
        executionType = "Synchronous",
        code,
        timeoutInSeconds = 30,
        outputStreamsMaxLength = 4096,
    });
    using HttpResponseMessage response = await httpClient.SendAsync(request, cancellationToken);
    response.EnsureSuccessStatusCode();
    return await response.Content.ReadFromJsonAsync<JsonElement>(cancellationToken);
}
