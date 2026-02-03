// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal class TestEchoAgent(string? id = null, string? name = null, string? prefix = null) : AIAgent
{
    protected override string? IdCore => id;
    public override string? Name => name ?? base.Name;

    public override async ValueTask<AgentSession> DeserializeSessionAsync(JsonElement serializedSession, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        return serializedSession.Deserialize<EchoAgentSession>(jsonSerializerOptions) ?? await this.CreateSessionAsync(cancellationToken);
    }

    public override ValueTask<AgentSession> CreateSessionAsync(CancellationToken cancellationToken = default) =>
        new(new EchoAgentSession());

    private static ChatMessage UpdateSession(ChatMessage message, InMemoryAgentSession? session = null)
    {
        session?.ChatHistoryProvider.Add(message);

        return message;
    }

    private IEnumerable<ChatMessage> EchoMessages(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null)
    {
        foreach (ChatMessage message in messages)
        {
            UpdateSession(message, session as InMemoryAgentSession);
        }

        IEnumerable<ChatMessage> echoMessages
            = from message in messages
              where message.Role == ChatRole.User &&
                    !string.IsNullOrEmpty(message.Text)
              select
                    UpdateSession(new ChatMessage(ChatRole.Assistant, $"{prefix}{message.Text}")
                    {
                        AuthorName = this.Name ?? this.Id,
                        CreatedAt = DateTimeOffset.Now,
                        MessageId = Guid.NewGuid().ToString("N")
                    }, session as InMemoryAgentSession);

        return echoMessages.Concat(this.GetEpilogueMessages(options).Select(m => UpdateSession(m, session as InMemoryAgentSession)));
    }

    protected virtual IEnumerable<ChatMessage> GetEpilogueMessages(AgentRunOptions? options = null)
    {
        return [];
    }

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        AgentResponse result =
            new(this.EchoMessages(messages, session, options).ToList())
            {
                AgentId = this.Id,
                CreatedAt = DateTimeOffset.Now,
                ResponseId = Guid.NewGuid().ToString("N"),
            };

        return Task.FromResult(result);
    }

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string responseId = Guid.NewGuid().ToString("N");

        foreach (ChatMessage message in this.EchoMessages(messages, session, options).ToList())
        {
            yield return
                new(message.Role, message.Contents)
                {
                    AgentId = this.Id,
                    AuthorName = message.AuthorName,
                    ResponseId = responseId,
                    MessageId = message.MessageId,
                    CreatedAt = message.CreatedAt
                };
        }
    }

    private sealed class EchoAgentSession : InMemoryAgentSession;
}
