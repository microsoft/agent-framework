// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations;

/// <summary>
/// Optional service for indexing conversations by agent ID.
/// This is a non-standard extension to the OpenAI Conversations API.
/// </summary>
internal interface IAgentConversationIndex
{
    /// <summary>
    /// Adds a conversation to the index for the specified agent.
    /// </summary>
    /// <param name="agentId">The agent identifier.</param>
    /// <param name="conversationId">The conversation identifier.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    Task AddConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Removes a conversation from the index for the specified agent.
    /// </summary>
    /// <param name="agentId">The agent identifier.</param>
    /// <param name="conversationId">The conversation identifier.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A task that represents the asynchronous operation.</returns>
    Task RemoveConversationAsync(string agentId, string conversationId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Gets all conversation IDs for the specified agent.
    /// </summary>
    /// <param name="agentId">The agent identifier.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>A list response containing conversation IDs associated with the agent.</returns>
    Task<ListResponse<string>> GetConversationIdsAsync(string agentId, CancellationToken cancellationToken = default);
}
