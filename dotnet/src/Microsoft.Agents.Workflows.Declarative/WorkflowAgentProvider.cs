// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Azure.Core.Pipeline;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Base class for workflow agent providers.
/// </summary>
public abstract class WorkflowAgentProvider
{
    /// <summary>
    /// Asynchronously retrieves an AI agent by its unique identifier.
    /// </summary>
    /// <param name="agentId">The unique identifier of the AI agent to retrieve. Cannot be null or empty.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the <see cref="AIAgent"/> associated
    /// with the specified <paramref name="agentId"/>. Returns <see langword="null"/> if no agent is found.</returns>
    public abstract Task<AIAgent> GetAgentAsync(string agentId, CancellationToken cancellationToken = default);
}

/// <summary>
/// Provides functionality to interact with Foundry agents within a specified project context.
/// </summary>
/// <remarks>This class is used to retrieve and manage AI agents associated with a Foundry project.  It requires a
/// project endpoint and credentials to authenticate requests.</remarks>
/// <param name="projectEndpoint">The endpoint URL of the Foundry project. This must be a valid, non-null URI pointing to the project.</param>
/// <param name="projectCredentials">The credentials used to authenticate with the Foundry project. This must be a valid instance of <see cref="TokenCredential"/>.</param>
/// <param name="httpClient">An optional <see cref="HttpClient"/> instance to be used for making HTTP requests. If not provided, a default client will be used.</param>
public sealed class FoundryAgentProvider(string projectEndpoint, TokenCredential projectCredentials, HttpClient? httpClient = null) : WorkflowAgentProvider
{
    private PersistentAgentsClient? _agentsClient;

    /// <inheritdoc/>
    public override async Task<AIAgent> GetAgentAsync(string agentId, CancellationToken cancellationToken = default)
    {
        AIAgent agent = await this.GetAgentsClient().GetAIAgentAsync(agentId, chatOptions: null, cancellationToken).ConfigureAwait(false);

        return agent;
    }

    private PersistentAgentsClient GetAgentsClient()
    {
        if (this._agentsClient is null)
        {
            PersistentAgentsAdministrationClientOptions clientOptions = new();

            if (httpClient is not null)
            {
                clientOptions.Transport = new HttpClientTransport(httpClient);
            }

            PersistentAgentsClient newClient = new(projectEndpoint, projectCredentials, clientOptions);

            Interlocked.CompareExchange(ref this._agentsClient, newClient, null);
        }

        return this._agentsClient;
    }
}
