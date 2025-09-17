// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
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
    /// <returns>The task result contains the <see cref="AIAgent"/> associated.</returns>
    public abstract Task<AIAgent> GetAgentAsync(string agentId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Asynchronously creates a new conversation and returns its unique identifier.
    /// </summary>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>The conversation identifier</returns>
    public abstract Task<string> CreateConversationAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Creates a new message in the specified conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of the target conversation.</param>
    /// <param name="conversationMessage">The message being added.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    public abstract Task CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a specific message from a conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of the target conversation.</param>
    /// <param name="messageId">The identifier of the target message.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>The requested message</returns>
    public abstract Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves a set of messages from a conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of the target conversation.</param>
    /// <param name="limit">A limit on the number of objects to be returned. Limit can range between 1 and 100, and the default is 20.</param>
    /// <param name="after">A cursor for use in pagination. after is an object ID that defines your place in the list.</param>
    /// <param name="before">A cursor for use in pagination. before is an object ID that defines your place in the list.</param>
    /// <param name="newestFirst">Provide records in descending order when true.</param>
    /// <param name="cancellationToken">A cancellation token that can be used to cancel the operation.</param>
    /// <returns>The requested messages</returns>
    public abstract IAsyncEnumerable<ChatMessage> GetMessagesAsync(
        string conversationId,
        int? limit = null,
        string? after = null,
        string? before = null,
        bool newestFirst = false,
        CancellationToken cancellationToken = default);
}
