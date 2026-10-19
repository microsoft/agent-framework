// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.PowerFx.Types;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Kit;

public sealed class RootExecutorTests
{
    [Fact]
    public async Task HandleAsync_RetryAfterStateWriteFailureReusesCreatedConversationAsync()
    {
        // Arrange
        MockAgentProvider provider = new();
        TestRootExecutor executor = new(new(provider.Object));
        Mock<IWorkflowContext> context = new();
        context.SetupSequence(c => c.QueueStateUpdateAsync(
                SystemScope.Names.Conversation, It.IsAny<object>(), VariableScopeNames.System, It.IsAny<CancellationToken>()))
            .Throws(new InvalidOperationException("State write failed."))
            .Returns(default(ValueTask));

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await executor.HandleAsync("first", context.Object, CancellationToken.None));
        await executor.HandleAsync("first", context.Object, CancellationToken.None);

        // Assert
        string conversationId = Assert.Single(provider.ExistingConversationIds);
        provider.Verify(p => p.CreateMessageAsync(conversationId, It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()), Times.Once);

        // Act
        await executor.ResetAsync();
        await executor.HandleAsync("second", new Mock<IWorkflowContext>().Object, CancellationToken.None);

        // Assert
        Assert.Equal(2, provider.ExistingConversationIds.Count);
        Assert.NotEqual(conversationId, provider.ExistingConversationIds[1]);
    }

    [Fact]
    public async Task ResumeAsync_RestoresFormulaValuesAfterDisposalAsync()
    {
        // Arrange
        TestRootExecutor executor = new(new(new MockAgentProvider().Object)) { AssignedValue = "assigned" };
        ReadValueExecutor reader = new(executor.Session);
        Workflow workflow = new WorkflowBuilder(executor).AddEdge(executor, reader).Build();
        CheckpointManager checkpoints = CheckpointManager.CreateInMemory();
        List<CheckpointInfo> savedCheckpoints = [];
        await using (StreamingRun run = await InProcessExecution.RunStreamingAsync(workflow, "first", checkpoints))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } checkpoint })
                {
                    savedCheckpoints.Add(checkpoint);
                }
            }
        }
        Assert.True(savedCheckpoints.Count >= 2);
        Assert.Equal("assigned", reader.Value);
        reader.Value = null;

        // Act
        await using (StreamingRun run = await InProcessExecution.ResumeStreamingAsync(workflow, savedCheckpoints[^2], checkpoints))
        {
            await foreach (WorkflowEvent _ in run.WatchStreamAsync())
            {
            }
        }

        // Assert
        Assert.Equal("assigned", reader.Value);
    }

    [Fact]
    public async Task ResetAsync_RestoresNestedConversationIdAsync()
    {
        // Arrange
        TestRootExecutor executor = new(new(new MockAgentProvider().Object));
        await executor.HandleAsync("first", new Mock<IWorkflowContext>().Object, CancellationToken.None);
        RecordValue activeConversation = Assert.IsAssignableFrom<RecordValue>(
            executor.Session.State.Get(SystemScope.Names.Conversation, VariableScopeNames.System));
        Assert.IsType<StringValue>(activeConversation.GetField("Id"));

        // Act
        await executor.ResetAsync();

        // Assert
        RecordValue initialConversation = Assert.IsAssignableFrom<RecordValue>(
            executor.Session.State.Get(SystemScope.Names.Conversation, VariableScopeNames.System));
        Assert.IsType<BlankValue>(initialConversation.GetField("Id"));
        Assert.IsType<BlankValue>(executor.Session.State.Get(SystemScope.Names.ConversationId, VariableScopeNames.System));
    }

    [Fact]
    public async Task HandleAsync_WithoutResetReusesConversationAsync()
    {
        // Arrange
        MockAgentProvider provider = new();
        TestRootExecutor executor = new(new(provider.Object));
        IWorkflowContext context = new Mock<IWorkflowContext>().Object;

        // Act
        await executor.HandleAsync("first", context, CancellationToken.None);
        await executor.HandleAsync("second", context, CancellationToken.None);

        // Assert
        string conversationId = Assert.Single(provider.ExistingConversationIds);
        provider.Verify(p => p.CreateMessageAsync(conversationId, It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()), Times.Exactly(2));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("configured-conversation")]
    public async Task HandleAsync_ReusedWorkflowResolvesConversationPerRunAsync(string? conversationId)
    {
        // Arrange
        MockAgentProvider provider = new();
        List<string> messageConversations = [];
        provider.Setup(p => p.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()))
            .Returns<string, ChatMessage, CancellationToken>((id, message, _) =>
            {
                messageConversations.Add(id);
                return Task.FromResult(message);
            });
        TestRootExecutor executor = new(new(provider.Object) { ConversationId = conversationId });
        Workflow workflow = new WorkflowBuilder(executor).Build();

        // Act
        await using (Run firstRun = await InProcessExecution.RunAsync(workflow, "first", sessionId: "first-session"))
        {
        }
        await using (Run secondRun = await InProcessExecution.RunAsync(workflow, "second", sessionId: "second-session"))
        {
        }

        // Assert
        Assert.Equal(2, messageConversations.Count);
        if (conversationId is null)
        {
            Assert.NotEqual(messageConversations[0], messageConversations[1]);
            provider.Verify(p => p.CreateConversationAsync(It.IsAny<CancellationToken>()), Times.Exactly(2));
        }
        else
        {
            Assert.All(messageConversations, id => Assert.Equal(conversationId, id));
            provider.Verify(p => p.CreateConversationAsync(It.IsAny<CancellationToken>()), Times.Never);
        }
    }

    [Theory]
    [InlineData(VariableScopeNames.Local)]
    [InlineData(VariableScopeNames.Global)]
    [InlineData(VariableScopeNames.Environment)]
    [InlineData(VariableScopeNames.System)]
    public async Task ResetAsync_RestoresInitialFormulaStateAsync(string scopeName)
    {
        // Arrange
        TestRootExecutor executor = new(new(new MockAgentProvider().Object));
        WorkflowFormulaState state = executor.Session.State;
        FormulaValue initialMessage = state.Get(SystemScope.Names.LastMessage, VariableScopeNames.System);
        state.Set("RunValue", FormulaValue.New("value"), scopeName, SensitivityLevel.Sensitive);
        state.Set(SystemScope.Names.LastMessage, FormulaValue.New("changed"), VariableScopeNames.System);
        state.SetInitialized();

        // Act
        await executor.ResetAsync();

        // Assert
        Assert.IsType<BlankValue>(state.Get("RunValue", scopeName));
        Assert.Equal(SensitivityLevel.None, state.GetSensitivity("RunValue", scopeName));
        Assert.Equal(initialMessage.ToObject(), state.Get(SystemScope.Names.LastMessage, VariableScopeNames.System).ToObject());
        Assert.True(state.SetInitialized());
    }

    [Fact]
    public async Task InitializeEnvironmentAsync_OnlyQueuesAllowedVariablesAsync()
    {
        // Arrange
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ALLOWED"] = "allowed-value",
                ["HIDDEN"] = "hidden-value",
            })
            .Build();
        DeclarativeWorkflowOptions options =
            new(new MockAgentProvider().Object)
            {
                Configuration = configuration,
                AllowedEnvironmentVariables = ["ALLOWED"],
            };
        TestRootExecutor executor = new(options);
        Mock<IWorkflowContext> sourceContext = new(MockBehavior.Strict);
        sourceContext.Setup(c => c.QueueStateUpdateAsync("ALLOWED", It.IsAny<object?>(), VariableScopeNames.Environment, It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        sourceContext.Setup(c => c.QueueStateUpdateAsync("ALLOWED", SensitivityLevel.Sensitive, WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Environment), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));

        DeclarativeWorkflowContext context = new(sourceContext.Object, executor.Session.State);

        // Act
        await executor.InitializeAsync(context, "ALLOWED", "HIDDEN");

        // Assert
        sourceContext.Verify(c => c.QueueStateUpdateAsync("ALLOWED", It.IsAny<object?>(), VariableScopeNames.Environment, It.IsAny<CancellationToken>()), Times.Once);
        sourceContext.Verify(c => c.QueueStateUpdateAsync("ALLOWED", SensitivityLevel.Sensitive, WorkflowFormulaState.GetSensitivityScopeName(VariableScopeNames.Environment), It.IsAny<CancellationToken>()), Times.Once);
        sourceContext.Verify(c => c.QueueStateUpdateAsync("HIDDEN", It.IsAny<object?>(), VariableScopeNames.Environment, It.IsAny<CancellationToken>()), Times.Never);
    }

    private sealed class TestRootExecutor(DeclarativeWorkflowOptions options) : RootExecutor<string>("test_root", options, inputTransform: null)
    {
        public string? AssignedValue { get; init; }

        public ValueTask InitializeAsync(IWorkflowContext context, params string[] variableNames) =>
            this.InitializeEnvironmentAsync(context, variableNames);

        protected override ValueTask ExecuteAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
            this.AssignedValue is null
                ? default
                : context.QueueStateUpdateAsync("TestValue", this.AssignedValue, VariableScopeNames.Local, cancellationToken);
    }

    private sealed class ReadValueExecutor(FormulaSession session) : ActionExecutor("read_value", session)
    {
        public string? Value { get; set; }

        protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            this.Value = await context.EvaluateValueAsync<string>("Local.TestValue", cancellationToken);
            return this.Value;
        }
    }
}
