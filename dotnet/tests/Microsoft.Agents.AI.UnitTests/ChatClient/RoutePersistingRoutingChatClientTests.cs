// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.ChatClient;

/// <summary>
/// Unit tests for the <see cref="RoutePersistingRoutingChatClient"/> class.
/// </summary>
public class RoutePersistingRoutingChatClientTests
{
    #region Constructor Tests

    [Fact]
    public void Constructor_NullRoutes_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new RoutePersistingRoutingChatClient(null!));
    }

    [Fact]
    public void Constructor_EmptyRoutes_Succeeds()
    {
        // Act
        using var client = new RoutePersistingRoutingChatClient(new Dictionary<string, IChatClient>());

        // Assert
        Assert.Empty(client.Routes);
    }

    [Fact]
    public void Constructor_NullRouteClient_Succeeds()
    {
        // Arrange
        var routes = new Dictionary<string, IChatClient> { ["a"] = null! };

        // Act
        using var client = new RoutePersistingRoutingChatClient(routes);

        // Assert
        Assert.Null(client.Routes["a"]);
    }

    [Theory]
    [InlineData("")]
    [InlineData("  ")]
    public void Constructor_WhitespaceRouteKey_Succeeds(string key)
    {
        // Arrange
        var routes = new Dictionary<string, IChatClient> { [key] = CreateChatClient("a") };

        // Act
        using var client = new RoutePersistingRoutingChatClient(routes);

        // Assert
        Assert.Same(routes[key], client.Routes[key]);
    }

    [Fact]
    public void Constructor_UnknownDefaultRoute_Succeeds()
    {
        // Arrange
        var routes = new Dictionary<string, IChatClient> { ["a"] = CreateChatClient("a") };

        // Act
        using var client = new RoutePersistingRoutingChatClient(
            routes,
            new RoutePersistingRoutingChatClientOptions { DefaultRoute = "missing" });

        // Assert
        Assert.Equal("missing", client.GetActiveRoute(new TestAgentSession()));
    }

    [Fact]
    public void Constructor_ValidRoutes_ExposesRoutes()
    {
        // Arrange
        var routes = CreateRoutes("a", "b");

        // Act
        using var client = new RoutePersistingRoutingChatClient(routes);

        // Assert
        Assert.Equal(2, client.Routes.Count);
        Assert.Contains("a", client.Routes.Keys);
        Assert.Contains("b", client.Routes.Keys);
    }

    [Fact]
    public void Constructor_CopiesRoutes()
    {
        // Arrange
        var routes = CreateRoutes("a");
        using var client = new RoutePersistingRoutingChatClient(routes);

        // Act
        routes["b"] = CreateChatClient("b");

        // Assert
        Assert.DoesNotContain("b", client.Routes.Keys);
    }

    #endregion

    #region Active Route Tests

    [Fact]
    public void GetActiveRoute_NewSession_ReturnsFirstRoute()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        var session = new TestAgentSession();

        // Act
        var route = client.GetActiveRoute(session);

        // Assert
        Assert.Equal("a", route);
    }

    [Fact]
    public void GetActiveRoute_NewSessionWithDefaultRoute_ReturnsConfiguredDefault()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(
            CreateRoutes("a", "b"),
            new RoutePersistingRoutingChatClientOptions { DefaultRoute = "b" });
        var session = new TestAgentSession();

        // Act
        var route = client.GetActiveRoute(session);

        // Assert
        Assert.Equal("b", route);
    }

    [Fact]
    public void GetActiveRoute_EmptyRoutesWithoutDefault_ThrowsInvalidOperationException()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(new Dictionary<string, IChatClient>());

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => client.GetActiveRoute(new TestAgentSession()));
    }

    [Fact]
    public void GetActiveRoute_NullSession_ThrowsArgumentNullException()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => client.GetActiveRoute(null!));
    }

    [Fact]
    public void SetActiveRoute_KnownRoute_RoundTrips()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        var session = new TestAgentSession();

        // Act
        client.SetActiveRoute(session, "b");

        // Assert
        Assert.Equal("b", client.GetActiveRoute(session));
    }

    [Fact]
    public void SetActiveRoute_UnknownRoute_ThrowsArgumentException()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        var session = new TestAgentSession();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => client.SetActiveRoute(session, "missing"));
    }

    [Fact]
    public void SetActiveRoute_NullClient_ThrowsArgumentException()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = CreateChatClient("a"), ["null"] = null! });
        var session = new TestAgentSession();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => client.SetActiveRoute(session, "null"));
        Assert.Equal("a", client.GetActiveRoute(session));
    }

    [Fact]
    public void SetActiveRoute_WhitespaceRouteWithClient_Succeeds()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = CreateChatClient("a"), [" "] = CreateChatClient("blank") });
        var session = new TestAgentSession();

        // Act
        client.SetActiveRoute(session, " ");

        // Assert
        Assert.Equal(" ", client.GetActiveRoute(session));
    }

    [Fact]
    public void SetActiveRoute_NullArguments_ThrowsArgumentNullException()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));
        var session = new TestAgentSession();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => client.SetActiveRoute(null!, "a"));
        Assert.Throws<ArgumentNullException>(() => client.SetActiveRoute(session, null!));
    }

    [Fact]
    public void SetActiveRoute_SeparateSessions_AreIndependent()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        var session1 = new TestAgentSession();
        var session2 = new TestAgentSession();

        // Act
        client.SetActiveRoute(session1, "b");

        // Assert
        Assert.Equal("b", client.GetActiveRoute(session1));
        Assert.Equal("a", client.GetActiveRoute(session2));
    }

    [Fact]
    public void SetActiveRoute_SurvivesStateBagSerialization()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        var session = new TestAgentSession();
        client.SetActiveRoute(session, "b");

        // Act
        var rehydrated = new TestAgentSession(AgentSessionStateBag.Deserialize(session.StateBag.Serialize()));

        // Assert
        Assert.Equal("b", client.GetActiveRoute(rehydrated));
    }

    [Fact]
    public void StateKey_CustomValue_KeepsInstancesIndependent()
    {
        // Arrange
        using var client1 = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        using var client2 = new RoutePersistingRoutingChatClient(
            CreateRoutes("a", "b"),
            new RoutePersistingRoutingChatClientOptions { StateKey = "other" });
        var session = new TestAgentSession();

        // Act
        client1.SetActiveRoute(session, "b");

        // Assert
        Assert.Equal("b", client1.GetActiveRoute(session));
        Assert.Equal("a", client2.GetActiveRoute(session));
    }

    #endregion

    #region Routing Tests

    [Fact]
    public async Task Routes_AddRoute_CanSelectAndRouteAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));
        var session = new TestAgentSession();

        // Act
        client.Routes["b"] = CreateChatClient("b");
        client.SetActiveRoute(session, "b");
        var response = await RunAsync(client, session);

        // Assert
        Assert.Equal("b", response.Text);
    }

    [Fact]
    public async Task Routes_ReplaceActiveRoute_UsesReplacementAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));
        var session = new TestAgentSession();

        // Act
        client.Routes["a"] = CreateChatClient("replacement");
        var response = await RunAsync(client, session);

        // Assert
        Assert.Equal("replacement", response.Text);
    }

    [Fact]
    public async Task Routes_RemoveActiveRoute_ThrowsWhenRequestRunsAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        var session = new TestAgentSession();
        client.SetActiveRoute(session, "b");

        // Act
        client.Routes.Remove("b");

        // Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => RunAsync(client, session));
    }

    [Fact]
    public async Task Routes_UnusedNullClient_DoesNotAffectOtherRoutesAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = CreateChatClient("a"), ["unused"] = null! });
        var session = new TestAgentSession();

        // Act
        var response = await RunAsync(client, session);

        // Assert
        Assert.Equal("a", response.Text);
    }

    [Fact]
    public async Task GetResponseAsync_RoutesToActiveRouteAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        var session = new TestAgentSession();

        // Act
        var first = await RunAsync(client, session);
        client.SetActiveRoute(session, "b");
        var second = await RunAsync(client, session);

        // Assert
        Assert.Equal("a", first.Text);
        Assert.Equal("b", second.Text);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_RoutesToActiveRouteAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        var session = new TestAgentSession();
        client.SetActiveRoute(session, "b");

        // Act
        var updates = await RunStreamingAsync(client, session);

        // Assert
        Assert.Equal("b", string.Concat(updates.Select(u => u.Text)));
    }

    [Fact]
    public async Task GetResponseAsync_NoRunContext_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => client.GetResponseAsync([new ChatMessage(ChatRole.User, "Hello")]));
    }

    [Fact]
    public async Task GetResponseAsync_AfterCompletedRun_DoesNotUseStaleRunContextAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));
        var session = new TestAgentSession();
        await RunAsync(client, session);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => client.GetResponseAsync([new ChatMessage(ChatRole.User, "Hello")]));
    }

    [Fact]
    public async Task GetResponseAsync_AfterNestedRun_UsesOuterSessionAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a", "b"));
        var outerSession = new TestAgentSession();
        var innerSession = new TestAgentSession();
        client.SetActiveRoute(innerSession, "b");

        var innerAgent = new TestAIAgent
        {
            RunAsyncFunc = (messages, session, options, ct) =>
                Task.FromResult(new AgentResponse([new ChatMessage(ChatRole.Assistant, "inner")]))
        };

        ChatResponse? routedResponse = null;
        var outerAgent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, session, options, ct) =>
            {
                await innerAgent.RunAsync("Inner request", innerSession, cancellationToken: ct);
                routedResponse = await client.GetResponseAsync(messages, cancellationToken: ct);
                return new AgentResponse(routedResponse);
            }
        };

        // Act
        await outerAgent.RunAsync("Outer request", outerSession);

        // Assert
        Assert.Equal("a", routedResponse?.Text);
    }

    [Fact]
    public async Task GetResponseAsync_NoSession_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => RunAsync(client, session: null));
    }

    [Fact]
    public async Task GetResponseAsync_ActiveRouteNoLongerRegistered_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange: persist a route key that the client does not know about.
        var session = new TestAgentSession();
        session.StateBag.SetValue(
            nameof(RoutePersistingRoutingChatClient),
            new AgentSessionRoutingState { ActiveRoute = "missing" });

        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => RunAsync(client, session));
    }

    #endregion

    #region GetService Tests

    [Fact]
    public void GetService_SelfType_ReturnsSelf()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));

        // Act & Assert
        Assert.Same(client, client.GetService(typeof(RoutePersistingRoutingChatClient)));
    }

    [Fact]
    public void GetService_NullServiceType_ThrowsArgumentNullException()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => client.GetService(null!));
    }

    [Fact]
    public void GetService_NoRunContext_ForwardsToDefaultRouteClient()
    {
        // Arrange
        var routes = new Dictionary<string, IChatClient>
        {
            ["a"] = CreateChatClient("a", new ChatClientMetadata("provider-a")),
            ["b"] = CreateChatClient("b", new ChatClientMetadata("provider-b")),
        };
        using var client = new RoutePersistingRoutingChatClient(
            routes,
            new RoutePersistingRoutingChatClientOptions { DefaultRoute = "b" });

        // Act
        var metadata = client.GetService(typeof(ChatClientMetadata)) as ChatClientMetadata;

        // Assert
        Assert.Equal("provider-b", metadata?.ProviderName);
    }

    [Fact]
    public void GetService_RemovedDefaultRoute_ReturnsNull()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(CreateRoutes("a"));
        client.Routes.Remove("a");

        // Act
        var metadata = client.GetService(typeof(ChatClientMetadata));

        // Assert
        Assert.Null(metadata);
    }

    [Fact]
    public void GetService_EmptyRoutes_ReturnsNull()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(new Dictionary<string, IChatClient>());

        // Act
        var metadata = client.GetService(typeof(ChatClientMetadata));

        // Assert
        Assert.Null(metadata);
    }

    [Fact]
    public void GetService_EmptyRoutes_CanCreateAgent()
    {
        // Arrange
        using var client = new RoutePersistingRoutingChatClient(new Dictionary<string, IChatClient>());

        // Act
        var agent = client.AsAIAgent();

        // Assert
        Assert.NotNull(agent);
    }

    [Fact]
    public async Task GetService_WithinRun_ForwardsToActiveRouteClientAsync()
    {
        // Arrange
        var routes = new Dictionary<string, IChatClient>
        {
            ["a"] = CreateChatClient("a", new ChatClientMetadata("provider-a")),
            ["b"] = CreateChatClient("b", new ChatClientMetadata("provider-b")),
        };
        using var client = new RoutePersistingRoutingChatClient(routes);
        var session = new TestAgentSession();
        client.SetActiveRoute(session, "b");
        ChatClientMetadata? metadata = null;

        // Act
        var agent = new TestAIAgent
        {
            RunAsyncFunc = (messages, s, options, ct) =>
            {
                metadata = client.GetService(typeof(ChatClientMetadata)) as ChatClientMetadata;
                return Task.FromResult(new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]));
            }
        };
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], session);

        // Assert
        Assert.Equal("provider-b", metadata?.ProviderName);
    }

    #endregion

    #region Dispose Tests

    [Fact]
    public void Dispose_OwnsInnerClients_DisposesRouteClients()
    {
        // Arrange
        var innerA = new TrackingChatClient("a");
        var innerB = new TrackingChatClient("b");
        var client = new RoutePersistingRoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = innerA, ["b"] = innerB },
            new RoutePersistingRoutingChatClientOptions { OwnsInnerClients = true });

        // Act
        client.Dispose();

        // Assert
        Assert.True(innerA.IsDisposed);
        Assert.True(innerB.IsDisposed);
    }

    [Fact]
    public void Dispose_ByDefault_DoesNotDisposeRouteClients()
    {
        // Arrange
        var innerA = new TrackingChatClient("a");
        var client = new RoutePersistingRoutingChatClient(new Dictionary<string, IChatClient> { ["a"] = innerA });

        // Act
        client.Dispose();

        // Assert
        Assert.False(innerA.IsDisposed);
    }

    [Fact]
    public void Dispose_OwnsInnerClients_DisposesOnlyCurrentlyRegisteredClients()
    {
        // Arrange
        var removed = new TrackingChatClient("removed");
        var replacement = new TrackingChatClient("replacement");
        var client = new RoutePersistingRoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = removed },
            new RoutePersistingRoutingChatClientOptions { OwnsInnerClients = true });
        client.Routes["a"] = replacement;

        // Act
        client.Dispose();

        // Assert
        Assert.False(removed.IsDisposed);
        Assert.True(replacement.IsDisposed);
    }

    [Fact]
    public void Dispose_OwnsInnerClients_DisposesAliasedClientOnce()
    {
        // Arrange
        var inner = new TrackingChatClient("inner");
        var client = new RoutePersistingRoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = inner, ["alias"] = inner },
            new RoutePersistingRoutingChatClientOptions { OwnsInnerClients = true });

        // Act
        client.Dispose();

        // Assert
        Assert.Equal(1, inner.DisposeCount);
    }

    [Fact]
    public void Dispose_CalledMultipleTimes_DisposesInnerClientOnce()
    {
        // Arrange
        var inner = new TrackingChatClient("inner");
        var client = new RoutePersistingRoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = inner },
            new RoutePersistingRoutingChatClientOptions { OwnsInnerClients = true });

        // Act
        client.Dispose();
        client.Dispose();

        // Assert
        Assert.Equal(1, inner.DisposeCount);
    }

    #endregion

    #region Helpers

    private static Dictionary<string, IChatClient> CreateRoutes(params string[] keys)
    {
        var routes = new Dictionary<string, IChatClient>();
        foreach (var key in keys)
        {
            routes[key] = CreateChatClient(key);
        }

        return routes;
    }

    /// <summary>
    /// Creates a chat client that echoes the supplied identifier, so tests can assert which route handled a request.
    /// </summary>
    private static TrackingChatClient CreateChatClient(string id, ChatClientMetadata? metadata = null)
        => new(id, metadata);

    private static async Task<ChatResponse> RunAsync(RoutePersistingRoutingChatClient client, AgentSession? session)
    {
        ChatResponse? response = null;
        var agent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, s, options, ct) =>
            {
                response = await client.GetResponseAsync(messages, cancellationToken: ct);
                return new AgentResponse(response);
            }
        };

        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], session);
        return response!;
    }

    private static async Task<List<ChatResponseUpdate>> RunStreamingAsync(RoutePersistingRoutingChatClient client, AgentSession? session)
    {
        List<ChatResponseUpdate> updates = [];
        var agent = new TestAIAgent
        {
            RunAsyncFunc = async (messages, s, options, ct) =>
            {
                await foreach (var update in client.GetStreamingResponseAsync(messages, cancellationToken: ct))
                {
                    updates.Add(update);
                }

                return new AgentResponse([new ChatMessage(ChatRole.Assistant, "done")]);
            }
        };

        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hello")], session);
        return updates;
    }

    private sealed class TrackingChatClient(string id, ChatClientMetadata? metadata = null) : IChatClient
    {
        public bool IsDisposed => this.DisposeCount > 0;

        public int DisposeCount { get; private set; }

        public Task<ChatResponse> GetResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
            => Task.FromResult(new ChatResponse([new ChatMessage(ChatRole.Assistant, id)]));

        public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
            IEnumerable<ChatMessage> messages, ChatOptions? options = null,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            yield return new ChatResponseUpdate(ChatRole.Assistant, id);
        }

        public object? GetService(Type serviceType, object? serviceKey = null)
            => serviceKey is null && serviceType == typeof(ChatClientMetadata) ? metadata : null;

        public void Dispose() => this.DisposeCount++;
    }

    private sealed class TestAgentSession : AgentSession
    {
        public TestAgentSession()
        {
        }

        public TestAgentSession(AgentSessionStateBag stateBag)
        {
            this.StateBag = stateBag;
        }
    }

    #endregion
}
