// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Moq;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="RequestExternalInputExecutor"/>.
/// </summary>
public sealed class RequestExternalInputExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    [Fact]
    public void RequestExternalInputNamingConvention()
    {
        // Arrange
        string testId = this.CreateActionId().Value;

        // Act
        string inputStep = RequestExternalInputExecutor.Steps.Input(testId);
        string captureStep = RequestExternalInputExecutor.Steps.Capture(testId);

        // Assert
        Assert.Equal($"{testId}_{nameof(RequestExternalInputExecutor.Steps.Input)}", inputStep);
        Assert.Equal($"{testId}_{nameof(RequestExternalInputExecutor.Steps.Capture)}", captureStep);
    }

    [Fact]
    public async Task RequestExternalInputWithoutVariableAsync()
    {
        // Arrange & Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(RequestExternalInputWithoutVariableAsync),
            variablePath: null);
    }

    [Fact]
    public async Task RequestExternalInputWithVariableAsync()
    {
        // Arrange & Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(RequestExternalInputWithVariableAsync),
            variablePath: "InputVariable");
    }

    [Fact]
    public async Task ExecuteIsNotDiscreteActionAsync()
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(
            nameof(ExecuteIsNotDiscreteActionAsync),
            null);
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        RequestExternalInputExecutor action = new(model, mockProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);

        // Verify IsDiscreteAction is false
        Assert.Equal(
            false,
            action.GetType().BaseType?
                .GetProperty("IsDiscreteAction", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
                .GetValue(action));

        // Verify EmitResultEvent is false
        Assert.Equal(
            false,
            action.GetType().BaseType?
                .GetProperty("EmitResultEvent", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)?
                .GetValue(action));
    }

    [Fact]
    public async Task CaptureResponseWithoutConversationAsync()
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(
            nameof(CaptureResponseWithoutConversationAsync),
            "TestVariable");
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        RequestExternalInputExecutor action = new(model, mockProvider.Object, this.State);

        ChatMessage testMessage = new(ChatRole.User, "Test input");
        ExternalInputResponse response = new(testMessage);

        // Create DeclarativeWorkflowContext with mock base context
        Mock<IWorkflowContext> mockBaseContext = new(MockBehavior.Loose);
        DeclarativeWorkflowContext context = new(mockBaseContext.Object, this.State);

        // Act
        await action.CaptureResponseAsync(context, response, CancellationToken.None);

        // Assert
        // Verify variable was set (should not be blank)
        Assert.IsNotType<Microsoft.PowerFx.Types.BlankValue>(this.State.Get("TestVariable"));
    }

    [Fact]
    public async Task CaptureResponseWithConversationAsync()
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(
            nameof(CaptureResponseWithConversationAsync),
            "TestVariable");
        const string conversationId = "test-conversation-123";

        ChatMessage testMessage = new(ChatRole.User, "Test input");
        ExternalInputResponse response = new(testMessage);

        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        mockProvider
            .Setup(p => p.CreateMessageAsync(conversationId, testMessage, It.IsAny<CancellationToken>()))
            .ReturnsAsync(testMessage);

        RequestExternalInputExecutor action = new(model, mockProvider.Object, this.State);

        // Set up conversation ID in state so GetWorkflowConversation returns it
        this.State.Set(SystemScope.Names.ConversationId, Microsoft.PowerFx.Types.FormulaValue.New(conversationId), VariableScopeNames.System);

        // Create DeclarativeWorkflowContext with mock base context
        Mock<IWorkflowContext> mockBaseContext = new(MockBehavior.Loose);
        DeclarativeWorkflowContext context = new(mockBaseContext.Object, this.State);

        // Act
        await action.CaptureResponseAsync(context, response, CancellationToken.None);

        // Assert
        mockProvider.Verify(
            p => p.CreateMessageAsync(conversationId, testMessage, It.IsAny<CancellationToken>()),
            Times.Once);
        Assert.IsNotType<Microsoft.PowerFx.Types.BlankValue>(this.State.Get("TestVariable"));
    }

    [Fact]
    public async Task CaptureResponseWithMultipleMessagesAsync()
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(
            nameof(CaptureResponseWithMultipleMessagesAsync),
            null);
        const string conversationId = "test-conversation-456";

        ChatMessage[] messages =
        [
            new ChatMessage(ChatRole.User, "First message"),
            new ChatMessage(ChatRole.User, "Second message"),
            new ChatMessage(ChatRole.User, "Third message")
        ];
        ExternalInputResponse response = new(messages);

        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        foreach (ChatMessage message in messages)
        {
            mockProvider
                .Setup(p => p.CreateMessageAsync(conversationId, message, It.IsAny<CancellationToken>()))
                .ReturnsAsync(message);
        }

        RequestExternalInputExecutor action = new(model, mockProvider.Object, this.State);

        // Set up conversation ID in state
        this.State.Set(SystemScope.Names.ConversationId, Microsoft.PowerFx.Types.FormulaValue.New(conversationId), VariableScopeNames.System);

        // Create DeclarativeWorkflowContext with mock base context
        Mock<IWorkflowContext> mockBaseContext = new(MockBehavior.Loose);
        DeclarativeWorkflowContext context = new(mockBaseContext.Object, this.State);

        // Act
        await action.CaptureResponseAsync(context, response, CancellationToken.None);

        // Assert
        mockProvider.Verify(
            p => p.CreateMessageAsync(conversationId, It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()),
            Times.Exactly(3));
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string? variablePath)
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(displayName, variablePath);
        Mock<WorkflowAgentProvider> mockProvider = new(MockBehavior.Strict);
        RequestExternalInputExecutor action = new(model, mockProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    private RequestExternalInput CreateModel(string displayName, string? variablePath)
    {
        RequestExternalInput.Builder actionBuilder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
        };

        if (variablePath != null)
        {
            actionBuilder.Variable = PropertyPath.Create(FormatVariablePath(variablePath));
        }

        return AssignParent<RequestExternalInput>(actionBuilder);
    }
}
