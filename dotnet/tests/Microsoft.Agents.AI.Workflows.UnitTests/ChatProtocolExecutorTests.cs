// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests for <see cref="ChatProtocolExecutor"/> to verify message routing behavior.
/// </summary>
public class ChatProtocolExecutorTests
{
    private sealed class TestChatProtocolExecutor : ChatProtocolExecutor
    {
        public List<ChatMessage> ReceivedMessages { get; } = [];
        public int TurnCount { get; private set; }

        public TestChatProtocolExecutor(string id = "test-executor", ChatProtocolExecutorOptions? options = null)
            : base(id, options)
        {
        }

        protected override async ValueTask TakeTurnAsync(
            List<ChatMessage> messages,
            IWorkflowContext context,
            bool? emitEvents,
            CancellationToken cancellationToken = default)
        {
            this.ReceivedMessages.AddRange(messages);
            this.TurnCount++;

            // Send messages back to context so they can be collected
            await context.SendMessageAsync(messages, cancellationToken: cancellationToken);
        }
    }

    [Fact]
    public async Task ChatProtocolExecutor_Handles_ListOfChatMessagesAsync()
    {
        // Arrange
        var executor = new TestChatProtocolExecutor();
        var context = new TestWorkflowContext(executor.Id);

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.User, "World")
        ];

        // Act - Send List<ChatMessage> via ExecuteAsync
        await executor.ExecuteAsync(messages, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        // Assert
        executor.ReceivedMessages.Should().HaveCount(2);
        executor.ReceivedMessages[0].Text.Should().Be("Hello");
        executor.ReceivedMessages[1].Text.Should().Be("World");
        executor.TurnCount.Should().Be(1);
    }

    [Fact]
    public async Task ChatProtocolExecutor_Handles_ArrayOfChatMessagesAsync()
    {
        // Arrange
        var executor = new TestChatProtocolExecutor();
        var context = new TestWorkflowContext(executor.Id);

        ChatMessage[] messages =
        [
            new ChatMessage(ChatRole.System, "System message"),
            new ChatMessage(ChatRole.User, "User query"),
            new ChatMessage(ChatRole.Assistant, "Agent reply")
        ];

        // Act - Send as ChatMessage[]
        await executor.ExecuteAsync(messages, new TypeId(typeof(ChatMessage[])), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        // Assert
        executor.ReceivedMessages.Should().HaveCount(3);
        executor.ReceivedMessages[0].Role.Should().Be(ChatRole.System);
        executor.ReceivedMessages[1].Role.Should().Be(ChatRole.User);
        executor.ReceivedMessages[2].Role.Should().Be(ChatRole.Assistant);
        executor.TurnCount.Should().Be(1);
    }

    [Fact]
    public async Task ChatProtocolExecutor_Handles_SingleChatMessageAsync()
    {
        // Arrange
        var executor = new TestChatProtocolExecutor();
        var context = new TestWorkflowContext(executor.Id);

        var message = new ChatMessage(ChatRole.User, "Single message");

        // Act - Send as single ChatMessage
        await executor.ExecuteAsync(message, new TypeId(typeof(ChatMessage)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        // Assert
        executor.ReceivedMessages.Should().HaveCount(1);
        executor.ReceivedMessages[0].Text.Should().Be("Single message");
        executor.TurnCount.Should().Be(1);
    }

    [Fact]
    public async Task ChatProtocolExecutor_AccumulatesAndClearsMessagesPerTurnAsync()
    {
        var executor = new TestChatProtocolExecutor();
        var context = new TestWorkflowContext(executor.Id);

        // Send multiple message batches before taking a turn
        await executor.ExecuteAsync(new ChatMessage(ChatRole.User, "Message 1"), new TypeId(typeof(ChatMessage)), context);
        await executor.ExecuteAsync(new List<ChatMessage>
        {
            new(ChatRole.User, "Message 2"),
            new(ChatRole.User, "Message 3")
        }, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.ExecuteAsync(new ChatMessage[] { new(ChatRole.User, "Message 4") }, new TypeId(typeof(ChatMessage[])), context);

        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().HaveCount(4);
        executor.ReceivedMessages.Select(m => m.Text).Should().Equal("Message 1", "Message 2", "Message 3", "Message 4");
        executor.TurnCount.Should().Be(1);

        executor.ReceivedMessages.Clear();

        // Second turn should process new messages only
        await executor.ExecuteAsync(new List<ChatMessage>
        {
            new(ChatRole.User, "Second batch")
        }, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().HaveCount(1);
        executor.ReceivedMessages[0].Text.Should().Be("Second batch");
        executor.TurnCount.Should().Be(2);
    }

    [Fact]
    public async Task ChatProtocolExecutor_WithStringRole_ConvertsStringToMessageAsync()
    {
        var executor = new TestChatProtocolExecutor(
            options: new ChatProtocolExecutorOptions
            {
                StringMessageChatRole = ChatRole.User
            });
        var context = new TestWorkflowContext(executor.Id);

        await executor.ExecuteAsync("String message", new TypeId(typeof(string)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().HaveCount(1);
        executor.ReceivedMessages[0].Role.Should().Be(ChatRole.User);
        executor.ReceivedMessages[0].Text.Should().Be("String message");
    }

    [Fact]
    public async Task ChatProtocolExecutor_EmptyCollection_HandledCorrectlyAsync()
    {
        var executor = new TestChatProtocolExecutor();
        var context = new TestWorkflowContext(executor.Id);

        await executor.ExecuteAsync(new List<ChatMessage>(), new TypeId(typeof(List<ChatMessage>)), context);
        await executor.ExecuteAsync(Array.Empty<ChatMessage>(), new TypeId(typeof(ChatMessage[])), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().BeEmpty();
        executor.TurnCount.Should().Be(1);
    }

    [Theory]
    [InlineData(typeof(List<ChatMessage>))]
    [InlineData(typeof(ChatMessage[]))]
    public async Task ChatProtocolExecutor_RoutesCollectionTypesAsync(Type collectionType)
    {
        var executor = new TestChatProtocolExecutor();
        var context = new TestWorkflowContext(executor.Id);

        var sourceMessages = new[] { new ChatMessage(ChatRole.User, "Test message") };
        object messagesToSend = collectionType == typeof(List<ChatMessage>) ? sourceMessages.ToList() : sourceMessages;

        await executor.ExecuteAsync(messagesToSend, new TypeId(collectionType), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().HaveCount(1);
        executor.ReceivedMessages[0].Text.Should().Be("Test message");
    }

    [Fact]
    public async Task ChatProtocolExecutor_MultipleTurns_EachTurnProcessesSeparatelyAsync()
    {
        var executor = new TestChatProtocolExecutor();
        var context = new TestWorkflowContext(executor.Id);

        await executor.ExecuteAsync(new List<ChatMessage> { new(ChatRole.User, "Turn 1") }, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().HaveCount(1);

        await executor.ExecuteAsync(new ChatMessage(ChatRole.User, "Turn 2"), new TypeId(typeof(ChatMessage)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().HaveCount(2);
        executor.ReceivedMessages[0].Text.Should().Be("Turn 1");
        executor.ReceivedMessages[1].Text.Should().Be("Turn 2");
        executor.TurnCount.Should().Be(2);
    }

    [Fact]
    public async Task ChatProtocolExecutor_InitialWorkflowMessages_RoutedCorrectlyAsync()
    {
        var executor = new TestChatProtocolExecutor();
        var context = new TestWorkflowContext(executor.Id);

        List<ChatMessage> initialMessages = [new ChatMessage(ChatRole.User, "Kick off the workflow")];

        await executor.ExecuteAsync(initialMessages, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().NotBeEmpty();
        executor.ReceivedMessages.Should().HaveCount(1);
        executor.ReceivedMessages[0].Text.Should().Be("Kick off the workflow");
    }
}
