// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Azure.AI.Agents.Persistent;

/// <summary>
/// Provides extension methods for <see cref="PersistentAgentsClient"/>.
/// </summary>
public static class PersistentAgentsClientExtensions
{
    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <returns>A <see cref="ChatClientAgent"/> for the persistent agent.</returns>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static async Task<ChatClientAgent> GetRunnableAgentAsync(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatOptions? chatOptions = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        if (string.IsNullOrWhiteSpace(agentId))
        {
            throw new ArgumentException($"{nameof(agentId)} should not be null or whitespace.", nameof(agentId));
        }

        var persistentAgentResponse = await persistentAgentsClient.Administration.GetAgentAsync(agentId, cancellationToken).ConfigureAwait(false);
        return persistentAgentResponse.AsRunnableAgent(persistentAgentsClient, chatOptions);
    }
}
