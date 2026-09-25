// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Moq;

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
    public async Task ExecuteRequestsExternalInputAsync()
    {
        // Arrange, Act & Assert
        await this.ExecuteTestAsync(
            displayName: nameof(ExecuteRequestsExternalInputAsync),
            variableName: "TestVariable");
    }

    [Fact]
    public async Task CaptureResponseWithVariableAsync()
    {
        // Arrange, Act & Assert
        await this.CaptureResponseTestAsync(
            displayName: nameof(CaptureResponseWithVariableAsync),
            variableName: "TestVariable");
    }

    [Fact]
    public async Task CaptureResponseWithoutVariableAsync()
    {
        // Arrange, Act & Assert
        await this.CaptureResponseTestAsync(
            displayName: nameof(CaptureResponseWithoutVariableAsync),
            variableName: null);
    }

    [Fact]
    public async Task CaptureResponseWithMultipleMessagesAsync()
    {
        // Arrange, Act & Assert
        await this.CaptureResponseTestAsync(
            displayName: nameof(CaptureResponseWithMultipleMessagesAsync),
            variableName: "TestVariable",
            messageCount: 3);
    }

    [Fact]
    public async Task CaptureResponseWithWorkflowConversationAsync()
    {
        // Arrange
        this.State.Set(SystemScope.Names.ConversationId, FormulaValue.New("WorkflowConversationId"), VariableScopeNames.System);

        // Act & Assert
        await this.CaptureResponseTestAsync(
            displayName: nameof(CaptureResponseWithWorkflowConversationAsync),
            variableName: "TestVariable",
            messageCount: 2,
            expectMessagesCreated: true);
    }

    [Fact]
    public async Task CaptureResponseUsesCanonicalMessagesWithWorkflowConversationAsync()
    {
        // Arrange
        const string VariableName = "TestVariable";
        this.State.Set(SystemScope.Names.ConversationId, FormulaValue.New("WorkflowConversationId"), VariableScopeNames.System);

        RequestExternalInput model = this.CreateModel(nameof(CaptureResponseUsesCanonicalMessagesWithWorkflowConversationAsync), VariableName);
        MockAgentProvider mockAgentProvider = new();
        RequestExternalInputExecutor action = new(model, mockAgentProvider.Object, this.State);

        ChatMessage[] inputMessages =
        [
            new(ChatRole.User, [new TextContent("First message"), new HostedFileContent("caller-file-1")]) { MessageId = "caller-message-1" },
            new(ChatRole.User, [new TextContent("Second message"), new HostedFileContent("caller-file-2")]) { MessageId = "caller-message-2" },
        ];
        ChatMessage[] canonicalMessages =
        [
            new(ChatRole.User, [new TextContent("Canonical first"), new HostedFileContent("provider-file-1")]) { MessageId = "provider-message-1" },
            new(ChatRole.User, [new TextContent("Canonical second"), new HostedFileContent("provider-file-2")]) { MessageId = "provider-message-2" },
        ];
        int canonicalMessageIndex = 0;
        mockAgentProvider
            .Setup(p => p.CreateMessageAsync("WorkflowConversationId", It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()))
            .Returns(() => Task.FromResult(canonicalMessages[canonicalMessageIndex++]));

        ExternalInputResponse response = new(inputMessages);

        // Act
        WorkflowEvent[] events =
            await this.ExecuteAsync(
                RequestExternalInputExecutor.Steps.Capture(action.Id),
                (context, message, cancellationToken) => action.CaptureResponseAsync(context, response, cancellationToken));

        // Assert
        VerifyCompletionEvent(events);
        ChatMessage[] expectedMessages =
        [
            new(ChatRole.User, [new TextContent("First message"), new HostedFileContent("provider-file-1")]) { MessageId = "provider-message-1" },
            new(ChatRole.User, [new TextContent("Second message"), new HostedFileContent("provider-file-2")]) { MessageId = "provider-message-2" },
        ];
        this.VerifyState(VariableName, expectedMessages.ToTable());
        this.VerifyState(SystemScope.Names.LastMessage, VariableScopeNames.System, expectedMessages[1].ToRecord());
        this.VerifyState(SystemScope.Names.LastMessageId, VariableScopeNames.System, FormulaValue.New("provider-message-2"));
        this.VerifyState(SystemScope.Names.LastMessageText, VariableScopeNames.System, FormulaValue.New("Second message"));
    }

    [Fact]
    public async Task CaptureResponseUsesCallerMessagesWithoutWorkflowConversationAsync()
    {
        // Arrange
        const string VariableName = "TestVariable";
        RequestExternalInput model = this.CreateModel(nameof(CaptureResponseUsesCallerMessagesWithoutWorkflowConversationAsync), VariableName);
        MockAgentProvider mockAgentProvider = new();
        RequestExternalInputExecutor action = new(model, mockAgentProvider.Object, this.State);
        ChatMessage[] inputMessages =
        [
            new(ChatRole.User, [new TextContent("First message"), new HostedFileContent("caller-file-1")]) { MessageId = "caller-message-1" },
            new(ChatRole.User, [new TextContent("Second message"), new HostedFileContent("caller-file-2")]) { MessageId = "caller-message-2" },
        ];
        ExternalInputResponse response = new(inputMessages);

        // Act
        WorkflowEvent[] events =
            await this.ExecuteAsync(
                RequestExternalInputExecutor.Steps.Capture(action.Id),
                (context, message, cancellationToken) => action.CaptureResponseAsync(context, response, cancellationToken));

        // Assert
        VerifyCompletionEvent(events);
        mockAgentProvider.Verify(
            p => p.CreateMessageAsync(It.IsAny<string>(), It.IsAny<ChatMessage>(), It.IsAny<CancellationToken>()),
            Times.Never);
        this.VerifyState(VariableName, inputMessages.ToTable());
        this.VerifyState(SystemScope.Names.LastMessage, VariableScopeNames.System, inputMessages[1].ToRecord());
        this.VerifyState(SystemScope.Names.LastMessageId, VariableScopeNames.System, FormulaValue.New("caller-message-2"));
        this.VerifyState(SystemScope.Names.LastMessageText, VariableScopeNames.System, FormulaValue.New("Second message"));
    }

    [Fact]
    public async Task CaptureResponseWithEmptyMessagesAsync()
    {
        await this.CaptureResponseTestAsync(
            displayName: nameof(CaptureResponseWithEmptyMessagesAsync),
            variableName: "TestVariable",
            messageCount: 0);
    }

    [Fact]
    public async Task CaptureResponseWithEmptyMessagesPreservesMessageTableTypeAsync()
    {
        // Arrange
        const string VariableName = "TestVariable";
        RequestExternalInput model = this.CreateModel(nameof(CaptureResponseWithEmptyMessagesPreservesMessageTableTypeAsync), VariableName);
        MockAgentProvider mockAgentProvider = new();
        RequestExternalInputExecutor action = new(model, mockAgentProvider.Object, this.State);
        ExternalInputResponse response = new([]);

        // Act
        WorkflowEvent[] events =
            await this.ExecuteAsync(
                RequestExternalInputExecutor.Steps.Capture(action.Id),
                (context, message, cancellationToken) => action.CaptureResponseAsync(context, response, cancellationToken));

        // Assert
        VerifyCompletionEvent(events);
        TableValue table = Assert.IsAssignableFrom<TableValue>(this.State.Get(VariableName));
        Assert.Empty(table.Rows);
        Assert.Equal(TypeSchema.Message.RecordType.ToTable(), table.Type);
    }

    [Fact]
    public async Task CaptureResponseWithEmptyMessagesAndWorkflowConversationAsync()
    {
        // Arrange
        this.State.Set(SystemScope.Names.ConversationId, FormulaValue.New("WorkflowConversationId"), VariableScopeNames.System);

        // Act & Assert
        await this.CaptureResponseTestAsync(
            displayName: nameof(CaptureResponseWithEmptyMessagesAndWorkflowConversationAsync),
            variableName: "TestVariable",
            messageCount: 0,
            expectMessagesCreated: false);
    }

    private async Task ExecuteTestAsync(
        string displayName,
        string variableName)
    {
        MockAgentProvider mockAgentProvider = new();
        RequestExternalInput model = this.CreateModel(displayName, variableName);
        RequestExternalInputExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    private async Task CaptureResponseTestAsync(
        string displayName,
        string? variableName = null,
        int messageCount = 1,
        bool expectMessagesCreated = false)
    {
        // Arrange
        RequestExternalInput model = this.CreateModel(displayName, variableName);
        MockAgentProvider mockAgentProvider = new();
        RequestExternalInputExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Create test messages
        List<ChatMessage> testMessages = [];
        for (int i = 0; i < messageCount; i++)
        {
            testMessages.Add(new ChatMessage(ChatRole.User, $"Test message {i + 1}"));
        }

        ExternalInputResponse response = new(testMessages);

        // Act
        WorkflowEvent[] events =
            await this.ExecuteAsync(
                RequestExternalInputExecutor.Steps.Capture(action.Id),
                (context, message, cancellationToken) => action.CaptureResponseAsync(context, response, cancellationToken));

        // Assert
        VerifyModel(model, action);
        VerifyCompletionEvent(events);

        // Verify messages were created in the workflow conversation if expected
        mockAgentProvider.Verify(p => p.CreateMessageAsync(
            It.IsAny<string>(),
            It.IsAny<ChatMessage>(),
            It.IsAny<CancellationToken>()), Times.Exactly(expectMessagesCreated ? messageCount : 0));

        // Verify the variable was set correctly
        if (variableName is not null)
        {
            this.VerifyState(variableName, testMessages.ToTable());
        }
    }

    private RequestExternalInput CreateModel(string displayName, string? variablePath)
    {
        RequestExternalInput.Builder actionBuilder =
            new()
            {
                Id = this.CreateActionId(),
                DisplayName = this.FormatDisplayName(displayName),
                Variable = variablePath is null ? null : (InitializablePropertyPath?)PropertyPath.Create(FormatVariablePath(variablePath)),
            };

        return AssignParent<RequestExternalInput>(actionBuilder);
    }
}
