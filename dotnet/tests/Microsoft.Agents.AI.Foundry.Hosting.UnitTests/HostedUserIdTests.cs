// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Tests covering the per-session user identity that <see cref="AgentFrameworkResponseHandler"/>
/// reads from <see cref="ResponseContext.PlatformContext"/>.
/// </summary>
public class HostedUserIdTests
{
    private const string TestUserId = "alice";

    [Fact]
    public async Task AspNetMiddleware_OverridesUserIdBeforeAgentHandlerAsync()
    {
        // Arrange: no isolation provider is registered. Application middleware replaces an
        // untrusted caller value before the AgentServer endpoint creates its ResponseContext.
        var capturingAgent = new HostedContextCapturingAgent();
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddFoundryResponses(capturingAgent, new TestAgentSessionStore());
        builder.Services.AddLogging();

        await using var app = builder.Build();
        app.Use(async (context, next) =>
        {
            context.Request.Headers["x-agent-user-id"] = TestUserId;
            await next(context);
        });
        app.MapFoundryResponses();
        await app.StartAsync();

        var testServer = app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found.");
        using var client = testServer.CreateClient();
        using var request = new HttpRequestMessage(HttpMethod.Post, "/responses")
        {
            Content = new StringContent(
                """
                {
                  "model": "test",
                  "input": [
                    {
                      "type": "message",
                      "id": "msg_1",
                      "status": "completed",
                      "role": "user",
                      "content": [{ "type": "input_text", "text": "Hello" }]
                    }
                  ]
                }
                """,
                Encoding.UTF8,
                "application/json"),
        };
        request.Headers.TryAddWithoutValidation("x-agent-user-id", "caller-controlled");

        // Act
        using var response = await client.SendAsync(request);
        string body = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.True(
            response.StatusCode == HttpStatusCode.OK,
            $"Expected HTTP 200 but received {(int)response.StatusCode}: {body}");
        Assert.NotNull(capturingAgent.LastSession);
        Assert.Equal(TestUserId, capturingAgent.LastSession.GetFoundryHostedUserId());
    }

    [Fact]
    public async Task Handler_FreshSession_AppliesUserIdentityFromPlatformContextAsync()
    {
        // Arrange
        var capturingAgent = new HostedContextCapturingAgent();
        var handler = BuildHandler(capturingAgent);

        var (request, mockContext) = BuildFreshRequest(TestUserId);

        // Act
        await DrainAsync(handler.CreateAsync(request, mockContext.Object, CancellationToken.None));

        // Assert
        Assert.NotNull(capturingAgent.LastSession);
        Assert.Equal(TestUserId, capturingAgent.LastSession.GetFoundryHostedUserId());
    }

    [Fact]
    public async Task Handler_NullKeysFromProvider_NotHosted_SucceedsWithoutContextAsync()
    {
        // Arrange: no x-agent-user-id is present. Under unit tests FoundryEnvironment.IsHosted is false, so
        // the container is treated as local: the request must proceed with per-user isolation not triggered
        // rather than 500ing. No hosted context is stamped on the session.
        var capturingAgent = new HostedContextCapturingAgent();
        var handler = BuildHandler(capturingAgent);

        var (request, mockContext) = BuildFreshRequest(userId: null);

        // Act
        await DrainAsync(handler.CreateAsync(request, mockContext.Object, CancellationToken.None));

        // Assert: no throw, a session was produced, and it carries no hosted identity context.
        Assert.NotNull(capturingAgent.LastSession);
        Assert.Null(capturingAgent.LastSession.GetFoundryHostedUserId());
    }

    [Fact]
    public async Task Handler_ResumeSession_MatchingKeys_PassesAsync()
    {
        // Arrange
        var capturingAgent = new HostedContextCapturingAgent();
        var sessionStore = new TestAgentSessionStore();
        var handler = BuildHandler(capturingAgent, sessionStore);

        // Step 1: drive a fresh request to populate the session store with a tagged session.
        var (freshRequest, freshContext) = BuildFreshRequest();
        await DrainAsync(handler.CreateAsync(freshRequest, freshContext.Object, CancellationToken.None));
        Assert.NotNull(capturingAgent.LastSession);

        // Step 2: persist the session under a known conversation id (mimics what the handler does
        // when it has a conversation id; here we plant it directly so we can drive a resume request).
        // The session is scoped to the same user ("alice") that will resume it.
        const string ConversationId = "resume-chat-id";
        AIAgent storageAgent = new FoundryHostingAgent(capturingAgent, "default");
        await sessionStore.SaveSessionAsync(
            storageAgent,
            new AgentSessionStoreKey(ConversationId).WithPartition("user", TestUserId),
            capturingAgent.LastSession,
            CancellationToken.None);

        // Step 3: drive a resume request with the same isolation keys.
        var (resumeRequest, resumeContext) = BuildResumeRequest(ConversationId);
        capturingAgent.LastSession = null;

        // Act
        await DrainAsync(handler.CreateAsync(resumeRequest, resumeContext.Object, CancellationToken.None));

        // Assert
        Assert.NotNull(capturingAgent.LastSession);
        Assert.Equal(TestUserId, capturingAgent.LastSession.GetFoundryHostedUserId());
    }

