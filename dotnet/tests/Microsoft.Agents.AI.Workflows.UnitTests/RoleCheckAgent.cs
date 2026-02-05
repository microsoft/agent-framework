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

    public override ValueTask<AgentSession> DeserializeSessionAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => new(new RoleCheckAgentSession());

    public override JsonElement SerializeSession(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null)
        => default;

    public override ValueTask<AgentSession> CreateSessionAsync(CancellationToken cancellationToken = default) => new(new RoleCheckAgentSession());

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.RunStreamingAsync(messages, session, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (ChatMessage message in messages)
        {
            if (!allowOtherAssistantRoles && message.Role == ChatRole.Assistant && !(message.AuthorName == null || message.AuthorName == this.Name))
            {
                throw new InvalidOperationException($"Message from other assistant role detected: AuthorName={message.AuthorName}");
            }
        }

        yield return new AgentResponseUpdate(ChatRole.Assistant, "Ok")
        {
            AgentId = this.Id,
            AuthorName = this.Name,
            MessageId = Guid.NewGuid().ToString("N"),
            ResponseId = Guid.NewGuid().ToString("N")
        };
    }

    private sealed class RoleCheckAgentSession : InMemoryAgentSession;
}
