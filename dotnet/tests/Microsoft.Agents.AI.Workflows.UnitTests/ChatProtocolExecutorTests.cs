// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
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
    public void ChatProtocolExecutor_DescribedProtocol_IsChatProtocol()
    {
        // Arrange
        TestChatProtocolExecutor executor = new();
        ProtocolDescriptor protocol = executor.DescribeProtocol();

        // Act & Assert
        Assert.True(protocol.IsChatProtocol());
    }

    [Fact]
    public async Task ChatProtocolExecutor_Handles_ListOfChatMessagesAsync()
    {
        // Arrange
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.User, "World")
        ];

        // Act - Send List<ChatMessage> via ExecuteAsync
        await executor.ExecuteCoreAsync(messages, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        // Assert
        Assert.Equal(2, executor.ReceivedMessages.Count);
        Assert.Equal("Hello", executor.ReceivedMessages[0].Text);
        Assert.Equal("World", executor.ReceivedMessages[1].Text);
        Assert.Equal(1, executor.TurnCount);
    }

    [Fact]
    public async Task ChatProtocolExecutor_Handles_ArrayOfChatMessagesAsync()
    {
        // Arrange
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        ChatMessage[] messages =
        [
            new ChatMessage(ChatRole.System, "System message"),
            new ChatMessage(ChatRole.User, "User query"),
            new ChatMessage(ChatRole.Assistant, "Agent reply")
        ];

        // Act - Send as ChatMessage[]
        await executor.ExecuteCoreAsync(messages, new TypeId(typeof(ChatMessage[])), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        // Assert
        Assert.Equal(3, executor.ReceivedMessages.Count);
        Assert.Equal(ChatRole.System, executor.ReceivedMessages[0].Role);
        Assert.Equal(ChatRole.User, executor.ReceivedMessages[1].Role);
        Assert.Equal(ChatRole.Assistant, executor.ReceivedMessages[2].Role);
        Assert.Equal(1, executor.TurnCount);
    }

    [Fact]
    public async Task ChatProtocolExecutor_Handles_SingleChatMessageAsync()
    {
        // Arrange
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        var message = new ChatMessage(ChatRole.User, "Single message");

        // Act - Send as single ChatMessage
        await executor.ExecuteCoreAsync(message, new TypeId(typeof(ChatMessage)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        // Assert
        Assert.Single(executor.ReceivedMessages);
        Assert.Equal("Single message", executor.ReceivedMessages[0].Text);
        Assert.Equal(1, executor.TurnCount);
    }

    [Fact]
    public async Task ChatProtocolExecutor_AccumulatesAndClearsMessagesPerTurnAsync()
    {
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        // Send multiple message batches before taking a turn
        await executor.ExecuteCoreAsync(new ChatMessage(ChatRole.User, "Message 1"), new TypeId(typeof(ChatMessage)), context);
        await executor.ExecuteCoreAsync(new List<ChatMessage>
        {
            new(ChatRole.User, "Message 2"),
            new(ChatRole.User, "Message 3")
        }, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.ExecuteCoreAsync(new ChatMessage[] { new(ChatRole.User, "Message 4") }, new TypeId(typeof(ChatMessage[])), context);

        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        Assert.Equal(4, executor.ReceivedMessages.Count);
        Assert.Equal(["Message 1", "Message 2", "Message 3", "Message 4"], executor.ReceivedMessages.Select(m => m.Text));
        Assert.Equal(1, executor.TurnCount);

        executor.ReceivedMessages.Clear();

        // Second turn should process new messages only
        await executor.ExecuteCoreAsync(new List<ChatMessage>
        {
            new(ChatRole.User, "Second batch")
        }, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        Assert.Single(executor.ReceivedMessages);
        Assert.Equal("Second batch", executor.ReceivedMessages[0].Text);
        Assert.Equal(2, executor.TurnCount);
    }

    [Fact]
    public async Task ChatProtocolExecutor_WithStringRole_ConvertsStringToMessageAsync()
    {
        TestChatProtocolExecutor executor = new(
            options: new ChatProtocolExecutorOptions
            {
                StringMessageChatRole = ChatRole.User
            });
        TestWorkflowContext context = new(executor.Id);

        await executor.ExecuteCoreAsync("String message", new TypeId(typeof(string)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        Assert.Single(executor.ReceivedMessages);
        Assert.Equal(ChatRole.User, executor.ReceivedMessages[0].Role);
        Assert.Equal("String message", executor.ReceivedMessages[0].Text);
    }

    [Fact]
    public async Task ChatProtocolExecutor_EmptyCollection_HandledCorrectlyAsync()
    {
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        await executor.ExecuteCoreAsync(new List<ChatMessage>(), new TypeId(typeof(List<ChatMessage>)), context);
        await executor.ExecuteCoreAsync(Array.Empty<ChatMessage>(), new TypeId(typeof(ChatMessage[])), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        Assert.Empty(executor.ReceivedMessages);
        Assert.Equal(1, executor.TurnCount);
    }

    [Theory]
    [InlineData(typeof(List<ChatMessage>))]
    [InlineData(typeof(ChatMessage[]))]
    public async Task ChatProtocolExecutor_RoutesCollectionTypesAsync(Type collectionType)
    {
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        var sourceMessages = new[] { new ChatMessage(ChatRole.User, "Test message") };
        object messagesToSend = collectionType == typeof(List<ChatMessage>) ? sourceMessages.ToList() : sourceMessages;

        await executor.ExecuteCoreAsync(messagesToSend, new TypeId(collectionType), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        Assert.Single(executor.ReceivedMessages);
        Assert.Equal("Test message", executor.ReceivedMessages[0].Text);
    }

    [Fact]
    public async Task ChatProtocolExecutor_MultipleTurns_EachTurnProcessesSeparatelyAsync()
    {
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        await executor.ExecuteCoreAsync(new List<ChatMessage> { new(ChatRole.User, "Turn 1") }, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        Assert.Single(executor.ReceivedMessages);

        await executor.ExecuteCoreAsync(new ChatMessage(ChatRole.User, "Turn 2"), new TypeId(typeof(ChatMessage)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        Assert.Equal(2, executor.ReceivedMessages.Count);
        Assert.Equal("Turn 1", executor.ReceivedMessages[0].Text);
        Assert.Equal("Turn 2", executor.ReceivedMessages[1].Text);
        Assert.Equal(2, executor.TurnCount);
    }

    [Fact]
    public async Task ChatProtocolExecutor_InitialWorkflowMessages_RoutedCorrectlyAsync()
    {
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        List<ChatMessage> initialMessages = [new ChatMessage(ChatRole.User, "Kick off the workflow")];

        await executor.ExecuteCoreAsync(initialMessages, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        Assert.NotEmpty(executor.ReceivedMessages);
        Assert.Single(executor.ReceivedMessages);
        Assert.Equal("Kick off the workflow", executor.ReceivedMessages[0].Text);
    }
}