    [Fact]
    public async Task Handler_ResumeSession_MismatchedUserId_Returns403Async()
    {
        // Arrange
        var capturingAgent = new HostedContextCapturingAgent();
        var sessionStore = new TestAgentSessionStore();
        var aliceHandler = BuildHandler(capturingAgent, sessionStore);

        var (freshRequest, freshContext) = BuildFreshRequest();
        await DrainAsync(aliceHandler.CreateAsync(freshRequest, freshContext.Object, CancellationToken.None));
        const string ConversationId = "resume-chat-id";
        AIAgent storageAgent = new FoundryHostingAgent(capturingAgent, "default");

        // Plant Alice's stamped session UNDER BOB'S partition to simulate a session that reached Bob's
        // key despite the per-user path partitioning (e.g. a non-partitioning custom store, or in-process
        // tampering). The 403 identity check is the defense-in-depth layer that must still reject it even
        // when the physical partition was bypassed.
        await sessionStore.SaveSessionAsync(
            storageAgent,
            new AgentSessionStoreKey(ConversationId).WithPartition("user", "bob"),
            capturingAgent.LastSession!,
            CancellationToken.None);

        // Bob attempts to resume Alice's conversation.
        var bobHandler = BuildHandler(capturingAgent, sessionStore);
        var (resumeRequest, resumeContext) = BuildResumeRequest(ConversationId, userId: "bob");

        // Act & Assert
        var ex = await Assert.ThrowsAsync<ResponsesApiException>(() => DrainAsync(bobHandler.CreateAsync(resumeRequest, resumeContext.Object, CancellationToken.None)));
        Assert.Equal(403, ex.StatusCode);
        Assert.Equal("Hosted user identity mismatch", ex.Error.Message);
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
        var sessionStore = new TestAgentSessionStore();
        const string ConversationId = "untagged-chat-id";
        var untagged = await capturingAgent.CreateSessionAsync(CancellationToken.None);
        AIAgent storageAgent = new FoundryHostingAgent(capturingAgent, "default");
        await sessionStore.SaveSessionAsync(
            storageAgent,
            new AgentSessionStoreKey(ConversationId).WithPartition("user", "alice"),
            untagged,
            CancellationToken.None);

        var handler = BuildHandler(capturingAgent, sessionStore);
        var (resumeRequest, resumeContext) = BuildResumeRequest(ConversationId);

        // Act
        await DrainAsync(handler.CreateAsync(resumeRequest, resumeContext.Object, CancellationToken.None));

        // Assert
        Assert.NotNull(capturingAgent.LastSession);
        Assert.Equal("alice", capturingAgent.LastSession.GetFoundryHostedUserId());
    }

    private static AgentFrameworkResponseHandler BuildHandler(
        AIAgent agent,
        AgentSessionStore? sessionStore = null)
    {
        var services = new ServiceCollection();
        services.AddSingleton(sessionStore ?? new TestAgentSessionStore());
        services.AddSingleton(agent);
        var sp = services.BuildServiceProvider();
        return new AgentFrameworkResponseHandler(sp, NullLogger<AgentFrameworkResponseHandler>.Instance);
    }

    private static (CreateResponse Request, Mock<ResponseContext> Context) BuildFreshRequest(
        string? userId = TestUserId)
    {
        var request = new CreateResponse { Model = "test" };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.PlatformContext).Returns(
            userId is null ? PlatformContext.Empty : new PlatformContext(userId, null));
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());
        return (request, mockContext);
    }

    private static (CreateResponse Request, Mock<ResponseContext> Context) BuildResumeRequest(
        string conversationId,
        string? userId = TestUserId)
    {
        var (request, mockContext) = BuildFreshRequest(userId);
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
    /// can inspect the hosted user id applied by the handler.
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
