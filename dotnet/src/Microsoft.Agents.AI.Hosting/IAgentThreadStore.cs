// Copyright (c) Microsoft. All rights reserved.

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
public abstract class AgentThreadStore
{
    /// <summary>
    /// Saves a serialized agent thread to persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this thread.</param>
    /// <param name="conversationId">The unique identifier for the conversation/thread.</param>
    /// <param name="thread">The thread to save.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    public abstract ValueTask SaveThreadAsync(
        AIAgent agent,
        string conversationId,
        AgentThread thread,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a serialized agent thread from persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this thread.</param>
    /// <param name="conversationId">The unique identifier for the conversation/thread to retrieve.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous retrieval operation.
    /// The task result contains the serialized thread state, or <see langword="null"/> if not found.
    /// </returns>
    public abstract ValueTask<AgentThread> GetThreadAsync(
        AIAgent agent,
        string conversationId,
        CancellationToken cancellationToken = default);
}
