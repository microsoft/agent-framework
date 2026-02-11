// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Moq;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="RequestExternalInputExecutor"/>.
/// </summary>
public sealed class RequestExternalInputExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public async Task ExecuteRequestsExternalInputAsync()
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(nameof(ExecuteRequestsExternalInputAsync), "TestVariable");

        MockAgentProvider mockAgentProvider = new();
        RequestExternalInputExecutor action = new(model, mockAgentProvider.Object, this.State);

        this.State.Bind();

        TestWorkflowExecutor workflowExecutor = new();
        WorkflowBuilder workflowBuilder = new(workflowExecutor);
        workflowBuilder.AddEdge(workflowExecutor, action);

        // Act
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflowBuilder.Build(), this.State);
        WorkflowEvent[] events = await run.WatchStreamAsync().ToArrayAsync();

        // Assert
        VerifyModel(model, action);
        // RequestExternalInputExecutor has IsDiscreteAction = false, so no completion event is raised
        Assert.Contains(events, e => e is DeclarativeActionInvokedEvent);
        // Verify no executor failures occurred
        Assert.DoesNotContain(events, e => e is ExecutorFailedEvent);
    }

    [Fact]
    public async Task CaptureResponseWithSingleMessageAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CaptureResponseWithSingleMessageAsync),
            variableName: "TestVariable",
            messageCount: 1);
    }

    [Fact]
    public async Task CaptureResponseWithMultipleMessagesAsync()
    {
        // Arrange, Act, Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CaptureResponseWithMultipleMessagesAsync),
            variableName: "TestVariable",
            messageCount: 3);
    }

    [Fact]
    public async Task CaptureResponseWithWorkflowConversationAsync()
    {
        // Arrange
        const string conversationId = "WorkflowConversationId";
        this.State.Set(SystemScope.Names.ConversationId, FormulaValue.New(conversationId), VariableScopeNames.System);

        // Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(CaptureResponseWithWorkflowConversationAsync),
            variableName: "TestVariable",
            messageCount: 2,
            expectMessagesCreated: true);
    }

    [Fact]
    public void StepsInputReturnsCorrectId()
    {
        // Arrange
        const string actionId = "test_action_123";

        // Act
        string result = RequestExternalInputExecutor.Steps.Input(actionId);

        // Assert
        Assert.Equal("test_action_123_Input", result);
    }

    [Fact]
    public void StepsCaptureReturnsCorrectId()
    {
        // Arrange
        const string actionId = "test_action_456";

        // Act
        string result = RequestExternalInputExecutor.Steps.Capture(actionId);

        // Assert
        Assert.Equal("test_action_456_Capture", result);
    }

    [Fact]
    public void IsDiscreteActionReturnsFalse()
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(nameof(IsDiscreteActionReturnsFalse), "TestVariable");
        MockAgentProvider mockAgentProvider = new();
        RequestExternalInputExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        bool isDiscrete = action.GetType()
            .BaseType?
            .GetProperty("IsDiscreteAction", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
            .GetValue(action) as bool? ?? true;

        // Assert
        Assert.False(isDiscrete);
    }

    [Fact]
    public void EmitResultEventReturnsFalse()
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(nameof(EmitResultEventReturnsFalse), "TestVariable");
        MockAgentProvider mockAgentProvider = new();
        RequestExternalInputExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        bool emitResult = action.GetType()
            .BaseType?
            .GetProperty("EmitResultEvent", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
            .GetValue(action) as bool? ?? true;

        // Assert
        Assert.False(emitResult);
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName,
        int messageCount,
        bool expectMessagesCreated = false)
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(this.FormatDisplayName(displayName), FormatVariablePath(variableName));
        MockAgentProvider mockAgentProvider = new();
        RequestExternalInputExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Create test messages
        List<ChatMessage> testMessages = [];
        for (int i = 0; i < messageCount; i++)
        {
            testMessages.Add(new ChatMessage(ChatRole.User, $"Test message {i + 1}"));
        }

        ExternalInputResponse response = new(testMessages);

        // Create a mock IWorkflowContext and wrap it with DeclarativeWorkflowContext
        Mock<IWorkflowContext> mockBaseContext = new();

        // Setup mock base context
        mockBaseContext.Setup(c => c.QueueStateUpdateAsync(
            It.IsAny<string>(),
            It.IsAny<object>(),
            It.IsAny<string>(),
            It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));

        DeclarativeWorkflowContext declarativeContext = new(mockBaseContext.Object, this.State);

        // Act
        await action.CaptureResponseAsync(declarativeContext, response, CancellationToken.None);

        // Assert
        VerifyModel(model, action);

        // Verify messages were created in the workflow conversation if expected
        if (expectMessagesCreated)
        {
            mockAgentProvider.Verify(p => p.CreateMessageAsync(
                It.IsAny<string>(),
                It.IsAny<ChatMessage>(),
                It.IsAny<CancellationToken>()), Times.Exactly(messageCount));
        }

        // Verify the variable was set correctly
        this.VerifyState(variableName, testMessages.ToTable());

        // Verify SetLastMessageAsync was called (it makes 3 calls: LastMessage, LastMessageId, LastMessageText)
        mockBaseContext.Verify(c => c.QueueStateUpdateAsync(
            SystemScope.Names.LastMessage,
            It.IsAny<object>(),
            VariableScopeNames.System,
            It.IsAny<CancellationToken>()), Times.Once);

        mockBaseContext.Verify(c => c.QueueStateUpdateAsync(
            SystemScope.Names.LastMessageText,
            It.IsAny<object>(),
            VariableScopeNames.System,
            It.IsAny<CancellationToken>()), Times.Once);
    }

    private RequestExternalInput CreateModel(string displayName, string variablePath)
    {
        RequestExternalInput.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = PropertyPath.Create(variablePath),
            };

        return AssignParent<RequestExternalInput>(actionBuilder);
    }
}
