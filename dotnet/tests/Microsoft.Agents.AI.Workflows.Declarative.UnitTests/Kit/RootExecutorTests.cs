// Copyright (c) Microsoft. All rights reserved.

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
        public ValueTask InitializeAsync(IWorkflowContext context, params string[] variableNames) =>
            this.InitializeEnvironmentAsync(context, variableNames);

        protected override ValueTask ExecuteAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
            default;
    }
}
