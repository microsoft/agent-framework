// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Tests covering the per-session identity context that <see cref="AgentFrameworkResponseHandler"/>
/// applies via the registered <see cref="HostedSessionIsolationKeyProvider"/>.
/// </summary>
public class HostedSessionIdentityContextTests
{
    private const string TestUserId = "user-isolation-key-1";
    private const string TestChatId = "chat-isolation-key-1";

    [Fact]
    public void HostedSessionContext_RejectsNullOrWhitespaceKeys()
    {
        // Assert
        Assert.Throws<ArgumentNullException>(() => new HostedSessionContext(null!, TestChatId));
        Assert.Throws<ArgumentNullException>(() => new HostedSessionContext(TestUserId, null!));
        Assert.Throws<ArgumentException>(() => new HostedSessionContext(string.Empty, TestChatId));
        Assert.Throws<ArgumentException>(() => new HostedSessionContext(TestUserId, "   "));
    }

    [Fact]
    public async Task PlatformProvider_MapsIsolationContextValuesAsync()
    {
        // Arrange
        var provider = new PlatformHostedSessionIsolationKeyProvider();
        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.Isolation).Returns(new IsolationContext(TestUserId, TestChatId));
        var request = new CreateResponse { Model = "test" };

        // Act
        var result = await provider.GetKeysAsync(mockContext.Object, request, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(TestUserId, result.UserId);
        Assert.Equal(TestChatId, result.ChatId);
    }

    [Fact]
    public async Task PlatformProvider_ReturnsNullWhenIsolationKeysAreEmptyAsync()
    {
        // Arrange
        var provider = new PlatformHostedSessionIsolationKeyProvider();
        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        // CallBase delegates to ResponseContext.Isolation default which is IsolationContext.Empty.
        var request = new CreateResponse { Model = "test" };

        // Act
        var result = await provider.GetKeysAsync(mockContext.Object, request, CancellationToken.None);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task Handler_FreshSession_AppliesContextFromCustomProviderAsync()
    {
        // Arrange
        var capturingAgent = new HostedContextCapturingAgent();
        var fakeProvider = new FakeHostedSessionIsolationKeyProvider("alice", "chat-A");
        var handler = BuildHandler(capturingAgent, fakeProvider);

        var (request, mockContext) = BuildFreshRequest();

        // Act
        await DrainAsync(handler.CreateAsync(request, mockContext.Object, CancellationToken.None));

        // Assert
        Assert.NotNull(capturingAgent.LastSession);
        var ctx = capturingAgent.LastSession.GetHostedContext();
        Assert.NotNull(ctx);
        Assert.Equal("alice", ctx.UserId);
        Assert.Equal("chat-A", ctx.ChatId);
    }

    [Fact]
    public async Task Handler_NullKeysFromProvider_ThrowsInvalidOperationAsync()
    {
        // Arrange
        var capturingAgent = new HostedContextCapturingAgent();
        var fakeProvider = new FakeHostedSessionIsolationKeyProvider(userId: null, chatId: null);
        var handler = BuildHandler(capturingAgent, fakeProvider);

        var (request, mockContext) = BuildFreshRequest();

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => DrainAsync(handler.CreateAsync(request, mockContext.Object, CancellationToken.None)));
        Assert.Contains(nameof(HostedSessionIsolationKeyProvider), ex.Message);
    }

    [Fact]
    public async Task Handler_ResumeSession_MatchingKeys_PassesAsync()
    {
        // Arrange
        var capturingAgent = new HostedContextCapturingAgent();
        var fakeProvider = new FakeHostedSessionIsolationKeyProvider("alice", "chat-A");
        var sessionStore = new InMemoryAgentSessionStore();
        var handler = BuildHandler(capturingAgent, fakeProvider, sessionStore);

        // Step 1: drive a fresh request to populate the session store with a tagged session.
        var (freshRequest, freshContext) = BuildFreshRequest();
        await DrainAsync(handler.CreateAsync(freshRequest, freshContext.Object, CancellationToken.None));
        Assert.NotNull(capturingAgent.LastSession);

        // Step 2: persist the session under a known conversation id (mimics what the handler does
        // when it has a conversation id; here we plant it directly so we can drive a resume request).
        const string ConversationId = "resume-chat-id";
        await sessionStore.SaveSessionAsync(capturingAgent, ConversationId, capturingAgent.LastSession, CancellationToken.None);

        // Step 3: drive a resume request with the same isolation keys.
        var (resumeRequest, resumeContext) = BuildResumeRequest(ConversationId);
        capturingAgent.LastSession = null;

        // Act
        await DrainAsync(handler.CreateAsync(resumeRequest, resumeContext.Object, CancellationToken.None));

        // Assert
        Assert.NotNull(capturingAgent.LastSession);
        var ctx = capturingAgent.LastSession.GetHostedContext();
        Assert.NotNull(ctx);
        Assert.Equal("alice", ctx.UserId);
    }

