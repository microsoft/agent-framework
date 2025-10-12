// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Defines the contract for storing and retrieving agent conversation threads.
/// </summary>
/// <remarks>
/// Implementations of this interface enable persistent storage of conversation threads,
/// allowing conversations to be resumed across HTTP requests, application restarts,
/// or different service instances in hosted scenarios.
/// </remarks>
public interface IAgentThreadStore
{
    /// <summary>
    /// Saves a serialized agent thread to persistent storage.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation/thread.</param>
    /// <param name="agentId">The identifier of the agent that owns this thread.</param>
    /// <param name="thread">The thread to save.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    /// <remarks>
    /// The <paramref name="conversationId"/> is used as the primary key for thread lookup.
    /// The <paramref name="agentId"/> provides additional scoping to prevent cross-agent thread access.
    /// </remarks>
    ValueTask SaveThreadAsync(
        string conversationId,
        string agentId,
        AgentThread thread,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a serialized agent thread from persistent storage.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation/thread to retrieve.</param>
    /// <param name="agentId">The identifier of the agent that owns this thread.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous retrieval operation.
    /// The task result contains the serialized thread state, or <see langword="null"/> if not found.
    /// </returns>
    ValueTask<JsonElement?> GetOrCreateThreadAsync(
        string conversationId,
        string agentId,
        CancellationToken cancellationToken = default);
}
