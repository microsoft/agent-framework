// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public class InvocableFunctionBypassingChatClientTests
{
    private const string BackendToolName = "backendTool";
    private const string FrontendToolName = "frontendTool";

    private static AIFunction CreateBackendTool()
        => AIFunctionFactory.Create(() => "result", BackendToolName);

    private static AIFunctionDeclaration CreateFrontendTool()
        => AIFunctionFactory.CreateDeclaration(FrontendToolName, "Frontend tool", AIFunctionFactory.Create(() => true).JsonSchema);

    private static ChatOptions CreateMixedToolOptions()
        => new() { Tools = [CreateBackendTool(), CreateFrontendTool()] };

    #region GetResponseAsync Tests

    [Fact]
    public async Task GetResponseAsync_NoFunctionCalls_PassesThroughUnchangedAsync()
    {
        // Arrange
        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Hello")])));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var response = await RunWithAgentContextAsync(decorator, session, CreateMixedToolOptions());

        // Assert
        Assert.Single(response.Messages);
        Assert.Equal("Hello", response.Messages[0].Text);
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetResponseAsync_OnlyInvocableCalls_PassesThroughUnchangedAsync()
    {
        // Arrange — no declaration-only sibling, so nothing should be bypassed.
        var backendCall = new FunctionCallContent("call1", BackendToolName);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, [backendCall])])));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var response = await RunWithAgentContextAsync(decorator, session, CreateMixedToolOptions());

        // Assert
        var contents = Assert.Single(response.Messages).Contents;
        var fcc = Assert.IsType<FunctionCallContent>(Assert.Single(contents));
        Assert.Equal(BackendToolName, fcc.Name);
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetResponseAsync_OnlyDeclarationOnlyCalls_PassesThroughUnchangedAsync()
    {
        // Arrange — the normal frontend-tools flow with no backend sibling.
        var frontendCall = new FunctionCallContent("call1", FrontendToolName);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, [frontendCall])])));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var response = await RunWithAgentContextAsync(decorator, session, CreateMixedToolOptions());

        // Assert
        var contents = Assert.Single(response.Messages).Contents;
        var fcc = Assert.IsType<FunctionCallContent>(Assert.Single(contents));
        Assert.Equal(FrontendToolName, fcc.Name);
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetResponseAsync_MixedCalls_RemovesInvocableCallFromResponseAsync()
    {
        // Arrange
        var backendCall = new FunctionCallContent("call1", BackendToolName);
        var frontendCall = new FunctionCallContent("call2", FrontendToolName);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([
                new ChatMessage(ChatRole.Assistant, [backendCall, frontendCall])
            ])));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var response = await RunWithAgentContextAsync(decorator, session, CreateMixedToolOptions());

        // Assert — only the declaration-only call remains in the response.
        var contents = Assert.Single(response.Messages).Contents;
        var remaining = Assert.IsType<FunctionCallContent>(Assert.Single(contents));
        Assert.Equal(FrontendToolName, remaining.Name);
    }

    [Fact]
    public async Task GetResponseAsync_MixedCalls_StoresInvocableCallInSessionAsync()
    {
        // Arrange
        var backendCall = new FunctionCallContent("call1", BackendToolName);
        var frontendCall = new FunctionCallContent("call2", FrontendToolName);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([
                new ChatMessage(ChatRole.Assistant, [backendCall, frontendCall])
            ])));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        await RunWithAgentContextAsync(decorator, session, CreateMixedToolOptions());

        // Assert — the backend call is stored in the session for the next turn.
        Assert.True(session.StateBag.TryGetValue<List<FunctionCallContent>>(
            InvocableFunctionBypassingChatClient.StateBagKey, out var stored, AgentJsonUtilities.DefaultOptions));
        Assert.NotNull(stored);
        var storedCall = Assert.Single(stored!);
        Assert.Equal("call1", storedCall.CallId);
        Assert.Equal(BackendToolName, storedCall.Name);
    }

    [Fact]
    public async Task GetResponseAsync_MixedCallsInSeparateMessages_RemovesEmptyAssistantMessageAsync()
    {
        // Arrange — backend and frontend calls in separate assistant messages.
        var backendCall = new FunctionCallContent("call1", BackendToolName);
        var frontendCall = new FunctionCallContent("call2", FrontendToolName);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([
                new ChatMessage(ChatRole.Assistant, [backendCall]),
                new ChatMessage(ChatRole.Assistant, [frontendCall])
            ])));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var response = await RunWithAgentContextAsync(decorator, session, CreateMixedToolOptions());

        // Assert — the message that only held the backend call is removed.
        var message = Assert.Single(response.Messages);
        var remaining = Assert.IsType<FunctionCallContent>(Assert.Single(message.Contents));
        Assert.Equal(FrontendToolName, remaining.Name);
    }

    [Fact]
    public async Task GetResponseAsync_NextRequest_InjectsStoredCallAsApprovedResponseAsync()
    {
        // Arrange — a full chat history round-trip: the backend call was stored on the previous turn, and the
        // history now only contains the resolved frontend call (the backend call was stripped, not persisted).
        var storedBackendCall = new FunctionCallContent("call1", BackendToolName);

        var session = new ChatClientAgentSession();
        session.StateBag.SetValue(
            InvocableFunctionBypassingChatClient.StateBagKey,
            new List<FunctionCallContent> { storedBackendCall },
            AgentJsonUtilities.DefaultOptions);

        var frontendCall = new FunctionCallContent("call2", FrontendToolName);
        var history = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello"),
            new(ChatRole.Assistant, [frontendCall]),
            new(ChatRole.Tool, [new FunctionResultContent("call2", "Amsterdam")]),
        };

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerClient = CreateMockChatClient((messages, _, _) =>
        {
            capturedMessages = messages.ToList();
            return Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Done")]));
        });

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);

        // Act
        await RunWithAgentContextAsync(decorator, session, CreateMixedToolOptions(), history);

        // Assert — exactly one approved ToolApprovalResponseContent for the backend call is injected, with no
        // matching approval request and no duplicate backend FunctionCallContent in the incoming history.
        Assert.NotNull(capturedMessages);
        var messagesList = capturedMessages!.ToList();

        var approvalResponses = messagesList
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalResponseContent>()
            .ToList();
        var approvalResponse = Assert.Single(approvalResponses);
        Assert.True(approvalResponse.Approved);
        Assert.Equal($"ifbcc_{approvalResponse.ToolCall.CallId}", approvalResponse.RequestId);
        var approvedCall = Assert.IsType<FunctionCallContent>(approvalResponse.ToolCall);
        Assert.Equal("call1", approvedCall.CallId);
        Assert.Equal(BackendToolName, approvedCall.Name);

        Assert.DoesNotContain(messagesList.SelectMany(m => m.Contents), c => c is ToolApprovalRequestContent);
        Assert.DoesNotContain(
            messagesList.SelectMany(m => m.Contents).OfType<FunctionCallContent>(),
            c => c.Name == BackendToolName);
    }

    [Fact]
    public async Task GetResponseAsync_NextRequest_ClearsStoredAfterInjectionAsync()
    {
        // Arrange
        var storedBackendCall = new FunctionCallContent("call1", BackendToolName);

        var session = new ChatClientAgentSession();
        session.StateBag.SetValue(
            InvocableFunctionBypassingChatClient.StateBagKey,
            new List<FunctionCallContent> { storedBackendCall },
            AgentJsonUtilities.DefaultOptions);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, "Done")])));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);

        // Act
        await RunWithAgentContextAsync(decorator, session, CreateMixedToolOptions());

        // Assert — the stored data is cleared after successful injection.
        Assert.False(session.StateBag.TryGetValue<List<FunctionCallContent>>(
            InvocableFunctionBypassingChatClient.StateBagKey, out _, AgentJsonUtilities.DefaultOptions));
    }

    #endregion

    #region GetStreamingResponseAsync Tests

    [Fact]
    public async Task GetStreamingResponseAsync_NoFunctionCalls_PassesThroughUnchangedAsync()
    {
        // Arrange
        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ToAsyncEnumerableAsync(new ChatResponseUpdate(ChatRole.Assistant, "Hello")));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates, CreateMixedToolOptions());

        // Assert
        Assert.Equal("Hello", updates.ToChatResponse().Messages.Single().Text);
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_MixedCalls_RemovesAndStoresInvocableCallAsync()
    {
        // Arrange
        var backendCall = new FunctionCallContent("call1", BackendToolName);
        var frontendCall = new FunctionCallContent("call2", FrontendToolName);

        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ToAsyncEnumerableAsync(
                new ChatResponseUpdate { Role = ChatRole.Assistant, Contents = [backendCall] },
                new ChatResponseUpdate { Role = ChatRole.Assistant, Contents = [frontendCall] }));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates, CreateMixedToolOptions());

        // Assert — only the frontend call is surfaced, and the backend call is stored.
        var surfacedCalls = updates.ToChatResponse().Messages
            .SelectMany(m => m.Contents)
            .OfType<FunctionCallContent>()
            .ToList();
        var surfaced = Assert.Single(surfacedCalls);
        Assert.Equal(FrontendToolName, surfaced.Name);

        Assert.True(session.StateBag.TryGetValue<List<FunctionCallContent>>(
            InvocableFunctionBypassingChatClient.StateBagKey, out var stored, AgentJsonUtilities.DefaultOptions));
        var storedCall = Assert.Single(stored!);
        Assert.Equal(BackendToolName, storedCall.Name);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_NextRequest_InjectsStoredCallAsApprovedResponseAsync()
    {
        // Arrange
        var storedBackendCall = new FunctionCallContent("call1", BackendToolName);

        var session = new ChatClientAgentSession();
        session.StateBag.SetValue(
            InvocableFunctionBypassingChatClient.StateBagKey,
            new List<FunctionCallContent> { storedBackendCall },
            AgentJsonUtilities.DefaultOptions);

        IEnumerable<ChatMessage>? capturedMessages = null;
        var innerClient = CreateMockStreamingChatClient((messages, _, _) =>
        {
            capturedMessages = messages.ToList();
            return ToAsyncEnumerableAsync(new ChatResponseUpdate(ChatRole.Assistant, "Done"));
        });

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates, CreateMixedToolOptions());

        // Assert
        Assert.NotNull(capturedMessages);
        var approvalResponses = capturedMessages!
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalResponseContent>()
            .ToList();
        var approvalResponse = Assert.Single(approvalResponses);
        Assert.True(approvalResponse.Approved);
        Assert.Equal("call1", Assert.IsType<FunctionCallContent>(approvalResponse.ToolCall).CallId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_StreamsPreFunctionCallUpdatesLiveAsync()
    {
        // Arrange — a text update precedes the function-call updates; it must pass through untouched and
        // ahead of the buffered call tail.
        var backendCall = new FunctionCallContent("call1", BackendToolName);
        var frontendCall = new FunctionCallContent("call2", FrontendToolName);

        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ToAsyncEnumerableAsync(
                new ChatResponseUpdate(ChatRole.Assistant, "Thinking..."),
                new ChatResponseUpdate { Role = ChatRole.Assistant, Contents = [backendCall] },
                new ChatResponseUpdate { Role = ChatRole.Assistant, Contents = [frontendCall] }));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates, CreateMixedToolOptions());

        // Assert — the leading text update is emitted first and unchanged; only the frontend call surfaces.
        Assert.Equal("Thinking...", updates[0].Text);
        Assert.DoesNotContain(updates[0].Contents, c => c is FunctionCallContent);

        var surfacedCalls = updates.SelectMany(u => u.Contents).OfType<FunctionCallContent>().ToList();
        var surfaced = Assert.Single(surfacedCalls);
        Assert.Equal(FrontendToolName, surfaced.Name);

        Assert.True(session.StateBag.TryGetValue<List<FunctionCallContent>>(
            InvocableFunctionBypassingChatClient.StateBagKey, out var stored, AgentJsonUtilities.DefaultOptions));
        Assert.Equal(BackendToolName, Assert.Single(stored!).Name);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_InvocableOnly_PassesThroughWithoutBypassingAsync()
    {
        // Arrange — two invocable calls and no declaration-only call: the both-kinds gate must not trigger.
        var firstCall = new FunctionCallContent("call1", BackendToolName);
        var secondCall = new FunctionCallContent("call2", BackendToolName);

        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ToAsyncEnumerableAsync(
                new ChatResponseUpdate { Role = ChatRole.Assistant, Contents = [firstCall] },
                new ChatResponseUpdate { Role = ChatRole.Assistant, Contents = [secondCall] }));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates, CreateMixedToolOptions());

        // Assert — both invocable calls are surfaced and nothing is stored.
        var surfacedCalls = updates.SelectMany(u => u.Contents).OfType<FunctionCallContent>().ToList();
        Assert.Equal(2, surfacedCalls.Count);
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_ReleasesBufferOnceCallsAreExecutedAsync()
    {
        // Arrange — mimic FunctionInvokingChatClient executing a backend call mid-stream: it yields the call,
        // flips InformationalOnly in place once invoked, then streams the final answer. The decorator must
        // release the buffered call and resume live streaming rather than withholding it to end-of-stream.
        var backendCall = new FunctionCallContent("call1", BackendToolName);
        var log = new List<string>();

        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ExecuteCallMidStreamAsync(backendCall, log));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(
            decorator, session, updates, CreateMixedToolOptions(), u => log.Add($"consumed:{u.Contents.Count}"));

        // Assert — the buffered call is released before the stream ends, so the caller receives updates while
        // the response is still being produced rather than in one batch at the end.
        Assert.True(
            log.IndexOf("produced:answer") > log.FindIndex(entry => entry.StartsWith("consumed:", StringComparison.Ordinal)),
            $"Expected consumption to interleave with production, but got: {string.Join(", ", log)}");

        // Every update is still surfaced, in order, and nothing is stored for bypassing.
        Assert.Collection(
            updates,
            u => Assert.Same(backendCall, Assert.Single(u.Contents)),
            u => Assert.IsType<FunctionResultContent>(Assert.Single(u.Contents)),
            u => Assert.Equal("The answer", u.Text));
        Assert.Equal(0, session.StateBag.Count);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_EmptiedUpdateRetainsMetadataAsync()
    {
        // Arrange — the update carrying the bypassed backend call carries nothing else, so stripping empties
        // it. It still holds stream metadata (conversation/response ids) that the caller needs. Deliberately
        // no FinishReason, since that alone is not what makes an emptied update worth keeping.
        var backendCall = new FunctionCallContent("call1", BackendToolName);
        var frontendCall = new FunctionCallContent("call2", FrontendToolName);

        var innerClient = CreateMockStreamingChatClient((_, _, _) =>
            ToAsyncEnumerableAsync(
                new ChatResponseUpdate { Role = ChatRole.Assistant, Contents = [frontendCall] },
                new ChatResponseUpdate
                {
                    Role = ChatRole.Assistant,
                    Contents = [backendCall],
                    ConversationId = "conv-1",
                    ResponseId = "resp-1",
                }));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);
        var session = new ChatClientAgentSession();

        // Act
        var updates = new List<ChatResponseUpdate>();
        await RunStreamingWithAgentContextAsync(decorator, session, updates, CreateMixedToolOptions());

        // Assert — the backend call is stripped, but the emptied update is still surfaced with its metadata.
        Assert.DoesNotContain(
            updates.SelectMany(u => u.Contents).OfType<FunctionCallContent>(),
            c => c.Name == BackendToolName);

        var emptied = Assert.Single(updates, u => u.Contents.Count == 0);
        Assert.Equal("conv-1", emptied.ConversationId);
        Assert.Equal("resp-1", emptied.ResponseId);
    }

    [Fact]
    public async Task GetResponseAsync_InnerClientThrows_DoesNotRestorePendingCallsAsync()
    {
        // Arrange - a call bypassed on a previous turn is pending, and the next request fails.
        var storedBackendCall = new FunctionCallContent("call1", BackendToolName);

        var session = new ChatClientAgentSession();
        session.StateBag.SetValue(
            InvocableFunctionBypassingChatClient.StateBagKey,
            new List<FunctionCallContent> { storedBackendCall },
            AgentJsonUtilities.DefaultOptions);

        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromException<ChatResponse>(new InvalidOperationException("transient")));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => RunWithAgentContextAsync(decorator, session, CreateMixedToolOptions()));

        // Assert - pending calls are consumed exactly once and are deliberately not put back. The batch is
        // injected as a unit and FunctionInvokingChatClient invokes approved responses before the service
        // call, so part of it has usually already run by the time a failure surfaces; re-injecting would
        // invoke those functions again while still leaving the batch missing the unrecoverable results.
        Assert.False(session.StateBag.TryGetValue<List<FunctionCallContent>>(
            InvocableFunctionBypassingChatClient.StateBagKey, out _, AgentJsonUtilities.DefaultOptions));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_EnumerationAbandonedEarly_DoesNotRestorePendingCallsAsync()
    {
        // Arrange - a call bypassed on a previous turn is pending and the consumer stops enumerating early.
        var storedBackendCall = new FunctionCallContent("call1", BackendToolName);

        var session = new ChatClientAgentSession();
        session.StateBag.SetValue(
            InvocableFunctionBypassingChatClient.StateBagKey,
            new List<FunctionCallContent> { storedBackendCall },
            AgentJsonUtilities.DefaultOptions);

        var innerClient = CreateMockStreamingChatClient((_, _, _) => ToAsyncEnumerableAsync(
            new ChatResponseUpdate(ChatRole.Assistant, "first"),
            new ChatResponseUpdate(ChatRole.Assistant, "second")));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);

        // Act
        var consumed = await ConsumeFirstUpdateThenAbandonAsync(decorator, session);

        // Assert - as on the failure path, the abandoned turn drops the pending calls rather than risking a
        // second invocation of functions the inner pipeline may already have run.
        Assert.Single(consumed);
        Assert.False(session.StateBag.TryGetValue<List<FunctionCallContent>>(
            InvocableFunctionBypassingChatClient.StateBagKey, out _, AgentJsonUtilities.DefaultOptions));
    }

    #endregion

    #region No-Context Pass-Through Tests

    [Fact]
    public async Task GetResponseAsync_NoRunContext_PassesThroughWithoutBypassingAsync()
    {
        // Arrange
        var backendCall = new FunctionCallContent("call1", BackendToolName);
        var frontendCall = new FunctionCallContent("call2", FrontendToolName);
        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, [backendCall, frontendCall])])));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);

        // Act — calling directly without agent context; the decorator should no-op and pass through.
        var response = await decorator.GetResponseAsync([new ChatMessage(ChatRole.User, "test")], CreateMixedToolOptions());

        // Assert — both calls are surfaced to the caller unchanged (not bypassed).
        var calls = Assert.Single(response.Messages).Contents.OfType<FunctionCallContent>().ToList();
        Assert.Equal(2, calls.Count);
    }

    [Fact]
    public async Task GetResponseAsync_NoSession_PassesThroughWithoutBypassingAsync()
    {
        // Arrange
        var backendCall = new FunctionCallContent("call1", BackendToolName);
        var frontendCall = new FunctionCallContent("call2", FrontendToolName);
        var innerClient = CreateMockChatClient((_, _, _) =>
            Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, [backendCall, frontendCall])])));

        var decorator = new InvocableFunctionBypassingChatClient(innerClient);

        // Act — run with an agent context but a null session; the decorator should no-op and pass through.
        var response = await RunWithAgentContextAsync(decorator, session: null!, CreateMixedToolOptions());

        // Assert — both calls are surfaced to the caller unchanged (not bypassed).
        var calls = Assert.Single(response.Messages).Contents.OfType<FunctionCallContent>().ToList();
        Assert.Equal(2, calls.Count);
    }

    #endregion

    #region Builder Extension Tests

    [Fact]
    public void UseInvocableFunctionBypassing_AddsDecoratorToPipeline()
    {
        // Arrange
        var innerClient = new Mock<IChatClient>().Object;

        // Act
        var pipeline = innerClient.AsBuilder()
            .UseInvocableFunctionBypassing()
            .Build();

        // Assert
        Assert.NotNull(pipeline.GetService<InvocableFunctionBypassingChatClient>());
    }

    [Fact]
    public void WithDefaultAgentMiddleware_EnableInvocableFunctionBypassing_InjectsDecorator()
    {
        // Arrange
        var innerClient = new Mock<IChatClient>().Object;
        var options = new ChatClientAgentOptions { EnableInvocableFunctionBypassing = true };

        // Act
        var pipeline = innerClient.WithDefaultAgentMiddleware(options);

        // Assert
        Assert.NotNull(pipeline.GetService<InvocableFunctionBypassingChatClient>());
    }

    [Fact]
    public void WithDefaultAgentMiddleware_ByDefault_DoesNotInjectDecorator()
    {
        // Arrange
        var innerClient = new Mock<IChatClient>().Object;
        var options = new ChatClientAgentOptions();

        // Act
        var pipeline = innerClient.WithDefaultAgentMiddleware(options);

        // Assert
        Assert.Null(pipeline.GetService<InvocableFunctionBypassingChatClient>());
    }

    [Fact]
    public void WithDefaultAgentMiddleware_EnableInvocableFunctionBypassing_PlacesDecoratorBelowApprovalBindingAndAboveFunctionInvocation()
    {
        // Arrange — the decorator emits synthetic approval responses that have no recorded approval request,
        // so ApprovalResponseBindingChatClient (which drops unbound responses) must sit above it, and
        // FunctionInvokingChatClient must sit below it so that those responses reach the invocation loop.
        var innerClient = new Mock<IChatClient>().Object;
        var options = new ChatClientAgentOptions { EnableInvocableFunctionBypassing = true };

        // Act — GetService matches on the current instance and otherwise forwards down the chain, so relative
        // order is observable by walking from one decorator and looking for the others below it.
        var pipeline = innerClient.WithDefaultAgentMiddleware(options);

        // Assert
        var binding = pipeline.GetService<ApprovalResponseBindingChatClient>();
        Assert.NotNull(binding);

        var bypassing = binding.GetService<InvocableFunctionBypassingChatClient>();
        Assert.NotNull(bypassing);

        Assert.Null(bypassing.GetService<ApprovalResponseBindingChatClient>());
        Assert.NotNull(bypassing.GetService<FunctionInvokingChatClient>());
    }

    #endregion

    #region Helpers

    private static async Task<ChatResponse> RunWithAgentContextAsync(
        InvocableFunctionBypassingChatClient decorator,
        AgentSession? session,
        ChatOptions? options = null,
        IList<ChatMessage>? inputMessages = null)
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

        await agent.RunAsync(inputMessages ?? [new ChatMessage(ChatRole.User, "Hello")], session);
        return capturedResponse!;
    }

    private static async Task RunStreamingWithAgentContextAsync(
        InvocableFunctionBypassingChatClient decorator,
        AgentSession session,
        List<ChatResponseUpdate> updates,
        ChatOptions? options = null,
        Action<ChatResponseUpdate>? onUpdate = null)
    {
        var agent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, agentSession, agentOptions, ct) =>
            {
                await foreach (var update in decorator.GetStreamingResponseAsync(messages, options, ct))
                {
                    updates.Add(update);
                    onUpdate?.Invoke(update);
                }

                return new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]);
            }
        };

        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], session);
    }

    /// <summary>
    /// Consumes a single update from the decorator and then abandons the enumeration, which resumes the
    /// iterator at the yield return as though it had returned.
    /// </summary>
    private static async Task<List<ChatResponseUpdate>> ConsumeFirstUpdateThenAbandonAsync(
        InvocableFunctionBypassingChatClient decorator,
        AgentSession session)
    {
        var consumed = new List<ChatResponseUpdate>();

        var agent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, agentSession, agentOptions, ct) =>
            {
                await foreach (var update in decorator.GetStreamingResponseAsync(messages, CreateMixedToolOptions(), ct))
                {
                    consumed.Add(update);
                    break;
                }

                return new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]);
            }
        };

        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], session);

        return consumed;
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

    /// <summary>
    /// Mimics FunctionInvokingChatClient executing a call mid-stream: the call is yielded while still
    /// pending, then flipped to InformationalOnly in place (as FICC does) before the result and the final
    /// answer are streamed. Each yield is recorded in <paramref name="log"/> so that a test can assert the
    /// decorator interleaves consumption with production rather than withholding to end-of-stream.
    /// </summary>
    private static async IAsyncEnumerable<ChatResponseUpdate> ExecuteCallMidStreamAsync(
        FunctionCallContent call,
        List<string> log)
    {
        log.Add("produced:call");
        yield return new ChatResponseUpdate { Role = ChatRole.Assistant, Contents = [call] };

        call.InformationalOnly = true;

        log.Add("produced:result");
        yield return new ChatResponseUpdate { Role = ChatRole.Tool, Contents = [new FunctionResultContent(call.CallId, "42")] };

        log.Add("produced:answer");
        yield return new ChatResponseUpdate(ChatRole.Assistant, "The answer");

        await Task.CompletedTask;
    }

    #endregion
}
