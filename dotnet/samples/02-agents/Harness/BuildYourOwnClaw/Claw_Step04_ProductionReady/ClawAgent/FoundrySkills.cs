// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http.Headers;
using Azure.Core;
using ModelContextProtocol.Client;

namespace ClawAgent;

/// <summary>
/// Helpers for wiring centrally-managed Foundry skills into the claw via a Foundry Toolbox MCP endpoint.
/// </summary>
internal static class FoundrySkills
{
    /// <summary>
    /// Connects to a Foundry Toolbox MCP endpoint and returns a connected MCP client.
    /// </summary>
    public static async Task<(McpClient McpClient, HttpClient HttpClient)> ConnectAsync(
        string toolboxMcpServerUrl,
        TokenCredential credential,
        Func<string?>? foundryCallIdProvider = null,
        CancellationToken cancellationToken = default)
    {
        var httpClient = new HttpClient(new BearerTokenHandler(credential, "https://ai.azure.com/.default", foundryCallIdProvider)
        {
            InnerHandler = new HttpClientHandler(),
        });

        try
        {
            McpClient mcpClient = await McpClient.CreateAsync(
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
                    httpClient),
                cancellationToken: cancellationToken).ConfigureAwait(false);

            return (mcpClient, httpClient);
        }
        catch
        {
            httpClient.Dispose();
            throw;
        }
    }

    private sealed class BearerTokenHandler(
        TokenCredential credential,
        string scope,
        Func<string?>? foundryCallIdProvider) : DelegatingHandler
    {
        private readonly TokenRequestContext _tokenContext = new([scope]);

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            AccessToken token = await credential.GetTokenAsync(this._tokenContext, cancellationToken).ConfigureAwait(false);
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);

            string? callId = foundryCallIdProvider?.Invoke();
            if (!string.IsNullOrWhiteSpace(callId) && !request.Headers.Contains("x-agent-foundry-call-id"))
            {
                request.Headers.TryAddWithoutValidation("x-agent-foundry-call-id", callId);
            }

            return await base.SendAsync(request, cancellationToken).ConfigureAwait(false);
        }
    }
}
