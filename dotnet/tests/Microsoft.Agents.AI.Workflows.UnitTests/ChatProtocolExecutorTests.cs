// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.InProc;
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
        public TurnToken? ReceivedTurnToken { get; private set; }

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

        protected override ValueTask TakeTurnAsync(
            List<ChatMessage> messages,
            IWorkflowContext context,
            TurnToken turnToken,
            CancellationToken cancellationToken = default)
        {
            this.ReceivedTurnToken = turnToken;
            return base.TakeTurnAsync(messages, context, turnToken, cancellationToken);
        }
    }

    [Fact]
    public void ChatProtocolExecutor_DescribedProtocol_IsChatProtocol()
    {
        // Arrange
        TestChatProtocolExecutor executor = new();
        ProtocolDescriptor protocol = executor.DescribeProtocol();

        // Act & Assert
        protocol.Should().Match<ProtocolDescriptor>(protocol => protocol.IsChatProtocol());
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
        executor.ReceivedMessages.Should().HaveCount(2);
        executor.ReceivedMessages[0].Text.Should().Be("Hello");
        executor.ReceivedMessages[1].Text.Should().Be("World");
        executor.TurnCount.Should().Be(1);
    }

    [Fact]
    public async Task ChatProtocolExecutor_ReceivesAndForwardsFullTurnTokenAsync()
    {
        // Arrange
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);
        AgentRunOptions runOptions = new() { AdditionalProperties = new() { ["test-property"] = "test-value" } };
        TurnToken turnToken = new(emitEvents: false, runOptions);

        // Act
        await executor.TakeTurnAsync(turnToken, context);

        // Assert
        executor.ReceivedTurnToken.Should().BeSameAs(turnToken);
        executor.ReceivedTurnToken!.RunOptions.Should().BeSameAs(runOptions);
        context.SentMessages.OfType<TurnToken>().Should().ContainSingle().Which.Should().BeSameAs(turnToken);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ChatProtocolExecutor_CheckpointRecoveryUsesCurrentRunOptionsAsync(bool serializeSession)
    {
        // Arrange
        TestChatProtocolExecutor firstExecutor = new("first-executor");
        TestChatProtocolExecutor secondExecutor = new("second-executor");
        ExecutorBinding firstBinding = firstExecutor.BindExecutor();
        ExecutorBinding secondBinding = secondExecutor.BindExecutor();
        Workflow workflow = new WorkflowBuilder(firstBinding)
            .AddEdge<List<ChatMessage>>(firstBinding, secondBinding, messages => messages is not null)
            .AddEdge<TurnToken>(firstBinding, secondBinding, token => token is not null)
            .WithOutputFrom(secondBinding)
            .Build();
        InProcessExecutionEnvironment environment =
            InProcessExecution.Lockstep.WithCheckpointing(CheckpointManager.CreateInMemory());
        AIAgent workflowAgent = workflow.AsAIAgent(executionEnvironment: environment);
        AgentSession session = await workflowAgent.CreateSessionAsync();
        AgentRunOptions firstRunOptions = new() { AdditionalProperties = new() { ["invocation"] = "first" } };
        AgentRunOptions recoveryRunOptions = new() { AdditionalProperties = new() { ["invocation"] = "recovery" } };

        CheckpointInfo checkpoint = await OrchestrationTestHelpers.RunWorkflowAgentUntilCheckpointAsync(
            workflowAgent,
            session,
            firstRunOptions,
            checkpointNumber: 1);
        if (serializeSession)
        {
            JsonElement serializedSession = await workflowAgent.SerializeSessionAsync(session);
            session = await workflowAgent.DeserializeSessionAsync(serializedSession);
        }

        WorkflowSessionCheckpointRecovery recovery = session.GetService<WorkflowSessionCheckpointRecovery>()
            ?? throw new InvalidOperationException("Workflow checkpoint recovery was not available.");
        recovery.TryPrepare(checkpoint.CheckpointId).Should().BeTrue();

        // Act
        _ = await workflowAgent.RunStreamingAsync([], session, recoveryRunOptions).ToListAsync();

        // Assert
        firstExecutor.ReceivedTurnToken.Should().NotBeNull();
        firstExecutor.ReceivedTurnToken!.RunOptions.Should().BeSameAs(firstRunOptions);
        secondExecutor.ReceivedTurnToken.Should().NotBeNull();
        secondExecutor.ReceivedTurnToken!.RunOptions.Should().BeSameAs(recoveryRunOptions);
    }

    [Fact]
    public void TurnToken_RunOptionsAreNotSerialized()
    {
        // Arrange
        ChatClientAgentRunOptions runOptions = new()
        {
            ChatClientFactory = static chatClient => chatClient,
        };
        TurnToken turnToken = new(emitEvents: false, runOptions);

        // Act
        string json = JsonSerializer.Serialize(turnToken);
        TurnToken? deserialized = JsonSerializer.Deserialize<TurnToken>(json);

        // Assert
        json.Should().NotContain(nameof(TurnToken.RunOptions));
        deserialized.Should().NotBeNull();
        deserialized!.EmitEvents.Should().BeFalse();
        deserialized.RunOptions.Should().BeNull();
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
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        var message = new ChatMessage(ChatRole.User, "Single message");

        // Act - Send as single ChatMessage
        await executor.ExecuteCoreAsync(message, new TypeId(typeof(ChatMessage)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        // Assert
        executor.ReceivedMessages.Should().HaveCount(1);
        executor.ReceivedMessages[0].Text.Should().Be("Single message");
        executor.TurnCount.Should().Be(1);
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

        executor.ReceivedMessages.Should().HaveCount(4);
        executor.ReceivedMessages.Select(m => m.Text).Should().Equal("Message 1", "Message 2", "Message 3", "Message 4");
        executor.TurnCount.Should().Be(1);

        executor.ReceivedMessages.Clear();

        // Second turn should process new messages only
        await executor.ExecuteCoreAsync(new List<ChatMessage>
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
        TestChatProtocolExecutor executor = new(
            options: new ChatProtocolExecutorOptions
            {
                StringMessageChatRole = ChatRole.User
            });
        TestWorkflowContext context = new(executor.Id);

        await executor.ExecuteCoreAsync("String message", new TypeId(typeof(string)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().HaveCount(1);
        executor.ReceivedMessages[0].Role.Should().Be(ChatRole.User);
        executor.ReceivedMessages[0].Text.Should().Be("String message");
    }

    [Fact]
    public async Task ChatProtocolExecutor_EmptyCollection_HandledCorrectlyAsync()
    {
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        await executor.ExecuteCoreAsync(new List<ChatMessage>(), new TypeId(typeof(List<ChatMessage>)), context);
        await executor.ExecuteCoreAsync(Array.Empty<ChatMessage>(), new TypeId(typeof(ChatMessage[])), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().BeEmpty();
        executor.TurnCount.Should().Be(1);
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

        executor.ReceivedMessages.Should().HaveCount(1);
        executor.ReceivedMessages[0].Text.Should().Be("Test message");
    }

    [Fact]
    public async Task ChatProtocolExecutor_MultipleTurns_EachTurnProcessesSeparatelyAsync()
    {
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        await executor.ExecuteCoreAsync(new List<ChatMessage> { new(ChatRole.User, "Turn 1") }, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().HaveCount(1);

        await executor.ExecuteCoreAsync(new ChatMessage(ChatRole.User, "Turn 2"), new TypeId(typeof(ChatMessage)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().HaveCount(2);
        executor.ReceivedMessages[0].Text.Should().Be("Turn 1");
        executor.ReceivedMessages[1].Text.Should().Be("Turn 2");
        executor.TurnCount.Should().Be(2);
    }

    [Fact]
    public async Task ChatProtocolExecutor_InitialWorkflowMessages_RoutedCorrectlyAsync()
    {
        TestChatProtocolExecutor executor = new();
        TestWorkflowContext context = new(executor.Id);

        List<ChatMessage> initialMessages = [new ChatMessage(ChatRole.User, "Kick off the workflow")];

        await executor.ExecuteCoreAsync(initialMessages, new TypeId(typeof(List<ChatMessage>)), context);
        await executor.TakeTurnAsync(new TurnToken(emitEvents: false), context);

        executor.ReceivedMessages.Should().NotBeEmpty();
        executor.ReceivedMessages.Should().HaveCount(1);
        executor.ReceivedMessages[0].Text.Should().Be("Kick off the workflow");
    }
}