    [Fact]
    public async Task Handler_ResumeSession_MismatchedUserId_Returns403Async()
    {
        // Arrange
        var capturingAgent = new HostedContextCapturingAgent();
        var aliceProvider = new FakeHostedSessionIsolationKeyProvider("alice", "chat-A");
        var sessionStore = new InMemoryAgentSessionStore();
        var aliceHandler = BuildHandler(capturingAgent, aliceProvider, sessionStore);

        var (freshRequest, freshContext) = BuildFreshRequest();
        await DrainAsync(aliceHandler.CreateAsync(freshRequest, freshContext.Object, CancellationToken.None));
        const string ConversationId = "resume-chat-id";
        await sessionStore.SaveSessionAsync(capturingAgent, ConversationId, capturingAgent.LastSession!, CancellationToken.None);

        // Bob attempts to resume Alice's conversation.
        var bobProvider = new FakeHostedSessionIsolationKeyProvider("bob", "chat-A");
        var bobHandler = BuildHandler(capturingAgent, bobProvider, sessionStore);
        var (resumeRequest, resumeContext) = BuildResumeRequest(ConversationId);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<ResponsesApiException>(() => DrainAsync(bobHandler.CreateAsync(resumeRequest, resumeContext.Object, CancellationToken.None)));
        Assert.Equal(403, ex.StatusCode);
        Assert.Equal("Hosted session identity context mismatch", ex.Error.Message);
    }

    [Fact]
    public async Task Handler_ResumeSession_MismatchedChatId_Returns403Async()
    {
        // Arrange
        var capturingAgent = new HostedContextCapturingAgent();
        var chatAProvider = new FakeHostedSessionIsolationKeyProvider("alice", "chat-A");
        var sessionStore = new InMemoryAgentSessionStore();
        var chatAHandler = BuildHandler(capturingAgent, chatAProvider, sessionStore);

        var (freshRequest, freshContext) = BuildFreshRequest();
        await DrainAsync(chatAHandler.CreateAsync(freshRequest, freshContext.Object, CancellationToken.None));
        const string ConversationId = "resume-chat-id";
        await sessionStore.SaveSessionAsync(capturingAgent, ConversationId, capturingAgent.LastSession!, CancellationToken.None);

        var chatBProvider = new FakeHostedSessionIsolationKeyProvider("alice", "chat-B");
        var chatBHandler = BuildHandler(capturingAgent, chatBProvider, sessionStore);
        var (resumeRequest, resumeContext) = BuildResumeRequest(ConversationId);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<ResponsesApiException>(() => DrainAsync(chatBHandler.CreateAsync(resumeRequest, resumeContext.Object, CancellationToken.None)));
        Assert.Equal(403, ex.StatusCode);
    }

