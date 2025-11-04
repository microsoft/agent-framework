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
    public override string Id => id ?? base.Id;
    public override string? Name => name ?? base.Name;

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return JsonSerializer.Deserialize<EchoAgentThread>(serializedThread, jsonSerializerOptions) ?? this.GetNewThread();
    }

    public override AgentThread GetNewThread()
    {
        return new EchoAgentThread();
    }

    private static ChatMessage UpdateThread(ChatMessage message, InMemoryAgentThread? thread = null)
    {
        thread?.MessageStore.Add(message);

        return message;
    }

    private IEnumerable<ChatMessage> EchoMessages(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null)
    {
        foreach (ChatMessage message in messages)
        {
            UpdateThread(message, thread as InMemoryAgentThread);
        }

        IEnumerable<ChatMessage> echoMessages
            = from message in messages
              where message.Role == ChatRole.User &&
                    !string.IsNullOrEmpty(message.Text)
              select
                    UpdateThread(new ChatMessage(ChatRole.Assistant, $"{prefix}{message.Text}")
                    {
                        AuthorName = this.DisplayName,
                        CreatedAt = DateTimeOffset.Now,
                        MessageId = Guid.NewGuid().ToString("N")
                    }, thread as InMemoryAgentThread);

        return echoMessages.Concat(this.GetEpilogueMessages(options).Select(m => UpdateThread(m, thread as InMemoryAgentThread)));
    }

    protected virtual IEnumerable<ChatMessage> GetEpilogueMessages(AgentRunOptions? options = null)
    {
        return Enumerable.Empty<ChatMessage>();
    }

    public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        AgentRunResponse result =
            new(this.EchoMessages(messages, thread, options).ToList())
            {
                AgentId = this.Id,
                CreatedAt = DateTimeOffset.Now,
                ResponseId = Guid.NewGuid().ToString("N"),
            };

        return Task.FromResult(result);
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string responseId = Guid.NewGuid().ToString("N");

        foreach (ChatMessage message in this.EchoMessages(messages, thread, options).ToList())
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

    private sealed class EchoAgentThread : InMemoryAgentThread
    {
    }
}
