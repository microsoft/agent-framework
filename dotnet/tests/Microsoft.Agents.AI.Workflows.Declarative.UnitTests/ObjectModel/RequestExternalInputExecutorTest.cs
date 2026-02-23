// Copyright (c) Microsoft. All rights reserved.

using System;
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
