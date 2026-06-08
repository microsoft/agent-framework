// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Moq;
using ApprovalSnapshot = Microsoft.Agents.AI.Workflows.Declarative.ObjectModel.InvokeMcpToolExecutor.ApprovalSnapshot;

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
    public async Task InvokeMcpToolApprovalRequestExcludesTransportHeadersAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolApprovalRequestExcludesTransportHeadersAsync),
            serverUrl: TestServerUrl,
            serverLabel: TestServerLabel,
            toolName: TestToolName,
            requireApproval: true,
            headerKey: "Authorization",
            headerValue: "Bearer super-secret-token");
        MockMcpToolProvider mockProvider = new();
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        ExternalInputRequest? capturedRequest = null;

        // Act
        await this.ExecuteAsync(
            [
                action,
                new DelegateActionExecutor<ExternalInputRequest>(
                    InvokeMcpToolExecutor.Steps.ExternalInput(action.Id),
                    this.State,
                    CaptureRequestAsync)
            ],
            isDiscrete: false);

        // Assert - the approval event must not carry any transport headers (e.g. Authorization).
        Assert.NotNull(capturedRequest);
        ToolApprovalRequestContent approvalRequest =
            capturedRequest!.AgentResponse.Messages
                .SelectMany(message => message.Contents)
                .OfType<ToolApprovalRequestContent>()
                .Single();

        AdditionalPropertiesDictionary? additionalProperties = approvalRequest.ToolCall.AdditionalProperties;
        Assert.True(additionalProperties is null || additionalProperties.Count == 0);

        // Defense in depth: the credential value must not appear anywhere in the serialized approval content.
        string serializedApproval = System.Text.Json.JsonSerializer.Serialize(capturedRequest.AgentResponse);
        Assert.DoesNotContain("super-secret-token", serializedApproval);

        ValueTask CaptureRequestAsync(IWorkflowContext context, ExternalInputRequest request, CancellationToken cancellationToken)
        {
            capturedRequest = request;
            return default;
        }
    }

    [Fact]
    public async Task InvokeMcpToolInvocationForwardsHeadersToTransportAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string HeaderKey = "Authorization";
        const string HeaderValue = "Bearer super-secret-token";
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolInvocationForwardsHeadersToTransportAsync),
            serverUrl: TestServerUrl,
            serverLabel: TestServerLabel,
            toolName: TestToolName,
            requireApproval: false,
            headerKey: HeaderKey,
            headerValue: HeaderValue);

        IDictionary<string, string>? capturedHeaders = null;
        Mock<IMcpToolHandler> mockProvider = new();
        mockProvider
            .Setup(provider => provider.InvokeToolAsync(
                It.IsAny<string>(),
                It.IsAny<string?>(),
                It.IsAny<string>(),
                It.IsAny<IDictionary<string, object?>?>(),
                It.IsAny<IDictionary<string, string>?>(),
                It.IsAny<string?>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, string?, string, IDictionary<string, object?>?, IDictionary<string, string>?, string?, CancellationToken>(
                (_, _, _, _, headers, _, _) => capturedHeaders = headers)
            .ReturnsAsync(new McpServerToolResultContent("mock-call-id") { Outputs = [new TextContent("ok")] });
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        await this.ExecuteAsync(action, isDiscrete: false);

        // Assert - headers remain available to the actual transport invocation.
        Assert.NotNull(capturedHeaders);
        Assert.True(capturedHeaders!.TryGetValue(HeaderKey, out string? forwardedValue));
        Assert.Equal(HeaderValue, forwardedValue);
    }

    [Fact]
    public async Task InvokeMcpToolApprovedCaptureResponseForwardsHeadersToTransportAsync()
    {
        // Arrange - exercises the post-approval CaptureResponseAsync resume path to prove the
        // fix did not regress header forwarding on the path that the vulnerability actually targets.
        this.State.InitializeSystem();
        const string HeaderKey = "Authorization";
        const string HeaderValue = "Bearer super-secret-token";
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolApprovedCaptureResponseForwardsHeadersToTransportAsync),
            serverUrl: TestServerUrl,
            serverLabel: TestServerLabel,
            toolName: TestToolName,
            requireApproval: true,
            headerKey: HeaderKey,
            headerValue: HeaderValue);

        IDictionary<string, string>? capturedHeaders = null;
        Mock<IMcpToolHandler> mockProvider = new();
        mockProvider
            .Setup(provider => provider.InvokeToolAsync(
                It.IsAny<string>(),
                It.IsAny<string?>(),
                It.IsAny<string>(),
                It.IsAny<IDictionary<string, object?>?>(),
                It.IsAny<IDictionary<string, string>?>(),
                It.IsAny<string?>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, string?, string, IDictionary<string, object?>?, IDictionary<string, string>?, string?, CancellationToken>(
                (_, _, _, _, headers, _, _) => capturedHeaders = headers)
            .ReturnsAsync(new McpServerToolResultContent("mock-call-id") { Outputs = [new TextContent("ok")] });
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        Mock<IWorkflowContext> mockContext = new(MockBehavior.Loose);

        // Build an approved response matching this action's request id.
        McpServerToolCallContent toolCall = new(action.Id, TestToolName, TestServerLabel);
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Act - call CaptureResponseAsync directly so the post-approval branch actually executes.
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - headers reach the transport invocation on the approved path.
        Assert.NotNull(capturedHeaders);
        Assert.True(capturedHeaders!.TryGetValue(HeaderKey, out string? forwardedValue));
        Assert.Equal(HeaderValue, forwardedValue);
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
    public async Task InvokeMcpToolExecuteWithReservedListToolsNameAsync()
    {
        // Arrange
        this.State.InitializeSystem();
        const string ListToolsToolName = "tools/list";
        string? capturedToolName = null;
        InvokeMcpTool model = this.CreateModel(
            displayName: nameof(InvokeMcpToolExecuteWithReservedListToolsNameAsync),
            serverUrl: TestServerUrl,
            toolName: ListToolsToolName);
        Mock<IMcpToolHandler> mockProvider = new();
        mockProvider.Setup(provider => provider.InvokeToolAsync(
                It.IsAny<string>(),
                It.IsAny<string?>(),
                It.IsAny<string>(),
                It.IsAny<IDictionary<string, object?>?>(),
                It.IsAny<IDictionary<string, string>?>(),
                It.IsAny<string?>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, string?, string, IDictionary<string, object?>?, IDictionary<string, string>?, string?, CancellationToken>(
                (_, _, toolName, _, _, _, _) => capturedToolName = toolName)
            .ReturnsAsync(new McpServerToolResultContent("list-tools-call-id")
            {
                Outputs = [new TextContent("{\"tools\":[]}")]
            });
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act
        WorkflowEvent[] events = await this.ExecuteAsync(action, isDiscrete: false);

        // Assert
        VerifyModel(model, action);
        VerifyInvocationEvent(events);
        Assert.Equal(ListToolsToolName, capturedToolName);
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
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
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
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: false);
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
        ToolApprovalRequestContent approvalRequest = new("different_id", toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
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
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
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
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
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
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Act
        WorkflowEvent[] events = await this.ExecuteCaptureResponseTestAsync(action, response);

        // Assert
        VerifyModel(model, action);
        Assert.NotEmpty(events);
    }

    #endregion

    #region Approval Snapshot Security Tests

    /// <summary>
    /// Verifies that mutating the tool name variable after approval does not change
    /// which tool is actually invoked. The originally-approved tool name must be used.
    /// </summary>
    [Fact]
    public async Task InvokeMcpToolCaptureResponseUsesApprovedToolNameNotMutatedAsync()
    {
        // Arrange
        const string ApprovedToolName = "safe_readonly_query";
        const string MutatedToolName = "dangerous_admin_tool";

        this.State.Set("TargetTool", FormulaValue.New(ApprovedToolName));
        this.State.InitializeSystem();
        this.State.Bind();

        InvokeMcpTool model = this.CreateModelWithVariableToolName(
            displayName: nameof(InvokeMcpToolCaptureResponseUsesApprovedToolNameNotMutatedAsync),
            serverUrl: TestServerUrl,
            variableName: "TargetTool");

        string? capturedToolName = null;
        Mock<IMcpToolHandler> mockProvider = new();
        mockProvider.Setup(provider => provider.InvokeToolAsync(
                It.IsAny<string>(),
                It.IsAny<string?>(),
                It.IsAny<string>(),
                It.IsAny<IDictionary<string, object?>?>(),
                It.IsAny<IDictionary<string, string>?>(),
                It.IsAny<string?>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, string?, string, IDictionary<string, object?>?, IDictionary<string, string>?, string?, CancellationToken>(
                (_, _, toolName, _, _, _, _) => capturedToolName = toolName)
            .ReturnsAsync(new McpServerToolResultContent("capture-call-id")
            {
                Outputs = [new TextContent("result")]
            });
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act - trigger ExecuteAsync to store the approval snapshot
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext();
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate parallel branch mutating state during the approval window
        this.State.Set("TargetTool", FormulaValue.New(MutatedToolName));
        this.State.Bind();

        // User clicks approve (they saw "safe_readonly_query" in the approval UI)
        McpServerToolCallContent toolCall = new(action.Id, ApprovedToolName, TestServerUrl);
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Resume after approval
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the originally-approved tool name must be used, not the mutated one
        Assert.NotNull(capturedToolName);
        Assert.Equal(ApprovedToolName, capturedToolName);
    }

    /// <summary>
    /// Verifies that mutating an argument variable after approval does not change
    /// the arguments actually passed to the MCP tool. The originally-approved arguments must be used.
    /// </summary>
    [Fact]
    public async Task InvokeMcpToolCaptureResponseUsesApprovedArgumentsNotMutatedAsync()
    {
        // Arrange
        const string ApprovedQuery = "SELECT * FROM users LIMIT 10";
        const string MutatedQuery = "DROP TABLE users CASCADE; --";

        this.State.Set("SqlQuery", FormulaValue.New(ApprovedQuery));
        this.State.InitializeSystem();
        this.State.Bind();

        InvokeMcpTool model = this.CreateModelWithVariableArgument(
            displayName: nameof(InvokeMcpToolCaptureResponseUsesApprovedArgumentsNotMutatedAsync),
            serverUrl: TestServerUrl,
            toolName: TestToolName,
            argumentKey: "query",
            variableName: "SqlQuery");

        IDictionary<string, object?>? capturedArguments = null;
        Mock<IMcpToolHandler> mockProvider = new();
        mockProvider.Setup(provider => provider.InvokeToolAsync(
                It.IsAny<string>(),
                It.IsAny<string?>(),
                It.IsAny<string>(),
                It.IsAny<IDictionary<string, object?>?>(),
                It.IsAny<IDictionary<string, string>?>(),
                It.IsAny<string?>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, string?, string, IDictionary<string, object?>?, IDictionary<string, string>?, string?, CancellationToken>(
                (_, _, _, arguments, _, _, _) => capturedArguments = arguments)
            .ReturnsAsync(new McpServerToolResultContent("capture-call-id")
            {
                Outputs = [new TextContent("result")]
            });
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act - trigger ExecuteAsync to store the approval snapshot
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext();
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate parallel branch mutating state during the approval window
        this.State.Set("SqlQuery", FormulaValue.New(MutatedQuery));
        this.State.Bind();

        // User clicks approve
        McpServerToolCallContent toolCall = new(action.Id, TestToolName, TestServerUrl);
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Resume after approval
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the originally-approved argument must be used, not the mutated one
        Assert.NotNull(capturedArguments);
        Assert.Equal(ApprovedQuery, capturedArguments["query"]?.ToString());
    }

    /// <summary>
    /// Verifies that mutating the server URL variable after approval does not redirect
    /// the MCP tool call to a different server. The originally-approved server URL must be used.
    /// </summary>
    [Fact]
    public async Task InvokeMcpToolCaptureResponseUsesApprovedServerUrlNotMutatedAsync()
    {
        // Arrange
        const string ApprovedServerUrl = "https://internal-mcp.corp";
        const string MutatedServerUrl = "https://attacker.evil/steal";

        this.State.Set("McpEndpoint", FormulaValue.New(ApprovedServerUrl));
        this.State.InitializeSystem();
        this.State.Bind();

        InvokeMcpTool model = this.CreateModelWithVariableServerUrl(
            displayName: nameof(InvokeMcpToolCaptureResponseUsesApprovedServerUrlNotMutatedAsync),
            variableName: "McpEndpoint",
            toolName: TestToolName);

        string? capturedServerUrl = null;
        Mock<IMcpToolHandler> mockProvider = new();
        mockProvider.Setup(provider => provider.InvokeToolAsync(
                It.IsAny<string>(),
                It.IsAny<string?>(),
                It.IsAny<string>(),
                It.IsAny<IDictionary<string, object?>?>(),
                It.IsAny<IDictionary<string, string>?>(),
                It.IsAny<string?>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, string?, string, IDictionary<string, object?>?, IDictionary<string, string>?, string?, CancellationToken>(
                (serverUrl, _, _, _, _, _, _) => capturedServerUrl = serverUrl)
            .ReturnsAsync(new McpServerToolResultContent("capture-call-id")
            {
                Outputs = [new TextContent("result")]
            });
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act - trigger ExecuteAsync to store the approval snapshot
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContext();
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate parallel branch mutating state during the approval window
        this.State.Set("McpEndpoint", FormulaValue.New(MutatedServerUrl));
        this.State.Bind();

        // User clicks approve
        McpServerToolCallContent toolCall = new(action.Id, TestToolName, ApprovedServerUrl);
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Resume after approval
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the originally-approved server URL must be used, not the mutated one
        Assert.NotNull(capturedServerUrl);
        Assert.Equal(ApprovedServerUrl, capturedServerUrl);
    }

    /// <summary>
    /// Verifies that the approval snapshot survives a checkpoint/restore cycle.
    /// After restore, the originally-approved tool name must still be used even if state was mutated.
    /// </summary>
    [Fact]
    public async Task InvokeMcpToolCaptureResponseUsesSnapshotAfterCheckpointRestoreAsync()
    {
        // Arrange
        const string ApprovedToolName = "safe_readonly_query";
        const string MutatedToolName = "dangerous_admin_tool";

        this.State.Set("TargetTool", FormulaValue.New(ApprovedToolName));
        this.State.InitializeSystem();
        this.State.Bind();

        InvokeMcpTool model = this.CreateModelWithVariableToolName(
            displayName: nameof(InvokeMcpToolCaptureResponseUsesSnapshotAfterCheckpointRestoreAsync),
            serverUrl: TestServerUrl,
            variableName: "TargetTool");

        string? capturedToolName = null;
        Mock<IMcpToolHandler> mockProvider = new();
        mockProvider.Setup(provider => provider.InvokeToolAsync(
                It.IsAny<string>(),
                It.IsAny<string?>(),
                It.IsAny<string>(),
                It.IsAny<IDictionary<string, object?>?>(),
                It.IsAny<IDictionary<string, string>?>(),
                It.IsAny<string?>(),
                It.IsAny<CancellationToken>()))
            .Callback<string, string?, string, IDictionary<string, object?>?, IDictionary<string, string>?, string?, CancellationToken>(
                (_, _, toolName, _, _, _, _) => capturedToolName = toolName)
            .ReturnsAsync(new McpServerToolResultContent("capture-call-id")
            {
                Outputs = [new TextContent("result")]
            });
        MockAgentProvider mockAgentProvider = new();
        InvokeMcpToolExecutor action = new(model, mockProvider.Object, mockAgentProvider.Object, this.State);

        // Act - trigger ExecuteAsync to store the approval snapshot
        Mock<IWorkflowContext> mockContext = CreateMockWorkflowContextWithStateStore();
        await action.HandleAsync(new ActionExecutorResult(action.Id), mockContext.Object, CancellationToken.None);

        // Simulate checkpoint: persist to state store
        await InvokeProtectedMethodAsync(action, "OnCheckpointingAsync", mockContext.Object, CancellationToken.None);

        // Simulate restore on a "new" executor instance by clearing the in-memory field via reflection
        // (In production, a new executor instance would be created with _approvalSnapshot == null)
        typeof(InvokeMcpToolExecutor)
            .GetField("_approvalSnapshot", BindingFlags.NonPublic | BindingFlags.Instance)!
            .SetValue(action, null);

        // Restore from state store
        await InvokeProtectedMethodAsync(action, "OnCheckpointRestoredAsync", mockContext.Object, CancellationToken.None);

        // Mutate state after restore (simulating parallel branch)
        this.State.Set("TargetTool", FormulaValue.New(MutatedToolName));
        this.State.Bind();

        // User clicks approve
        McpServerToolCallContent toolCall = new(action.Id, ApprovedToolName, TestServerUrl);
        ToolApprovalRequestContent approvalRequest = new(action.Id, toolCall);
        ToolApprovalResponseContent approvalResponse = approvalRequest.CreateResponse(approved: true);
        ExternalInputResponse response = new(new ChatMessage(ChatRole.User, [approvalResponse]));

        // Resume after approval
        await action.CaptureResponseAsync(mockContext.Object, response, CancellationToken.None);

        // Assert - the originally-approved tool name must be used, not the mutated one
        Assert.NotNull(capturedToolName);
        Assert.Equal(ApprovedToolName, capturedToolName);
    }

    private static Mock<IWorkflowContext> CreateMockWorkflowContext()
    {
        Mock<IWorkflowContext> mockContext = new();
        mockContext.Setup(c => c.AddEventAsync(It.IsAny<WorkflowEvent>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<object?>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.SendMessageAsync(It.IsAny<object>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        return mockContext;
    }

    /// <summary>
    /// Creates a mock workflow context that actually stores state values (for checkpoint/restore tests).
    /// </summary>
    private static Mock<IWorkflowContext> CreateMockWorkflowContextWithStateStore()
    {
        Dictionary<string, object?> stateStore = new();
        Mock<IWorkflowContext> mockContext = new();
        mockContext.Setup(c => c.AddEventAsync(It.IsAny<WorkflowEvent>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.QueueStateUpdateAsync(It.IsAny<string>(), It.IsAny<ApprovalSnapshot?>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Callback<string, ApprovalSnapshot?, string?, CancellationToken>((key, value, _, _) => stateStore[key] = value)
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.SendMessageAsync(It.IsAny<object>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns(default(ValueTask));
        mockContext.Setup(c => c.ReadStateAsync<ApprovalSnapshot>(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .Returns<string, string?, CancellationToken>((key, _, _) =>
                new ValueTask<ApprovalSnapshot?>(stateStore.TryGetValue(key, out object? val) ? val as ApprovalSnapshot : null));
        mockContext.Setup(c => c.ReadStateKeysAsync(It.IsAny<string?>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new HashSet<string>());
        return mockContext;
    }

    /// <summary>
    /// Invokes a protected method on an executor via reflection (for testing checkpoint hooks).
    /// </summary>
    private static async ValueTask InvokeProtectedMethodAsync(InvokeMcpToolExecutor action, string methodName, IWorkflowContext context, CancellationToken cancellationToken)
    {
        MethodInfo method = typeof(InvokeMcpToolExecutor)
            .GetMethod(methodName, BindingFlags.NonPublic | BindingFlags.Instance)!;
        ValueTask result = (ValueTask)method.Invoke(action, [context, cancellationToken])!;
        await result.ConfigureAwait(false);
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

    private InvokeMcpTool CreateModelWithVariableToolName(string displayName, string serverUrl, string variableName)
    {
        InvokeMcpTool.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            ServerUrl = new StringExpression.Builder(StringExpression.Literal(serverUrl)),
            ToolName = new StringExpression.Builder(
                StringExpression.Variable(PropertyPath.TopicVariable(variableName))),
            RequireApproval = new BoolExpression.Builder(BoolExpression.Literal(true)),
        };
        return AssignParent<InvokeMcpTool>(builder);
    }

    private InvokeMcpTool CreateModelWithVariableArgument(
        string displayName, string serverUrl, string toolName, string argumentKey, string variableName)
    {
        InvokeMcpTool.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            ServerUrl = new StringExpression.Builder(StringExpression.Literal(serverUrl)),
            ToolName = new StringExpression.Builder(StringExpression.Literal(toolName)),
            RequireApproval = new BoolExpression.Builder(BoolExpression.Literal(true)),
        };
        builder.Arguments.Add(argumentKey,
            ValueExpression.Variable(PropertyPath.TopicVariable(variableName)));
        return AssignParent<InvokeMcpTool>(builder);
    }

    private InvokeMcpTool CreateModelWithVariableServerUrl(string displayName, string variableName, string toolName)
    {
        InvokeMcpTool.Builder builder = new()
        {
            Id = this.CreateActionId(),
            DisplayName = this.FormatDisplayName(displayName),
            ServerUrl = new StringExpression.Builder(
                StringExpression.Variable(PropertyPath.TopicVariable(variableName))),
            ToolName = new StringExpression.Builder(StringExpression.Literal(toolName)),
            RequireApproval = new BoolExpression.Builder(BoolExpression.Literal(true)),
        };
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
                            result.Outputs = null;
                        }
                        else if (returnEmptyOutput)
                        {
                            result.Outputs = [];
                        }
                        else if (returnJsonObject)
                        {
                            result.Outputs = [new TextContent("{\"key\": \"value\", \"number\": 42}")];
                        }
                        else if (returnJsonArray)
                        {
                            result.Outputs = [new TextContent("[1, 2, 3, \"four\"]")];
                        }
                        else if (returnInvalidJson)
                        {
                            result.Outputs = [new TextContent("this is not valid json {")];
                        }
                        else if (returnDataContent)
                        {
                            result.Outputs = [new DataContent("data:image/png;base64,iVBORw0KGgo=", "image/png")];
                        }
                        else if (returnMultipleContent)
                        {
                            result.Outputs =
                            [
                                new TextContent("First text"),
                                new TextContent("{\"nested\": true}"),
                                new DataContent("data:audio/mp3;base64,SUQz", "audio/mp3")
                            ];
                        }
                        else
                        {
                            result.Outputs = [new TextContent("Mock MCP tool result")];
                        }

                        return Task.FromResult(result);
                    });
        }
    }

    #endregion
}
