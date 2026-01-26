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

public class TestReplayAgent(List<ChatMessage>? messages = null, string? id = null, string? name = null) : AIAgent
{
    protected override string? IdCore => id;
    public override string? Name => name;

    public static List<ChatMessage> ToChatMessages(params string[] messages)
    {
        List<ChatMessage> result = messages.Select(ToMessage).ToList();

        static ChatMessage ToMessage(string text)
        {
            if (string.IsNullOrEmpty(text))
            {
                return new ChatMessage(ChatRole.Assistant, "") { MessageId = "" };
            }

            string[] splits = text.Split(' ');
            for (int i = 0; i < splits.Length - 1; i++)
            {
                splits[i] += ' ';
            }

            List<AIContent> contents = splits.Select<string, AIContent>(text => new TextContent(text) { RawRepresentation = text }).ToList();
            return new(ChatRole.Assistant, contents)
            {
                MessageId = Guid.NewGuid().ToString("N"),
                RawRepresentation = text,
                CreatedAt = DateTime.UtcNow,
            };
        }

        return result;
    }

    public override ValueTask<AgentThread> GetNewThreadAsync(CancellationToken cancellationToken = default)
        => new(new ReplayAgentThread());

    public override ValueTask<AgentThread> DeserializeThreadAsync(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => new(new ReplayAgentThread());

    public static TestReplayAgent FromStrings(params string[] messages) =>
        new(ToChatMessages(messages));

    public List<ChatMessage> Messages { get; } = Validate(messages) ?? [];

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        => this.RunStreamingAsync(messages, thread, options, cancellationToken).ToAgentResponseAsync(cancellationToken);

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string responseId = Guid.NewGuid().ToString("N");
        foreach (ChatMessage message in this.Messages)
        {
            foreach (AIContent content in message.Contents)
            {
                yield return new AgentResponseUpdate()
                {
                    AgentId = this.Id,
                    AuthorName = this.Name,
                    MessageId = message.MessageId,
                    ResponseId = responseId,
                    Contents = [content],
                    Role = message.Role,
                };
            }
        }
    }

    private static List<ChatMessage>? Validate(List<ChatMessage>? candidateMessages)
    {
        string? currentMessageId = null;

        if (candidateMessages is not null)
        {
            foreach (ChatMessage message in candidateMessages)
            {
                if (currentMessageId is null)
                {
                    currentMessageId = message.MessageId;
                }
                else if (currentMessageId == message.MessageId)
                {
                    throw new ArgumentException("Duplicate consecutive message ids");
                }
            }
        }

        return candidateMessages;
    }

    private sealed class ReplayAgentThread() : InMemoryAgentThread();
}
