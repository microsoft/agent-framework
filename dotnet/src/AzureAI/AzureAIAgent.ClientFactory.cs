// Copyright (c) Microsoft. All rights reserved.
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Azure.Core.Pipeline;
using System.Net.Http;

namespace Microsoft.Agents.AzureAI;

/// <summary>
/// Provides an <see cref="PersistentAgentsClient"/> for use by <see cref="AzureAIAgent"/>.
/// </summary>
public sealed partial class AzureAIAgent : Agent
{
    /// <summary>
    /// Produces a <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="endpoint">The Azure AI Foundry project endpoint.</param>
    /// <param name="credential"> A credential used to authenticate to an Azure Service.</param>
    /// <param name="httpClient">A custom <see cref="HttpClient"/> for HTTP requests.</param>
    public static PersistentAgentsClient CreateAgentsClient(
        string endpoint,
        TokenCredential credential,
        HttpClient? httpClient = null)
    {
        Verify.NotNull(endpoint, nameof(endpoint));
        Verify.NotNull(credential, nameof(credential));

        PersistentAgentsAdministrationClientOptions clientOptions = CreateAzureClientOptions(httpClient);

        return new PersistentAgentsClient(endpoint, credential, clientOptions);
    }

    private static PersistentAgentsAdministrationClientOptions CreateAzureClientOptions(HttpClient? httpClient)
    {
        PersistentAgentsAdministrationClientOptions options = new();

        if (httpClient is not null)
        {
            options.Transport = new HttpClientTransport(httpClient);
            // Disable retry policy if and only if a custom HttpClient is provided.
            options.RetryPolicy = new RetryPolicy(maxRetries: 0);
        }

        return options;
    }
}
