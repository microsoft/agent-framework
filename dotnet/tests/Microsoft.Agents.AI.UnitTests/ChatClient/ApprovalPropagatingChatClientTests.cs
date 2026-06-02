// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Moq;
using ApprovalPropagatingChatClient = Microsoft.Agents.AI.ChatClient.ApprovalPropagatingChatClient;
using RootToolApprovalRequestPropagator = Microsoft.Agents.AI.ToolApprovalRequestPropagator;

namespace Microsoft.Agents.AI.UnitTests.ChatClient;

/// <summary>
/// Tests for <see cref="ApprovalPropagatingChatClient"/>.
/// </summary>
public sealed class ApprovalPropagatingChatClientTests
{
    [Fact]
    public async Task GetResponseAsync_WhenFunctionCallHasAttachedApproval_AppendsApprovalAndRemovesPrematureResultAsync()
    {
        // Arrange
        var parentFunctionCall = new FunctionCallContent("parent-call", "SpecialistAgent");
        var parentFunctionResult = new FunctionResultContent(parentFunctionCall.CallId, "premature result");
        var parentApproval = new ToolApprovalRequestContent("approval-1", parentFunctionCall);
        RootToolApprovalRequestPropagator.Attach(parentFunctionCall, [parentApproval]);

        var innerResponse = new ChatResponse([
            new ChatMessage(ChatRole.Assistant, [parentFunctionCall]),
            new ChatMessage(ChatRole.Tool, [parentFunctionResult]),
        ]);

        var innerClient = new Mock<IChatClient>();
        innerClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerResponse);

        var client = new ApprovalPropagatingChatClient(innerClient.Object);

        // Act
        var response = await client.GetResponseAsync([new ChatMessage(ChatRole.User, "route this")]);

        // Assert
        Assert.Equal(2, response.Messages.Count);
        Assert.Contains(response.Messages[0].Contents, content => content is FunctionCallContent);
        Assert.DoesNotContain(response.Messages.SelectMany(message => message.Contents), content => content is FunctionResultContent);

        var propagatedApproval = Assert.Single(response.Messages[1].Contents.OfType<ToolApprovalRequestContent>());
        Assert.Equal("approval-1", propagatedApproval.RequestId);
        Assert.Same(parentFunctionCall, propagatedApproval.ToolCall);
    }

    [Fact]
    public async Task GetResponseAsync_WhenFunctionCallHasNoAttachedApproval_ReturnsResponseUnchangedAsync()
    {
        // Arrange
        var parentFunctionCall = new FunctionCallContent("parent-call", "SpecialistAgent");
        var parentFunctionResult = new FunctionResultContent(parentFunctionCall.CallId, "normal result");
        var innerResponse = new ChatResponse([
            new ChatMessage(ChatRole.Assistant, [parentFunctionCall]),
            new ChatMessage(ChatRole.Tool, [parentFunctionResult]),
        ]);

        var innerClient = new Mock<IChatClient>();
        innerClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerResponse);

        var client = new ApprovalPropagatingChatClient(innerClient.Object);

        // Act
        var response = await client.GetResponseAsync([new ChatMessage(ChatRole.User, "route this")]);

        // Assert
        Assert.Same(innerResponse, response);
        Assert.Contains(response.Messages.SelectMany(message => message.Contents), content => content is FunctionResultContent);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WhenFunctionCallHasAttachedApproval_YieldsApprovalAndFiltersPrematureResultAsync()
    {
        // Arrange
        var parentFunctionCall = new FunctionCallContent("parent-call", "SpecialistAgent");
        var parentFunctionResult = new FunctionResultContent(parentFunctionCall.CallId, "premature result");
        var parentApproval = new ToolApprovalRequestContent("approval-1", parentFunctionCall);
        RootToolApprovalRequestPropagator.Attach(parentFunctionCall, [parentApproval]);

        var innerClient = new Mock<IChatClient>();
        innerClient
            .Setup(client => client.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(GetStreamingUpdatesAsync(parentFunctionCall, parentFunctionResult));

        var client = new ApprovalPropagatingChatClient(innerClient.Object);
        var updates = new List<ChatResponseUpdate>();

        // Act
        await foreach (var update in client.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "route this")]))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Equal(2, updates.Count);
        Assert.Contains(updates[0].Contents, content => content is FunctionCallContent);
        Assert.DoesNotContain(updates.SelectMany(update => update.Contents), content => content is FunctionResultContent);

        var propagatedApproval = Assert.Single(updates[1].Contents.OfType<ToolApprovalRequestContent>());
        Assert.Equal("approval-1", propagatedApproval.RequestId);
        Assert.Same(parentFunctionCall, propagatedApproval.ToolCall);
    }

    [Fact]
    public async Task GetResponseAsync_WithMixedFunctionCalls_RemovesOnlyResultsForCallsAwaitingApprovalAsync()
    {
        // Arrange
        var pendingFunctionCall = new FunctionCallContent("pending-call", "SpecialistAgent");
        var completedFunctionCall = new FunctionCallContent("completed-call", "SafeTool");
        var pendingResult = new FunctionResultContent(pendingFunctionCall.CallId, "premature result");
        var completedResult = new FunctionResultContent(completedFunctionCall.CallId, "safe result");
        var pendingApproval = new ToolApprovalRequestContent("approval-1", pendingFunctionCall);
        RootToolApprovalRequestPropagator.Attach(pendingFunctionCall, [pendingApproval]);

        var innerResponse = new ChatResponse([
            new ChatMessage(ChatRole.Assistant, [pendingFunctionCall, completedFunctionCall]),
            new ChatMessage(ChatRole.Tool, [pendingResult, completedResult]),
        ]);

        var innerClient = new Mock<IChatClient>();
        innerClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(innerResponse);

        var client = new ApprovalPropagatingChatClient(innerClient.Object);

        // Act
        var response = await client.GetResponseAsync([new ChatMessage(ChatRole.User, "route this")]);

        // Assert
        var functionResults = response.Messages
            .SelectMany(message => message.Contents)
            .OfType<FunctionResultContent>()
            .ToList();

        Assert.Single(functionResults);
        Assert.Equal(completedFunctionCall.CallId, functionResults[0].CallId);

        var propagatedApproval = Assert.Single(response.Messages
            .SelectMany(message => message.Contents)
            .OfType<ToolApprovalRequestContent>());

        Assert.Equal("approval-1", propagatedApproval.RequestId);
        Assert.Same(pendingFunctionCall, propagatedApproval.ToolCall);
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> GetStreamingUpdatesAsync(
        FunctionCallContent functionCall,
        FunctionResultContent functionResult,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.Yield();
        cancellationToken.ThrowIfCancellationRequested();
        yield return new ChatResponseUpdate(ChatRole.Assistant, [functionCall]);
        yield return new ChatResponseUpdate(ChatRole.Tool, [functionResult]);
    }
}
