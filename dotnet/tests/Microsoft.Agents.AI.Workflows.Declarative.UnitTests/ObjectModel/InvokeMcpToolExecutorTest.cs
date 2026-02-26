// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Moq;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.ObjectModel;

/// <summary>
/// Tests for <see cref="InvokeMcpToolExecutor"/>.
/// </summary>
public sealed class InvokeMcpToolExecutorTest(ITestOutputHelper output) : WorkflowActionExecutorTest(output)
{
    private const string TestServerUrl = "https://mcp.example.com";
    private const string TestServerLabel = "TestMcpServer";
    private const string TestToolName = "test_tool";

    #region Step Naming Convention Tests

    [Fact]
    public void InvokeMcpToolThrowsWhenModelInvalid()
    {
        // Arrange
        Mock<IMcpToolHandler> mockProvider = new();
        MockAgentProvider mockAgentProvider = new();

        // Act & Assert
        Assert.Throws<DeclarativeModelException>(() => new InvokeMcpToolExecutor(
            new InvokeMcpTool(),
            mockProvider.Object,
            mockAgentProvider.Object,
            this.State));
    }

    [Fact]
    public void InvokeMcpToolNamingConvention()
    {
        // Arrange
        string testId = this.CreateActionId().Value;

        // Act
        string externalInputStep = InvokeMcpToolExecutor.Steps.ExternalInput(testId);
        string resumeStep = InvokeMcpToolExecutor.Steps.Resume(testId);

        // Assert
        Assert.Equal($"{testId}_{nameof(InvokeMcpToolExecutor.Steps.ExternalInput)}", externalInputStep);
        Assert.Equal($"{testId}_{nameof(InvokeMcpToolExecutor.Steps.Resume)}", resumeStep);
    }

    #endregion

    #region RequiresInput and RequiresNothing Tests

    [Fact]
    public void RequiresInputReturnsTrueForExternalInputRequest()
    {
        // Arrange
        ExternalInputRequest request = new(new AgentResponse([]));

        // Act
        bool result = InvokeMcpToolExecutor.RequiresInput(request);

        // Assert
        Assert.True(result);
    }

    [Fact]
    public void RequiresInputReturnsFalseForOtherTypes()
    {
        // Act & Assert
        Assert.False(InvokeMcpToolExecutor.RequiresInput(null));
        Assert.False(InvokeMcpToolExecutor.RequiresInput("string"));
        Assert.False(InvokeMcpToolExecutor.RequiresInput(new ActionExecutorResult("test")));
    }

    [Fact]
    public void RequiresNothingReturnsTrueForActionExecutorResult()
    {
        // Arrange
        ActionExecutorResult result = new("test");

        // Act
        bool requiresNothing = InvokeMcpToolExecutor.RequiresNothing(result);

        // Assert
        Assert.True(requiresNothing);
    }

    [Fact]
    public void RequiresNothingReturnsFalseForOtherTypes()
    {
        // Act & Assert
        Assert.False(InvokeMcpToolExecutor.RequiresNothing(null));
        Assert.False(InvokeMcpToolExecutor.RequiresNothing("string"));
        Assert.False(InvokeMcpToolExecutor.RequiresNothing(new ExternalInputRequest(new AgentResponse([]))));
    }

    #endregion

    #region ExecuteAsync Tests

