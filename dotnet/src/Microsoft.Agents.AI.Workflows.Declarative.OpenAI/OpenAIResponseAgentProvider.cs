// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// $$$ COMMENT
/// </summary>
/// <param name="client">The service client.</param>
public sealed class OpenAIResponseAgentProvider(OpenAIClient client) : WorkflowAgentProvider
{
    /// <summary>
    /// The OpenAI client used to interact with the OpenAI service.
    /// </summary>
    public OpenAIClient Client { get; } = client;

    /// <inheritdoc/>
    public override async Task<string> CreateConversationAsync(CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }

    /// <inheritdoc/>
    public override async Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }

    /// <inheritdoc/>
    public override IAsyncEnumerable<AgentRunResponseUpdate> InvokeAgentAsync(
        string agentId,
        string? agentVersion,
        string? conversationId,
        IEnumerable<ChatMessage>? messages,
        IDictionary<string, object?>? inputArguments,
        CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }

    /// <inheritdoc/>
    public override async Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }

    /// <inheritdoc/>
    public override IAsyncEnumerable<ChatMessage> GetMessagesAsync(
        string conversationId,
        int? limit = null,
        string? after = null,
        string? before = null,
        bool newestFirst = false,
        CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }
}
