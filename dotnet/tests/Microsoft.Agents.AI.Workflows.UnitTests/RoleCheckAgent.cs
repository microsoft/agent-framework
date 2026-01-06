// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class RoleCheckAgent(bool allowOtherAssistantRoles, string? id = null, string? name = null) : AIAgent
{
    protected override string? IdCore => id;

    public override string? Name => name;

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => new RoleCheckAgentThread();

    public override AgentThread GetNewThread() => new RoleCheckAgentThread();

    protected override Task<AgentRunResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.RunStreamingAsync(messages, thread, options, cancellationToken).ToAgentRunResponseAsync(cancellationToken);

    protected override async IAsyncEnumerable<AgentRunResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (ChatMessage message in messages)
        {
            if (!allowOtherAssistantRoles && message.Role == ChatRole.Assistant && !(message.AuthorName == null || message.AuthorName == this.Name))
            {
                throw new InvalidOperationException($"Message from other assistant role detected: AuthorName={message.AuthorName}");
            }
        }

        yield return new AgentRunResponseUpdate(ChatRole.Assistant, "Ok")
        {
            AgentId = this.Id,
            AuthorName = this.Name,
            MessageId = Guid.NewGuid().ToString("N"),
            ResponseId = Guid.NewGuid().ToString("N")
        };
    }

    private sealed class RoleCheckAgentThread : InMemoryAgentThread;
}