    [Fact]
    public async Task InvokeMcpToolExecuteWithoutApprovalAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithoutApprovalAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            requireApproval: false);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithServerLabelAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithServerLabelAsync),
            serverUrl: TestServerUrl,
            serverLabel: TestServerLabel,
            toolName: TestToolName);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithArgumentsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithArgumentsAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            argumentKey: "query",
            argumentValue: "test query");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithHeadersAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithHeadersAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            headerKey: "Authorization",
            headerValue: "Bearer token123");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithRequireApprovalAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithRequireApprovalAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            requireApproval: true);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithEmptyConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithEmptyConversationIdAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            conversationId: "");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithNullArgumentsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithNullArgumentsAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            argumentKey: null);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithNullRequireApprovalAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithNullRequireApprovalAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            requireApproval: null);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithNullConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithNullConversationIdAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            conversationId: null);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithEmptyServerLabelAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithEmptyServerLabelAsync),
            serverUrl: TestServerUrl,
            serverLabel: "",
            toolName: TestToolName);

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithConversationIdAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            conversationId: "test-conversation-id");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithRequireApprovalAndHeadersAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithRequireApprovalAndHeadersAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            requireApproval: true,
            headerKey: "X-Custom-Header",
            headerValue: "custom-value");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithEmptyHeaderValueAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithEmptyHeaderValueAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            headerKey: "X-Empty-Header",
            headerValue: "");

        // Act and Assert
        await this.ExecuteTestAsync(model);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithJsonObjectResultAsync()
    {
        // Arrange - Tests JSON object parsing in AssignResultAsync
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithJsonObjectResultAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new(returnJsonObject: true);
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithJsonArrayResultAsync()
    {
        // Arrange - Tests JSON array parsing in AssignResultAsync
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithJsonArrayResultAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new(returnJsonArray: true);
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithInvalidJsonResultAsync()
    {
        // Arrange - Tests graceful handling of invalid JSON
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithInvalidJsonResultAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new(returnInvalidJson: true);
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert - Should handle gracefully
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithDataContentResultAsync()
    {
        // Arrange - Tests DataContent handling (returns URI)
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithDataContentResultAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new(returnDataContent: true);
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithEmptyOutputAsync()
    {
        // Arrange - Tests empty output list handling
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithEmptyOutputAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new(returnEmptyOutput: true);
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithNullOutputAsync()
    {
        // Arrange - Tests null output handling
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithNullOutputAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new(returnNullOutput: true);
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    [Fact]
    public async Task InvokeMcpToolExecuteWithMultipleContentTypesAsync()
    {
        // Arrange - Tests handling of multiple content types in output
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithMultipleContentTypesAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new(returnMultipleContent: true);
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
    }

    #endregion

    #region CaptureResponseAsync Tests

    [Fact]
    public async Task InvokeMcpToolCaptureResponseWithApprovalApprovedAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolCaptureResponseWithApprovalApprovedAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            requireApproval: true);
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Create approval request then response
        McpServerToolCallContent toolCall = new(action.Id, TestToolName, TestServerUrl);
        McpServerToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        McpServerToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeMcpToolCaptureResponseWithApprovalRejectedAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolCaptureResponseWithApprovalRejectedAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            requireApproval: true);
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Create approval request then response (rejected)
        McpServerToolCallContent toolCall = new(action.Id, TestToolName, TestServerUrl);
        McpServerToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        McpServerToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: false);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeMcpToolCaptureResponseWithEmptyMessagesAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolCaptureResponseWithEmptyMessagesAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Empty response - no approval found, should treat as rejected
        ExternalInputResponse response = new([]);

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeMcpToolCaptureResponseWithNonMatchingApprovalIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolCaptureResponseWithNonMatchingApprovalIdAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Create approval with different ID
        McpServerToolCallContent toolCall = new("different_id", TestToolName, TestServerUrl);
        McpServerToolApprovalRequestContent approvalRequest = new("different_id", toolCall);
        McpServerToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert - Should be treated as rejected since no matching approval
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeMcpToolCaptureResponseWithApprovedAndArgumentsAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolCaptureResponseWithApprovedAndArgumentsAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            requireApproval: true,
            argumentKey: "query",
            argumentValue: "test query");
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Create approval request then response
        McpServerToolCallContent toolCall = new(action.Id, TestToolName, TestServerUrl);
        McpServerToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        McpServerToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeMcpToolCaptureResponseWithApprovedAndHeadersAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolCaptureResponseWithApprovedAndHeadersAsync),
            serverUrl: TestServerUrl,
            serverLabel: TestServerLabel,
            toolName: TestToolName,
            requireApproval: true,
            headerKey: "X-Custom-Header",
            headerValue: "custom-value");
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Create approval request then response
        McpServerToolCallContent toolCall = new(action.Id, TestToolName, TestServerLabel);
        McpServerToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        McpServerToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    [Fact]
    public async Task InvokeMcpToolCaptureResponseWithApprovedAndConversationIdAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string ConversationId = "TestConversationId";
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolCaptureResponseWithApprovedAndConversationIdAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            requireApproval: true,
            conversationId: ConversationId);
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Create approval request then response
        McpServerToolCallContent toolCall = new(action.Id, TestToolName, TestServerUrl);
        McpServerToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        McpServerToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    #endregion

    #region CompleteAsync Tests

    [Fact]
    public async Task InvokeMcpToolCompleteAsyncRaisesCompletionEventAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolCompleteAsyncRaisesCompletionEventAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName);
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);
        ActionExecutorResult result = new(action.Id);

        // Act
        WorkflowEvent[] events = await this.ExecuteCompleteTestAsync(action, result);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    #endregion

    #region Helper Methods

    private async Task ExecuteTestAsync(InvokeMcpTool model)
    {
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);

        // IsDiscreteAction should be false for InvokeMcpTool
        VerifyIsDiscrete(action, isDiscrete: false);
    }

    private async Task<WorkflowEvent[]> ExecuteCaptureResponseTestAsync(
        InvokeMcpToolExecutor action,
        ExternalInputResponse response)
    {
        return await this.ExecuteAsync(
            action,
            InvokeMcpToolExecutor.Steps.ExternalInput(action.Id),
            (context, _, cancellationToken) => action.CaptureResponseAsync(context, response, cancellationToken));
    }

    private async Task<WorkflowEvent[]> ExecuteCompleteTestAsync(
        InvokeMcpToolExecutor action,
        ActionExecutorResult result)
    {
        return await this.ExecuteAsync(
            action,
            InvokeMcpToolExecutor.Steps.Resume(action.Id),
            (context, _, cancellationToken) => action.CompleteAsync(context, result, cancellationToken));
    }

    private InvokeMcpTool CreateModel(
        string displayName,
        string serverUrl,
        string toolName,
        string? serverLabel = null,
        bool? requireApproval = false,
        string? conversationId = null,
        string? argumentKey = null,
        string? argumentValue = null,
        string? headerKey = null,
        string? headerValue = null)
    {
        InvokeMcpTool.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            ServerUrl = new StringExpression.Builder(StringExpression.Literal(serverUrl)),
            ToolName = new StringExpression.Builder(StringExpression.Literal(toolName)),
            RequireApproval = requireApproval != null ? new BoolExpression.Builder(BoolExpression.Literal(requireApproval.Value)) : null
        };

        if (serverLabel is not null)
        {
            builder.ServerLabel = new StringExpression.Builder(StringExpression.Literal(serverLabel));
        }

        if (conversationId is not null)
        {
            builder.ConversationId = new StringExpression.Builder(StringExpression.Literal(conversationId));
        }

        if (argumentKey is not null && argumentValue is not null)
        {
            builder.Arguments.Add(argumentKey, ValueExpression.Literal(new StringDataValue(argumentValue)));
        }

        if (headerKey is not null && headerValue is not null)
        {
            builder.Headers.Add(headerKey, new StringExpression.Builder(StringExpression.Literal(headerValue)));
        }

        return AssignParent<InvokeMcpTool>(builder);
    }

    #endregion

    #region Mock MCP Tool Provider

    /// <summary>
    /// Mock implementation of <see cref="IMcpToolHandler"/> for unit testing purposes.
    /// </summary>
    private sealed class MockMcpToolProvider : Mock<IMcpToolHandler>
    {
        public MockMcpToolProvider(
            bool returnJsonObject = false,
            bool returnJsonArray = false,
            bool returnInvalidJson = false,
            bool returnDataContent = false,
            bool returnEmptyOutput = false,
            bool returnNullOutput = false,
            bool returnMultipleContent = false)
        {
            this.Setup(provider => provider.InvokeToolAsync(
                    It.IsAny<string>(),
                    It.IsAny<string?>(),
                    It.IsAny<string>(),
                    It.IsAny<IDictionary<string, object?>?>(),
                    It.IsAny<IDictionary<string, string>?>(),
                    It.IsAny<string?>(),
                    It.IsAny<CancellationToken>()))
                .Returns<string, string?, string, IDictionary<string, object?>?, IDictionary<string, string>?, string?, CancellationToken>(
                    (_, _, _, _, _, _, _) =>
                    {
                        McpServerToolResultContent result = new("mock-call-id");

                        if (returnNullOutput)
                        {
                            result.Output = null;
                        }
                        else if (returnEmptyOutput)
                        {
                            result.Output = [];
                        }
                        else if (returnJsonObject)
                        {
                            result.Output = [new TextContent("{\"key\": \"value\", \"number\": 42}")];
                        }
                        else if (returnJsonArray)
                        {
                            result.Output = [new TextContent("[1, 2, 3, \"four\"]")];
                        }
                        else if (returnInvalidJson)
                        {
                            result.Output = [new TextContent("this is not valid json {")];
                        }
                        else if (returnDataContent)
                        {
                            result.Output = [new DataContent("data:image/png;base64,iVBORw0KGgo=", "image/png")];
                        }
                        else if (returnMultipleContent)
                        {
                            result.Output =
                            [
                                new TextContent("First text"),
                                new TextContent("{\"nested\": true}"),
                                new DataContent("data:audio/mp3;base64,SUQz", "audio/mp3")
                            ];
                        }
                        else
                        {
                            result.Output = [new TextContent("Mock MCP tool result")];
                        }

                        return Task.FromResult(result);
                    });
        }
    }

    #endregion
}
