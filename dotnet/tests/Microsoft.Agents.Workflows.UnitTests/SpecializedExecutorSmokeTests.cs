// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.UnitTests;

public class SpecializedExecutorSmokeTests
{
    public class TestAIAgent(List<ChatMessage>? messages = null, string? id = null, string? name = null) : AIAgent
    {
        public override string Id => id ?? base.Id;
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
                    CreatedAt = DateTime.Now,
                };
            }

            return result;
        }

        public override AgentThread GetNewThread()
            => new TestAgentThread();

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
            => new TestAgentThread();

        public static TestAIAgent FromStrings(params string[] messages) =>
            new(ToChatMessages(messages));

        public List<ChatMessage> Messages { get; } = Validate(messages) ?? [];

        public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            Task.FromResult(new AgentRunResponse(this.Messages)
            {
                AgentId = this.Id,
                ResponseId = Guid.NewGuid().ToString("N")
            });

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            string responseId = Guid.NewGuid().ToString("N");
            foreach (ChatMessage message in this.Messages)
            {
                foreach (AIContent content in message.Contents)
                {
                    yield return new AgentRunResponseUpdate()
                    {
                        AgentId = this.Id,
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
    }

    public sealed class TestAgentThread() : InMemoryAgentThread();

    internal sealed class TestWorkflowContext : IWorkflowContext
    {
        public List<List<ChatMessage>> Updates { get; } = [];

        public ValueTask AddEventAsync(WorkflowEvent workflowEvent) =>
            default;

        public ValueTask QueueClearScopeAsync(string? scopeName = null) =>
            default;

        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null) =>
            default;

        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null) =>
            throw new NotImplementedException();

        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null) =>
            throw new NotImplementedException();

        public ValueTask SendMessageAsync(object message, string? targetId = null)
        {
            if (message is List<ChatMessage> messages)
            {
                this.Updates.Add(messages);
            }
            else if (message is ChatMessage chatMessage)
            {
                this.Updates.Add([chatMessage]);
            }

            return default;
        }
    }

    [Fact]
    public async Task Test_AIAgentStreamingMessage_AggregationAsync()
    {
        string[] MessageStrings = [
            "",
            "Hello world!",
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "Quisque dignissim ante odio, at facilisis orci porta a. Duis mi augue, fringilla eu egestas a, pellentesque sed lacus."
        ];

        string[][] splits = MessageStrings.Select(t => t.Split()).ToArray();
        foreach (string[] messageSplits in splits)
        {
            for (int i = 0; i < messageSplits.Length - 1; i++)
            {
                messageSplits[i] += ' ';
            }
        }

        List<ChatMessage> expected = TestAIAgent.ToChatMessages(MessageStrings);

        TestAIAgent agent = new(expected);
        AIAgentHostExecutor host = new(agent);

        TestWorkflowContext collectingContext = new();

        await host.TakeTurnAsync(new TurnToken(emitEvents: false), collectingContext);

        // The first empty message is skipped.
        collectingContext.Updates.Should().HaveCount(MessageStrings.Length - 1);

        for (int i = 1; i < MessageStrings.Length; i++)
        {
            string expectedText = MessageStrings[i];
            string[] expectedSplits = splits[i];

            ChatMessage equivalent = expected[i];
            List<ChatMessage> collected = collectingContext.Updates[i - 1];

            collected.Should().HaveCount(1);
            collected[0].Text.Should().Be(expectedText);
            collected[0].Contents.Should().HaveCount(splits[i].Length);

            Action<AIContent>[] splitCheckActions = splits[i].Select(MakeSplitCheckAction).ToArray();
            Assert.Collection(collected[0].Contents, splitCheckActions);
        }

        Action<AIContent> MakeSplitCheckAction(string splitString)
        {
            return Check;

            void Check(AIContent content)
            {
                TextContent? text = content as TextContent;
                text!.Text.Should().Be(splitString);
            }
        }
    }
}