    [Fact]
    public async Task Handler_ResumeSession_WithoutPriorContext_StampsAsFreshAsync()
    {
        // Arrange: store an untagged session. This case arises in production when the platform
        // (or the caller) creates a Foundry conversation_id externally, and the very first
        // hosted-agent request for that conversation hits the handler before any context is
        // stamped. Such a session is treated as "fresh" rather than "resume" because there is
        // no prior identity to defend; the stamp made now is what future resumes will validate.
        var capturingAgent = new HostedContextCapturingAgent();
        var sessionStore = new InMemoryAgentSessionStore();
        const string ConversationId = "untagged-chat-id";
        var untagged = await capturingAgent.CreateSessionAsync(CancellationToken.None);
        await sessionStore.SaveSessionAsync(capturingAgent, ConversationId, untagged, CancellationToken.None);

        var fakeProvider = new FakeHostedSessionIsolationKeyProvider("alice", "chat-A");
        var handler = BuildHandler(capturingAgent, fakeProvider, sessionStore);
        var (resumeRequest, resumeContext) = BuildResumeRequest(ConversationId);

        // Act
        await DrainAsync(handler.CreateAsync(resumeRequest, resumeContext.Object, CancellationToken.None));

        // Assert
        Assert.NotNull(capturingAgent.LastSession);
        var ctx = capturingAgent.LastSession.GetHostedContext();
        Assert.NotNull(ctx);
        Assert.Equal("alice", ctx.UserId);
        Assert.Equal("chat-A", ctx.ChatId);
    }

    [Fact]
    public void GetHostedContext_ReturnsNullWhenAbsent()
    {
        // Arrange
        var session = new HostedContextCapturingSession();

        // Act
        var ctx = session.GetHostedContext();

        // Assert
        Assert.Null(ctx);
    }

    [Fact]
    public void SetHostedContext_ThenGet_RoundTrips()
    {
        // Arrange
        var session = new HostedContextCapturingSession();

        // Act
        session.SetHostedContext(new HostedSessionContext("alice", "chat-A"));
        var ctx = session.GetHostedContext();

        // Assert
        Assert.NotNull(ctx);
        Assert.Equal("alice", ctx.UserId);
        Assert.Equal("chat-A", ctx.ChatId);
    }

    private static AgentFrameworkResponseHandler BuildHandler(
        AIAgent agent,
        HostedSessionIsolationKeyProvider provider,
        AgentSessionStore? sessionStore = null)
    {
        var services = new ServiceCollection();
        services.AddSingleton(sessionStore ?? new InMemoryAgentSessionStore());
        services.AddSingleton(agent);
        services.AddSingleton(provider);
        var sp = services.BuildServiceProvider();
        return new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);
    }

    private static (CreateResponse Request, Mock<ResponseContext> Context) BuildFreshRequest()
    {
        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());
        return (request, mockContext);
    }

    private static (CreateResponse Request, Mock<ResponseContext> Context) BuildResumeRequest(string conversationId)
    {
        var (request, mockContext) = BuildFreshRequest();
        request.Conversation = BinaryData.FromString($"\"{conversationId}\"");
        return (request, mockContext);
    }

    private static async Task DrainAsync(IAsyncEnumerable<ResponseStreamEvent> stream)
    {
        await foreach (var _ in stream)
        {
        }
    }

    /// <summary>
    /// Minimal <see cref="AIAgent"/> subclass that captures the session it was invoked with so tests
    /// can inspect the <see cref="HostedSessionContext"/> applied by the handler.
    /// </summary>
    private sealed class HostedContextCapturingAgent : AIAgent
    {
        public AgentSession? LastSession { get; set; }

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default)
        {
            this.LastSession = session;
            return ToAsyncEnumerableAsync(new AgentResponseUpdate
            {
                MessageId = "resp_msg_1",
                Contents = [new Extensions.AI.TextContent("ok")]
            });
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            new(new HostedContextCapturingSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(((HostedContextCapturingSession)session).Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(HostedContextCapturingSession.Deserialize(serializedState));

        private static async IAsyncEnumerable<AgentResponseUpdate> ToAsyncEnumerableAsync(params AgentResponseUpdate[] items)
        {
            foreach (var item in items)
            {
                yield return item;
            }

            await Task.CompletedTask;
        }
    }

    /// <summary>
    /// Minimal session implementation that round-trips its <see cref="AgentSessionStateBag"/> via JSON.
    /// </summary>
    private sealed class HostedContextCapturingSession : AgentSession
    {
        public HostedContextCapturingSession()
        {
        }

        private HostedContextCapturingSession(AgentSessionStateBag bag)
        {
            this.StateBag = bag;
        }

        public JsonElement Serialize() => this.StateBag.Serialize();

        public static HostedContextCapturingSession Deserialize(JsonElement element)
            => new(AgentSessionStateBag.Deserialize(element));
    }
}
