// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Azure.Core.Pipeline;
using Azure.Identity;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Provides functionality to interact with Foundry agents within a specified project context.
/// </summary>
/// <remarks>This class is used to retrieve and manage AI agents associated with a Foundry project.  It requires a
/// project endpoint and credentials to authenticate requests.</remarks>
/// <param name="projectEndpoint">The endpoint URL of the Foundry project. This must be a valid, non-null URI pointing to the project.</param>
/// <param name="projectCredentials">The credentials used to authenticate with the Foundry project. This must be a valid instance of <see cref="TokenCredential"/>.</param>
/// <param name="httpClient">An optional <see cref="HttpClient"/> instance to be used for making HTTP requests. If not provided, a default client will be used.</param>
public sealed class AzureAgentProvider(string projectEndpoint, TokenCredential? projectCredentials = null, HttpClient? httpClient = null) : WorkflowAgentProvider
{
    private PersistentAgentsClient? _agentsClient;

    /// <inheritdoc/>
    public override async Task<string> CreateConversationAsync(CancellationToken cancellationToken = default)
    {
        PersistentAgentThread conversation = await this.GetAgentsClient().Threads.CreateThreadAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
        return conversation.Id;
    }

    /// <inheritdoc/>
    public override async Task CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default)
    {
        //await this.GetAgentsClient().Messages.CreateMessageAsync(conversationId, conversationMessage, cancellationToken).ConfigureAwait(false); // %%% TODO
        await Task.Delay(0, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async Task<AIAgent> GetAgentAsync(string agentId, CancellationToken cancellationToken = default)
    {
        AIAgent agent = await this.GetAgentsClient().GetAIAgentAsync(agentId, chatOptions: null, cancellationToken).ConfigureAwait(false);

        return agent;
    }

    /// <inheritdoc/>
    public override async Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default)
    {
        PersistentThreadMessage message = await this.GetAgentsClient().Messages.GetMessageAsync(conversationId, messageId, cancellationToken).ConfigureAwait(false);
        return message.ToChatMessage();
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatMessage> GetMessagesAsync(
        string conversationId,
        int? limit = null,
        string? after = null,
        string? before = null,
        bool newestFirst = false,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ListSortOrder order = newestFirst ? ListSortOrder.Ascending : ListSortOrder.Descending;
        await foreach (PersistentThreadMessage message in this.GetAgentsClient().Messages.GetMessagesAsync(conversationId, runId: null, limit, order, after, before, cancellationToken).ConfigureAwait(false))
        {
            yield return message.ToChatMessage();
        }
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

            PersistentAgentsClient newClient = new(projectEndpoint, projectCredentials ?? new DefaultAzureCredential(), clientOptions);

            Interlocked.CompareExchange(ref this._agentsClient, newClient, null);
        }

        return this._agentsClient;
    }
}
