// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="InvokeFunctionToolExecutor"/>.
/// </summary>
public sealed class InvokeFunctionToolExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    #region Step Naming Convention Tests

    [Fact]
    public void InvokeFunctionToolThrowsWhenModelInvalid() =>
        // Arrange, Act & Assert
        Assert.Throws<DeclarativeModelException>(() => new InvokeFunctionToolExecutor(new InvokeFunctionTool(), new MockAgentProvider().Object, this.State));

    [Fact]
    public void InvokeFunctionToolNamingConvention()
    {
        // Arrange
        string testId = this.CreateActionId().Value;

        // Act
        string externalInputStep = InvokeFunctionToolExecutor.Steps.ExternalInput(testId);
        string resumeStep = InvokeFunctionToolExecutor.Steps.Resume(testId);

        // Assert
        Assert.Equal($"{testId}_{nameof(InvokeFunctionToolExecutor.Steps.ExternalInput)}", externalInputStep);
        Assert.Equal($"{testId}_{nameof(InvokeFunctionToolExecutor.Steps.Resume)}", resumeStep);
    }

    #endregion

    #region ExecuteAsync Tests

    [Fact]
    public async Task InvokeFunctionToolExecuteWithoutApprovalAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithoutApprovalAsync),
            functionName: "simple_function",
            requireApproval: false);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithArgumentsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithArgumentsAsync),
            functionName: "get_weather",
            argumentKey: "location",
            argumentValue: "Seattle");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithRequireApprovalAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithRequireApprovalAsync),
            functionName: "approval_function",
            requireApproval: true);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithEmptyConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithEmptyConversationIdAsync),
            functionName: "test_function",
            conversationId: "");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithNullArgumentsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithNullArgumentsAsync),
            functionName: "no_args_function",
            argumentKey: null);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithNullRequireApprovalAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithNullRequireApprovalAsync),
            functionName: "test_function",
            requireApproval: null);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeFunctionToolExecuteWithNullConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolExecuteWithNullConversationIdAsync),
            functionName: "test_function",
            conversationId: null);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    #endregion

    #region CaptureResponseAsync Tests

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithNoOutputConfiguredAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithNoOutputConfiguredAsync),
            functionName: "test_function");
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        FunctionResultContent functionResult = new(action.Id, "Result without output");
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [functionResult]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithEmptyMessagesAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithEmptyMessagesAsync),
            functionName: "test_function");
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Empty response
        ExternalInputResponse response = new([]);

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string ConversationId = "TestConversationId";
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithConversationIdAsync),
            functionName: "test_function",
            conversationId: ConversationId);
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        FunctionResultContent functionResult = new(action.Id, "Result for conversation");
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [functionResult]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithNonMatchingResultAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithNonMatchingResultAsync),
            functionName: "test_function");
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Use a different call ID that doesn't match the action ID
        FunctionResultContent functionResult = new("different_call_id", "Different result");
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [functionResult]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeFunctionToolCaptureResponseWithMultipleFunctionResultsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeFunctionTool model = this.CreateModel(
            displayName: nameof(InvokeFunctionToolCaptureResponseWithMultipleFunctionResultsAsync),
            functionName: "test_function",
            conversationId: "TestConversation");
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Multiple function results - the matching one should be captured
        FunctionResultContent nonMatchingResult = new("other_call_id", "Other result");
        FunctionResultContent matchingResult = new(action.Id, "Matching result");
        ExternalInputResponse response = new(new ChatMessage(ChatRole.Tool, [nonMatchingResult, matchingResult]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    #endregion

    #region Helper Methods

    private async Task ExecuteTestAsync(InvokeFunctionTool model)
    {
        MockAgentProvider mockAgentProvider = new();
        InvokeFunctionToolExecutor action = new(model, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);

        // IsDiscreteAction should be false for InvokeFunction
        VerifyIsDiscrete(action, isDiscrete: false);
    }

    private async Task<WorkflowEvent[]> ExecuteCaptureResponseTestAsync(
        InvokeFunctionToolExecutor action,
        ExternalInputResponse response)
    {
        return await this.ExecuteAsync(
            action,
            InvokeFunctionToolExecutor.Steps.ExternalInput(action.Id),
            (context, _, cancellationToken) => action.CaptureResponseAsync(context, response, cancellationToken));
    }

    private InvokeFunctionTool CreateModel(
        string displayName,
        string functionName,
        bool? requireApproval = false,
        string? conversationId = null,
        string? argumentKey = null,
        string? argumentValue = null)
    {
        InvokeFunctionTool.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            FunctionName = new StringExpression.Builder(StringExpression.Literal(functionName)),
            RequireApproval = requireApproval != null ? new BoolExpression.Builder(BoolExpression.Literal(requireApproval.Value)) : null
        };

        if (conversationId is not null)
        {
            builder.ConversationId = new StringExpression.Builder(StringExpression.Literal(conversationId));
        }

        if (argumentKey is not null && argumentValue is not null)
        {
            builder.Arguments.Add(argumentKey, ValueExpression.Literal(new StringDataValue(argumentValue)));
        }

        return AssignParent<InvokeFunctionTool>(builder);
    }

    #endregion
}
