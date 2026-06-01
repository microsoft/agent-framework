// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Defines the contract for storing and retrieving agent conversation sessions.
/// </summary>
/// <remarks>
/// Implementations of this interface enable persistent storage of conversation sessions,
/// allowing conversations to be resumed across HTTP requests, application restarts,
/// or different service instances in hosted scenarios.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public abstract class AgentSessionStore
{
    /// <summary>
    /// Saves a serialized agent session to persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="conversationId">The unique identifier for the conversation/session.</param>
    /// <param name="session">The session to save.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task that represents the asynchronous save operation.</returns>
    public abstract ValueTask SaveSessionAsync(
        AIAgent agent,
        string conversationId,
        AgentSession session,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a serialized agent session from persistent storage.
    /// </summary>
    /// <param name="agent">The agent that owns this session.</param>
    /// <param name="conversationId">The unique identifier for the conversation/session to retrieve.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous retrieval operation.
    /// The task result contains the session, or a new session if not found.
    /// </returns>
    public abstract ValueTask<AgentSession> GetSessionAsync(
        AIAgent agent,
        string conversationId,
        CancellationToken cancellationToken = default);
}
