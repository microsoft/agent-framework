// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public class NonApprovalRequiredFunctionBypassingChatClientTests
{
    #region GetResponseAsync Tests

    [Fact]
    public async Task GetResponseAsync_NoApprovalContent_PassesThroughUnchangedAsync()
    {
        // Arrange
        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Hello")])));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var response = await RunWithAgentContextAsync(decorator, session);

        // Assert
        Assert.Single(response.Messages);
        Assert.Equal("Hello", response.Messages[0].Text);
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetResponseAsync_AllToolsRequireApproval_PassesThroughUnchangedAsync()
    {
        // Arrange
        var approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "result", "approvalTool"));
        var fcc = new FunctionCallContent("call1", "approvalTool");
        var approval = new ToolApprovalRequestContent("req1", fcc);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, [approval])])));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();
        var options = new ChatOptions { Tools = [approvalTool] };

        // Act
        var response = await RunWithAgentContextAsync(decorator, session, options);

        // Assert — approval request should remain
        Assert.Single(response.Messages);
        var contents = response.Messages[0].Contents;
        Assert.Single(contents);
        Assert.IsType<ToolApprovalRequestContent>(contents[0]);
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetResponseAsync_MixedApproval_RemovesNonApprovalItemsAsync()
    {
        // Arrange
        var normalTool = AIFunctionFactory.Create(() => "result", "normalTool");
        var approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "result", "approvalTool"));

        var fccNormal = new FunctionCallContent("call1", "normalTool");
        var fccApproval = new FunctionCallContent("call2", "approvalTool");
        var approvalNormal = new ToolApprovalRequestContent("req1", fccNormal);
        var approvalRequired = new ToolApprovalRequestContent("req2", fccApproval);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([
                new ChatMessage(ChatRole.Assistant, [approvalNormal, approvalRequired])
            ])));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();
        var options = new ChatOptions { Tools = [normalTool, approvalTool] };

        // Act
        var response = await RunWithAgentContextAsync(decorator, session, options);

        // Assert — only the approval-required item remains in the response
        Assert.Single(response.Messages);
        var contents = response.Messages[0].Contents;
        Assert.Single(contents);
        var remainingApproval = Assert.IsType<ToolApprovalRequestContent>(contents[0]);
        Assert.Equal("req2", remainingApproval.RequestId);
    }

    [Fact]
    public async Task GetResponseAsync_MixedApproval_StoresAutoApprovedInSessionAsync()
    {
        // Arrange
        var normalTool = AIFunctionFactory.Create(() => "result", "normalTool");
        var approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "result", "approvalTool"));

        var fccNormal = new FunctionCallContent("call1", "normalTool");
        var fccApproval = new FunctionCallContent("call2", "approvalTool");
        var approvalNormal = new ToolApprovalRequestContent("req1", fccNormal);
        var approvalRequired = new ToolApprovalRequestContent("req2", fccApproval);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([
                new ChatMessage(ChatRole.Assistant, [approvalNormal, approvalRequired])
            ])));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();
        var options = new ChatOptions { Tools = [normalTool, approvalTool] };

        // Act
        await RunWithAgentContextAsync(decorator, session, options);

        // Assert — the auto-approved item should be stored in the session
        Assert.True(session.StateBag.TryGetValue<List<ToolApprovalRequestContent>>(
            NonApprovalRequiredFunctionBypassingChatClient.StateBagKey, out var stored, AgentJsonUtilities.DefaultOptions));
        Assert.NotNull(stored);
        Assert.Single(stored!);
        Assert.Equal("req1", stored![0].RequestId);
    }

    [Fact]
    public async Task GetResponseAsync_AllNonApproval_RemovesAllApprovalsAndRemovesEmptyMessageAsync()
    {
        // Arrange
        var normalTool = AIFunctionFactory.Create(() => "result", "normalTool");

        var fccNormal = new FunctionCallContent("call1", "normalTool");
        var approvalNormal = new ToolApprovalRequestContent("req1", fccNormal);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([
                new ChatMessage(ChatRole.Assistant, [approvalNormal])
            ])));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();
        var options = new ChatOptions { Tools = [normalTool] };

        // Act
        var response = await RunWithAgentContextAsync(decorator, session, options);

        // Assert — the message should be removed since it's now empty
        Assert.Empty(response.Messages);
    }

    [Fact]
    public async Task GetResponseAsync_NextRequest_InjectsStoredAutoApprovalsAsync()
    {
        // Arrange
        var fccNormal = new FunctionCallContent("call1", "normalTool");
        var storedApproval = new ToolApprovalRequestContent("req1", fccNormal);

        var session = new ChatClientAgentSession();
        session.StateBag.SetValue(
            NonApprovalRequiredFunctionBypassingChatClient.StateBagKey,
            new List<ToolApprovalRequestContent> { storedApproval },
            AgentJsonUtilities.DefaultOptions);

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerClient = CreateMockChatClient((messages, _, _) =>
        {
            capturedMessages = messages.ToList();
            return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Done")]));
        });

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var options = new ChatOptions { Tools = [AIFunctionFactory.Create(() => "result", "normalTool")] };

        // Act
        await RunWithAgentContextAsync(decorator, session, options);

        // Assert — the inner client should receive injected messages
        Assert.NotNull(capturedMessages);
        var messagesList = capturedMessages!.ToList();

        // Original user message + user message with approved responses.
        Assert.Equal(2, messagesList.Count);
        Assert.Equal(ChatRole.User, messagesList[0].Role);

        // User message with the auto-approved ToolApprovalResponseContent
        Assert.Equal(ChatRole.User, messagesList[1].Role);
        var userContent = messagesList[1].Contents.OfType<ToolApprovalResponseContent>().ToList();
        Assert.Single(userContent);
        Assert.Equal("req1", userContent[0].RequestId);
        Assert.True(userContent[0].Approved);
    }

    [Fact]
    public async Task GetResponseAsync_NextRequest_ClearsStoredAfterInjectionAsync()
    {
        // Arrange
        var fccNormal = new FunctionCallContent("call1", "normalTool");
        var storedApproval = new ToolApprovalRequestContent("req1", fccNormal);

        var session = new ChatClientAgentSession();
        session.StateBag.SetValue(
            NonApprovalRequiredFunctionBypassingChatClient.StateBagKey,
            new List<ToolApprovalRequestContent> { storedApproval },
            AgentJsonUtilities.DefaultOptions);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Done")])));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var options = new ChatOptions { Tools = [AIFunctionFactory.Create(() => "result", "normalTool")] };

        // Act
        await RunWithAgentContextAsync(decorator, session, options);

        // Assert — the stored data should be cleared after successful injection
        Assert.False(session.StateBag.TryGetValue<List<ToolApprovalRequestContent>>(
            NonApprovalRequiredFunctionBypassingChatClient.StateBagKey, out _, AgentJsonUtilities.DefaultOptions));
    }

    [Fact]
    public async Task GetResponseAsync_UnknownTool_TreatedAsApprovalRequiredAsync()
    {
        // Arrange — tool is not in ChatOptions.Tools
        var fccUnknown = new FunctionCallContent("call1", "unknownTool");
        var approvalUnknown = new ToolApprovalRequestContent("req1", fccUnknown);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([
                new ChatMessage(ChatRole.Assistant, [approvalUnknown])
            ])));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();
        var options = new ChatOptions { Tools = [] };

        // Act
        var response = await RunWithAgentContextAsync(decorator, session, options);

        // Assert — unknown tool should NOT be auto-approved
        Assert.Single(response.Messages);
        Assert.Single(response.Messages[0].Contents);
        Assert.IsType<ToolApprovalRequestContent>(response.Messages[0].Contents[0]);
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetResponseAsync_StoredRequestToolSetChanged_StillInjectsAsApprovedAsync()
    {
        // Arrange — tool was previously non-approval-required but is now wrapped in ApprovalRequiredAIFunction.
        // The LLM still requires a complete set of responses, so we inject unconditionally.
        var fccTool = new FunctionCallContent("call1", "changingTool");
        var storedApproval = new ToolApprovalRequestContent("req1", fccTool);

        var session = new ChatClientAgentSession();
        session.StateBag.SetValue(
            NonApprovalRequiredFunctionBypassingChatClient.StateBagKey,
            new List<ToolApprovalRequestContent> { storedApproval },
            AgentJsonUtilities.DefaultOptions);

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerClient = CreateMockChatClient((messages, _, _) =>
        {
            capturedMessages = messages.ToList();
            return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Done")]));
        });

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);

        // The tool is now wrapped in ApprovalRequiredAIFunction — but we still inject unconditionally
        var approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "result", "changingTool"));
        var options = new ChatOptions { Tools = [approvalTool] };

        // Act
        await RunWithAgentContextAsync(decorator, session, options);

        // Assert — the stored request should still be injected as approved
        Assert.NotNull(capturedMessages);
        var messagesList = capturedMessages!.ToList();
        Assert.Equal(2, messagesList.Count);
        var userContent = messagesList[1].Contents.OfType<ToolApprovalResponseContent>().ToList();
        Assert.Single(userContent);
        Assert.Equal("req1", userContent[0].RequestId);
        Assert.True(userContent[0].Approved);

        // Session should be cleared
        Assert.False(session.StateBag.TryGetValue<List<ToolApprovalRequestContent>>(
            NonApprovalRequiredFunctionBypassingChatClient.StateBagKey, out _, AgentJsonUtilities.DefaultOptions));
    }

    #endregion

    #region GetStreamingResponseAsync Tests

    [Fact]
    public async Task GetStreamingResponseAsync_NoApprovalContent_PassesThroughUnchangedAsync()
    {
        // Arrange
        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ToAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "Hello")));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates);

        // Assert
        Assert.Single(updates);
        Assert.Equal("Hello", updates[0].Text);
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_MixedApproval_FiltersNonApprovalItemsAsync()
    {
        // Arrange
        var normalTool = AIFunctionFactory.Create(() => "result", "normalTool");
        var approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "result", "approvalTool"));

        var fccNormal = new FunctionCallContent("call1", "normalTool");
        var fccApproval = new FunctionCallContent("call2", "approvalTool");
        var approvalNormal = new ToolApprovalRequestContent("req1", fccNormal);
        var approvalRequired = new ToolApprovalRequestContent("req2", fccApproval);

        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ToAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "text"),
                new ChatResponseUpdate { Contents = [approvalNormal, approvalRequired] }));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();
        var options = new ChatOptions { Tools = [normalTool, approvalTool] };

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates, options);

        // Assert — text update + filtered approval update
        Assert.Equal(2, updates.Count);
        Assert.Equal("text", updates[0].Text);

        // Second update should only have the approval-required item
        var approvalContents = updates[1].Contents.OfType<ToolApprovalRequestContent>().ToList();
        Assert.Single(approvalContents);
        Assert.Equal("req2", approvalContents[0].RequestId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_MixedApproval_StoresAutoApprovedInSessionAsync()
    {
        // Arrange
        var normalTool = AIFunctionFactory.Create(() => "result", "normalTool");
        var approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "result", "approvalTool"));

        var fccNormal = new FunctionCallContent("call1", "normalTool");
        var fccApproval = new FunctionCallContent("call2", "approvalTool");
        var approvalNormal = new ToolApprovalRequestContent("req1", fccNormal);
        var approvalRequired = new ToolApprovalRequestContent("req2", fccApproval);

        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ToAsyncEnumerableAsync(
                new ChatResponseUpdate { Contents = [approvalNormal, approvalRequired] }));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();
        var options = new ChatOptions { Tools = [normalTool, approvalTool] };

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates, options);

        // Assert — the auto-approved item should be stored in the session
        Assert.True(session.StateBag.TryGetValue<List<ToolApprovalRequestContent>>(
            NonApprovalRequiredFunctionBypassingChatClient.StateBagKey, out var stored, AgentJsonUtilities.DefaultOptions));
        Assert.NotNull(stored);
        Assert.Single(stored!);
        Assert.Equal("req1", stored![0].RequestId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_AllNonApproval_SkipsEmptyUpdateAsync()
    {
        // Arrange
        var normalTool = AIFunctionFactory.Create(() => "result", "normalTool");

        var fccNormal = new FunctionCallContent("call1", "normalTool");
        var approvalNormal = new ToolApprovalRequestContent("req1", fccNormal);

        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ToAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "text"),
                new ChatResponseUpdate { Contents = [approvalNormal] }));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();
        var options = new ChatOptions { Tools = [normalTool] };

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates, options);

        // Assert — the approval update should be skipped entirely
        Assert.Single(updates);
        Assert.Equal("text", updates[0].Text);
    }

    #endregion

    #region Error Handling Tests

    [Fact]
    public async Task GetResponseAsync_NoRunContext_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "response")])));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);

        // Act & Assert — calling directly without agent context
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => decorator.GetResponseAsync([new ChatMessage(ChatRole.User, "test")]));
    }

    [Fact]
    public async Task GetResponseAsync_NoSession_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "response")])));

        var decorator = new NonApprovalRequiredFunctionBypassingChatClient(innerClient);

        // Act & Assert — run with null session
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => RunWithAgentContextAsync(decorator, session: null!));
    }

    #endregion

    #region Builder Extension Tests

    [Fact]
    public void UseNonApprovalRequiredFunctionBypassing_AddsDecoratorToPipeline()
    {
        // Arrange
        var innerClient = new Mock<IChatClient>().Object;

        // Act
        var pipeline = innerClient.AsBuilder()
            .UseNonApprovalRequiredFunctionBypassing()
            .Build();

        // Assert
        Assert.NotNull(pipeline.GetService<NonApprovalRequiredFunctionBypassingChatClient>());
    }

    [Fact]
    public void WithDefaultAgentMiddleware_EnableNonApprovalRequiredFunctionBypassing_InjectsDecorator()
    {
        // Arrange
        var innerClient = new Mock<IChatClient>().Object;
        var options = new ChatClientAgentOptions { EnableNonApprovalRequiredFunctionBypassing = true };

        // Act
        var pipeline = innerClient.WithDefaultAgentMiddleware(options);

        // Assert
        Assert.NotNull(pipeline.GetService<NonApprovalRequiredFunctionBypassingChatClient>());
    }

    [Fact]
    public void WithDefaultAgentMiddleware_EnableNonApprovalRequiredFunctionBypassingFalse_DoesNotInjectDecorator()
    {
        // Arrange
        var innerClient = new Mock<IChatClient>().Object;
        var options = new ChatClientAgentOptions { EnableNonApprovalRequiredFunctionBypassing = false };

        // Act
        var pipeline = innerClient.WithDefaultAgentMiddleware(options);

        // Assert
        Assert.Null(pipeline.GetService<NonApprovalRequiredFunctionBypassingChatClient>());
    }

    #endregion

    #region Helpers

    private static async Task<ChatResponse> RunWithAgentContextAsync(
        NonApprovalRequiredFunctionBypassingChatClient decorator,
        AgentSession? session,
        ChatOptions? options = null)
    {
        ChatResponse? capturedResponse = null;

        var agent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, agentSession, agentOptions, ct) =>
            {
                capturedResponse = await decorator.GetResponseAsync(messages, options, ct);
                return new AgentResponse(capturedResponse);
            }
        };

        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], session);
        return capturedResponse!;
    }

    private static Task<ChatResponse> RunWithAgentContextAsync(
        NonApprovalRequiredFunctionBypassingChatClient decorator,
        AgentSession session)
        => RunWithAgentContextAsync(decorator, session, options: null);

    private static async Task RunStreamingWithAgentContextAsync(
        NonApprovalRequiredFunctionBypassingChatClient decorator,
        AgentSession session,
        List<ChatResponseUpdate> updates,
        ChatOptions? options = null)
    {
        var agent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, agentSession, agentOptions, ct) =>
            {
                await foreach (var update in decorator.GetStreamingResponseAsync(messages, options, ct))
                {
                    updates.Add(update);
                }

                return new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]);
            }
        };

        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], session);
    }

    private static IChatClient CreateMockChatClient(
        Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, Task<ChatResponse>> onGetResponse)
    {
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> m, ChatOptions? o, CancellationToken ct) => onGetResponse(m, o, ct));
        return mock.Object;
    }

    private static IChatClient CreateMockStreamingChatClient(
        Func<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken, IAsyncEnumerable<ChatResponseUpdate>> onGetStreamingResponse)
    {
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> m, ChatOptions? o, CancellationToken ct) => onGetStreamingResponse(m, o, ct));
        return mock.Object;
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> ToAsyncEnumerableAsync(params ChatResponseUpdate[] updates)
    {
        foreach (var update in updates)
        {
            yield return update;
        }

        await Task.CompletedTask;
    }

    #endregion
}
