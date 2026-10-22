// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.PowerFx.Types;
using Moq;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Kit;

public sealed class RootExecutorTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RestoreCheckpointAsync_ReloadsFormulaSessionOnEveryLoadAsync(bool offThread)
    {
        // Arrange
        MockAgentProvider provider = new();
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["SETTING"] = "configured" })
            .Build();
        TestRootExecutor executor = new(new(provider.Object)
        {
            Configuration = configuration,
            AllowedEnvironmentVariables = ["SETTING"],
        })
        {
            AssignedValue = "root-value",
            EnvironmentVariables = ["SETTING"],
            SkipBaseCheckpointRestore = true,
        };
        WriteValueExecutor writer = new(executor.Session, skipBaseCheckpointRestore: true) { ChangeConversation = true };
        ReadValueExecutor reader = new(executor.Session) { SkipBaseCheckpointRestore = true };
        Workflow workflow = new WorkflowBuilder(executor).AddEdge(executor, writer).AddEdge(writer, reader).Build();
        CheckpointManager checkpoints = CheckpointManager.CreateInMemory();
        var environment = (offThread ? InProcessExecution.OffThread : InProcessExecution.Lockstep).WithCheckpointing(checkpoints);
        List<CheckpointInfo> savedCheckpoints = [];
        await using (StreamingRun run = await environment.RunStreamingAsync(workflow, "first"))
        {
            await foreach (WorkflowEvent evt in run.WatchStreamAsync())
            {
                if (evt is SuperStepCompletedEvent { CompletionInfo.Checkpoint: { } checkpoint })
                {
                    savedCheckpoints.Add(checkpoint);
                }
            }
        }
        Assert.True(savedCheckpoints.Count >= 3);
        string initialConversation = Assert.Single(provider.ExistingConversationIds);

        await using StreamingRun resumed = await environment.ResumeStreamingAsync(workflow, savedCheckpoints[0]);
        await foreach (WorkflowEvent _ in resumed.WatchStreamAsync())
        {
            // Let the writer replace the checkpointed value before restoring again.
        }
        WorkflowFormulaState state = executor.Session.State;
        Assert.Equal("action-value", reader.Value);
        Assert.Equal(SensitivityLevel.Sensitive, reader.Sensitivity);
        Assert.Equal("action-conversation", Assert.IsType<StringValue>(state.Get(SystemScope.Names.ConversationId, VariableScopeNames.System)).Value);
        state.Set("SETTING", FormulaValue.New("changed"), VariableScopeNames.Environment, SensitivityLevel.None);
        state.Set("LaterValue", FormulaValue.New("later"), VariableScopeNames.Global, SensitivityLevel.Sensitive);
        state.Bind();

        // Act
        await resumed.RestoreCheckpointAsync(savedCheckpoints[0]);

        // Assert
        Assert.Equal("root-value", executor.RestoredValue);
        Assert.Equal("root-value", reader.RestoredValue);
        Assert.Equal("root-value", Assert.IsType<StringValue>(state.Get("TestValue", VariableScopeNames.Local)).Value);
        Assert.Equal(SensitivityLevel.None, state.GetSensitivity("TestValue", VariableScopeNames.Local));
        Assert.Equal("configured", Assert.IsType<StringValue>(state.Get("SETTING", VariableScopeNames.Environment)).Value);
        Assert.Equal(SensitivityLevel.Sensitive, state.GetSensitivity("SETTING", VariableScopeNames.Environment));
        Assert.IsType<BlankValue>(state.Get("LaterValue", VariableScopeNames.Global));
        Assert.Equal(SensitivityLevel.None, state.GetSensitivity("LaterValue", VariableScopeNames.Global));
        Assert.Equal(initialConversation, Assert.IsType<StringValue>(state.Get(SystemScope.Names.ConversationId, VariableScopeNames.System)).Value);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task ResumeAsync_RestoresActionWrittenValuesAsync(bool skipBaseCheckpointRestore, bool reuseWorkflow)
    {
        // Arrange
        DeclarativeWorkflowOptions options = new(new MockAgentProvider().Object);
        TestRootExecutor executor = new(options) { AssignedValue = "root-value", SkipBaseCheckpointRestore = skipBaseCheckpointRestore };
        WriteValueExecutor writer = new(executor.Session, skipBaseCheckpointRestore);
        ReadValueExecutor reader = new(executor.Session) { SkipBaseCheckpointRestore = skipBaseCheckpointRestore };
        Workflow workflow = new WorkflowBuilder(executor).AddEdge(executor, writer).AddEdge(writer, reader).Build();
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
        Assert.True(savedCheckpoints.Count >= 3);
        Assert.Equal("action-value", reader.Value);
        Assert.Equal(SensitivityLevel.Sensitive, reader.Sensitivity);

        if (!reuseWorkflow)
        {
            executor = new(options) { SkipBaseCheckpointRestore = skipBaseCheckpointRestore };
            writer = new(executor.Session, skipBaseCheckpointRestore);
            reader = new(executor.Session) { SkipBaseCheckpointRestore = skipBaseCheckpointRestore };
            workflow = new WorkflowBuilder(executor).AddEdge(executor, writer).AddEdge(writer, reader).Build();
        }
        reader.Value = null;

        // Act
        await using (StreamingRun run = await InProcessExecution.ResumeStreamingAsync(workflow, savedCheckpoints[^2], checkpoints))
        {
            await foreach (WorkflowEvent _ in run.WatchStreamAsync())
            {
                // Consume the resumed run before checking the downstream action.
            }
        }

        // Assert
        Assert.Equal("action-value", executor.RestoredValue);
        Assert.Equal("action-value", reader.RestoredValue);
        Assert.Equal("action-value", reader.Value);
        Assert.Equal(SensitivityLevel.Sensitive, reader.Sensitivity);
    }

    [Theory]
    [InlineData(true, true)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task ResumeAsync_RestoresAllowlistedEnvironmentValuesAsync(bool reuseWorkflow, bool allowEnvironmentOnResume)
    {
        // Arrange
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["SETTING"] = "configured" })
            .Build();
        DeclarativeWorkflowOptions options = new(new MockAgentProvider().Object)
        {
            Configuration = configuration,
            AllowedEnvironmentVariables = ["SETTING"],
        };
        TestRootExecutor executor = new(options) { AssignedValue = "assigned", EnvironmentVariables = ["SETTING"] };
        ReadValueExecutor reader = new(executor.Session) { Expression = "Env.SETTING" };
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
        Assert.Equal("configured", reader.Value);
        Assert.Equal(SensitivityLevel.Sensitive, reader.Sensitivity);

        if (!reuseWorkflow)
        {
            options = new(options.AgentProvider)
            {
                Configuration = configuration,
                AllowedEnvironmentVariables = allowEnvironmentOnResume ? ["SETTING"] : ["OTHER_SETTING"],
            };
            executor = new(options);
            reader = new(executor.Session) { Expression = allowEnvironmentOnResume ? "Env.SETTING" : "Local.TestValue" };
            workflow = new WorkflowBuilder(executor).AddEdge(executor, reader).Build();
        }
        reader.Value = null;

        // Act
        await using (StreamingRun run = await InProcessExecution.ResumeStreamingAsync(workflow, savedCheckpoints[^2], checkpoints))
        {
            await foreach (WorkflowEvent _ in run.WatchStreamAsync())
            {
                // Consume the resumed run to completion before inspecting its state.
            }

            // Assert
            Assert.Equal(allowEnvironmentOnResume ? "configured" : "assigned", reader.Value);
            Assert.Equal(allowEnvironmentOnResume ? SensitivityLevel.Sensitive : SensitivityLevel.None, reader.Sensitivity);
            if (!allowEnvironmentOnResume)
            {
                Assert.IsType<BlankValue>(executor.Session.State.Get("SETTING", VariableScopeNames.Environment));
                Assert.Equal(SensitivityLevel.None, executor.Session.State.GetSensitivity("SETTING", VariableScopeNames.Environment));
            }
        }
    }

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
                // Consume the resumed run to completion before inspecting the result.
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

        public bool SkipBaseCheckpointRestore { get; init; }

        public string? RestoredValue { get; private set; }

        public string[] EnvironmentVariables { get; init; } = [];

        public ValueTask InitializeAsync(IWorkflowContext context, params string[] variableNames) =>
            this.InitializeEnvironmentAsync(context, variableNames);

        protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            if (!this.SkipBaseCheckpointRestore)
            {
                await base.OnCheckpointRestoredAsync(context, cancellationToken);
            }
            this.RestoredValue = this.Session.State.Get("TestValue", VariableScopeNames.Local).ToObject() as string;
        }

        protected override async ValueTask ExecuteAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            await this.InitializeEnvironmentAsync(context, this.EnvironmentVariables);
            if (this.AssignedValue is not null)
            {
                await context.QueueStateUpdateAsync("TestValue", this.AssignedValue, VariableScopeNames.Local, cancellationToken);
            }
        }
    }

    private sealed class WriteValueExecutor(FormulaSession session, bool skipBaseCheckpointRestore) : ActionExecutor("write_value", session)
    {
        public bool ChangeConversation { get; init; }

        protected override ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default) =>
            skipBaseCheckpointRestore ? default : base.OnCheckpointRestoredAsync(context, cancellationToken);

        protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            await context.QueueStateUpdateWithSensitivityAsync(
                "TestValue", new EvaluationResult<string>("action-value", SensitivityLevel.Sensitive), VariableScopeNames.Local, cancellationToken);
            if (this.ChangeConversation)
            {
                await context.QueueConversationUpdateAsync("action-conversation", isExternal: true, cancellationToken);
            }
            return null;
        }
    }

    private sealed class ReadValueExecutor : ActionExecutor
    {
        private readonly FormulaSession _session;

        public ReadValueExecutor(FormulaSession session) : base("read_value", session)
        {
            this._session = session;
        }

        public string? Value { get; set; }

        public bool SkipBaseCheckpointRestore { get; init; }

        public string? RestoredValue { get; private set; }

        public string Expression { get; init; } = "Local.TestValue";

        public SensitivityLevel Sensitivity { get; private set; }

        protected override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            if (!this.SkipBaseCheckpointRestore)
            {
                await base.OnCheckpointRestoredAsync(context, cancellationToken);
            }
            EvaluationResult<string?> result = await new DeclarativeWorkflowContext(context, this._session.State)
                .EvaluateValueWithSensitivityAsync<string>("Local.TestValue", cancellationToken);
            this.RestoredValue = result.Value;
        }

        protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            EvaluationResult<string?> result = await context.EvaluateValueWithSensitivityAsync<string>(this.Expression, cancellationToken);
            this.Value = result.Value;
            this.Sensitivity = result.Sensitivity;
            return this.Value;
        }
    }
}
