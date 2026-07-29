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

    [Fact]
    public void HostedSessionContext_RejectsNullOrWhitespaceKeys()
    {
        // Assert
        Assert.Throws<ArgumentNullException>(() => new HostedSessionContext(null!));
        Assert.Throws<ArgumentException>(() => new HostedSessionContext(string.Empty));
        Assert.Throws<ArgumentException>(() => new HostedSessionContext("   "));
    }

    [Fact]
    public async Task PlatformProvider_MapsIsolationContextValuesAsync()
    {
        // Arrange
        var provider = new PlatformHostedSessionIsolationKeyProvider();
        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.PlatformContext).Returns(new PlatformContext(TestUserId, "call-1"));
        var request = new CreateResponse { Model = "test" };

        // Act
        var result = await provider.GetKeysAsync(mockContext.Object, request, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(TestUserId, result.UserId);
    }

    [Fact]
    public async Task PlatformProvider_ReturnsNullWhenIsolationKeysAreEmptyAsync()
    {
        // Arrange
        var provider = new PlatformHostedSessionIsolationKeyProvider();
        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        // CallBase delegates to ResponseContext.PlatformContext default which is PlatformContext.Empty.
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
        var fakeProvider = new FakeHostedSessionIsolationKeyProvider("alice");
        var handler = BuildHandler(capturingAgent, fakeProvider);

        var (request, mockContext) = BuildFreshRequest();

        // Act
        await DrainAsync(handler.CreateAsync(request, mockContext.Object, CancellationToken.None));

        // Assert
        Assert.NotNull(capturingAgent.LastSession);
        var ctx = capturingAgent.LastSession.GetHostedContext();
        Assert.NotNull(ctx);
        Assert.Equal("alice", ctx.UserId);
    }

    [Fact]
    public async Task Handler_NullKeysFromProvider_NotHosted_SucceedsWithoutContextAsync()
    {
        // Arrange: a provider that returns null keys (as the default platform provider does locally when
        // no x-agent-user-id header is present). Under unit tests FoundryEnvironment.IsHosted is false, so
        // the container is treated as local: the request must proceed with per-user isolation not triggered
        // rather than 500ing. No hosted context is stamped on the session.
        var capturingAgent = new HostedContextCapturingAgent();
        var fakeProvider = new FakeHostedSessionIsolationKeyProvider(userId: null);
        var handler = BuildHandler(capturingAgent, fakeProvider);

        var (request, mockContext) = BuildFreshRequest();

        // Act
        await DrainAsync(handler.CreateAsync(request, mockContext.Object, CancellationToken.None));

        // Assert: no throw, a session was produced, and it carries no hosted identity context.
        Assert.NotNull(capturingAgent.LastSession);
        Assert.Null(capturingAgent.LastSession.GetHostedContext());
    }

    [Fact]
    public async Task Handler_ResumeSession_MatchingKeys_PassesAsync()
    {
        // Arrange
        var capturingAgent = new HostedContextCapturingAgent();
        var fakeProvider = new FakeHostedSessionIsolationKeyProvider("alice");
        var sessionStore = new InMemoryAgentSessionStore();
        var handler = BuildHandler(capturingAgent, fakeProvider, sessionStore);

        // Step 1: drive a fresh request to populate the session store with a tagged session.
        var (freshRequest, freshContext) = BuildFreshRequest();
        await DrainAsync(handler.CreateAsync(freshRequest, freshContext.Object, CancellationToken.None));
        Assert.NotNull(capturingAgent.LastSession);

        // Step 2: persist the session under a known conversation id (mimics what the handler does
        // when it has a conversation id; here we plant it directly so we can drive a resume request).
        // The session is scoped to the same user ("alice") that will resume it.
        const string ConversationId = "resume-chat-id";
        await sessionStore.SaveSessionAsync(capturingAgent, ConversationId, capturingAgent.LastSession, "alice", CancellationToken.None);

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
        var aliceProvider = new FakeHostedSessionIsolationKeyProvider("alice");
        var sessionStore = new InMemoryAgentSessionStore();
        var aliceHandler = BuildHandler(capturingAgent, aliceProvider, sessionStore);

        var (freshRequest, freshContext) = BuildFreshRequest();
        await DrainAsync(aliceHandler.CreateAsync(freshRequest, freshContext.Object, CancellationToken.None));
        const string ConversationId = "resume-chat-id";

        // Plant Alice's stamped session UNDER BOB'S partition to simulate a session that reached Bob's
        // key despite the per-user path partitioning (e.g. a non-partitioning custom store, or in-process
        // tampering). The 403 identity check is the defense-in-depth layer that must still reject it even
        // when the physical partition was bypassed.
        await sessionStore.SaveSessionAsync(capturingAgent, ConversationId, capturingAgent.LastSession!, "bob", CancellationToken.None);

        // Bob attempts to resume Alice's conversation.
        var bobProvider = new FakeHostedSessionIsolationKeyProvider("bob");
        var bobHandler = BuildHandler(capturingAgent, bobProvider, sessionStore);
        var (resumeRequest, resumeContext) = BuildResumeRequest(ConversationId);

        // Act & Assert
        var ex = await Assert.ThrowsAsync<ResponsesApiException>(() => DrainAsync(bobHandler.CreateAsync(resumeRequest, resumeContext.Object, CancellationToken.None)));
        Assert.Equal(403, ex.StatusCode);
        Assert.Equal("Hosted session identity context mismatch", ex.Error.Message);
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
        await sessionStore.SaveSessionAsync(capturingAgent, ConversationId, untagged, "alice", CancellationToken.None);

        var fakeProvider = new FakeHostedSessionIsolationKeyProvider("alice");
        var handler = BuildHandler(capturingAgent, fakeProvider, sessionStore);
        var (resumeRequest, resumeContext) = BuildResumeRequest(ConversationId);

        // Act
        await DrainAsync(handler.CreateAsync(resumeRequest, resumeContext.Object, CancellationToken.None));

        // Assert
        Assert.NotNull(capturingAgent.LastSession);
        var ctx = capturingAgent.LastSession.GetHostedContext();
        Assert.NotNull(ctx);
        Assert.Equal("alice", ctx.UserId);
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
        session.SetHostedContext(new HostedSessionContext("alice"));
        var ctx = session.GetHostedContext();

        // Assert
        Assert.NotNull(ctx);
        Assert.Equal("alice", ctx.UserId);
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
