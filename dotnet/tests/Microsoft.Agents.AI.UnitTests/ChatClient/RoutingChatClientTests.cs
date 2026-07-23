// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for <see cref="RoutingChatClient"/>.
/// </summary>
public class RoutingChatClientTests
{
    #region Construction

    /// <summary>
    /// Verify that the constructor throws when there are no inner clients and no fallback factory.
    /// </summary>
    [Fact]
    public void Constructor_NullInnerClients_NoFallback_Throws()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentNullException>(() => new RoutingChatClient((IReadOnlyDictionary<string, IChatClient>)null!));
    }

    /// <summary>
    /// Verify that the constructor throws when the inner clients dictionary is empty and no fallback factory
    /// is configured.
    /// </summary>
    [Fact]
    public void Constructor_EmptyInnerClients_NoFallback_Throws()
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentException>(() => new RoutingChatClient(new Dictionary<string, IChatClient>()));
    }

    /// <summary>
    /// Verify that the constructor allows no inner clients when a fallback factory is configured.
    /// </summary>
    [Fact]
    public void Constructor_NoInnerClients_WithFallback_Succeeds()
    {
        // Arrange
        var fallback = CreateMockClient();

        // Act & Assert (does not throw)
        using var routing = new RoutingChatClient(
            fallbackFactory: (_, _, _) => new ValueTask<IChatClient>(fallback.Object));
    }

    /// <summary>
    /// Verify that <see cref="RoutingContext"/> can be constructed via its public constructor so callers can
    /// unit-test their own router and fallback factory callbacks.
    /// </summary>
    [Fact]
    public async Task RoutingContext_PublicConstructor_ExposesSuppliedValuesAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient> { ["a"] = clientA.Object });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();
        var messages = new[] { new ChatMessage(ChatRole.User, "hi") };
        var options = new ChatOptions();
        var innerClients = new Dictionary<string, IChatClient> { ["a"] = clientA.Object };

        // Act
        var context = new RoutingContext(agent, session, messages, options, innerClients, "a");

        // Assert
        Assert.Same(agent, context.Agent);
        Assert.Same(session, context.Session);
        Assert.Same(messages, context.Messages);
        Assert.Same(options, context.Options);
        Assert.Same(innerClients, context.InnerClients);
        Assert.Equal("a", context.ActiveDestination);
    }

    #endregion

    #region Routing

    /// <summary>
    /// Verify that, without a custom router, requests route to the default (first) destination.
    /// </summary>
    [Fact]
    public async Task GetResponseAsync_DefaultRoutesToFirstDestinationAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var clientB = CreateMockClient();
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient>
        {
            ["a"] = clientA.Object,
            ["b"] = clientB.Object,
        });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientB.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Verify that a custom router selects the destination for a request.
    /// </summary>
    [Fact]
    public async Task GetResponseAsync_CustomRouterSelectsDestinationAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var clientB = CreateMockClient();
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = clientA.Object, ["b"] = clientB.Object },
            options: new RoutingChatClientOptions { Router = (_, _) => new ValueTask<string?>("b") });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        clientB.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Verify that an asynchronous router is awaited before the selected destination is used.
    /// </summary>
    [Fact]
    public async Task GetResponseAsync_AsyncRouterIsAwaitedAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var clientB = CreateMockClient();
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = clientA.Object, ["b"] = clientB.Object },
            options: new RoutingChatClientOptions
            {
                Router = async (_, ct) =>
                {
                    await Task.Delay(1, ct);
                    return "b";
                },
            });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        clientB.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Verify that the router and fallback factory receive the current agent and session on the context.
    /// </summary>
    [Fact]
    public async Task Router_ReceivesAgentAndSessionAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        AIAgent? observedAgent = null;
        AgentSession? observedSession = null;
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = clientA.Object },
            options: new RoutingChatClientOptions
            {
                Router = (context, _) =>
                {
                    observedAgent = context.Agent;
                    observedSession = context.Session;
                    return new ValueTask<string?>(context.ActiveDestination);
                },
            });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        Assert.NotNull(observedAgent);
        Assert.NotNull(observedSession);
    }

    /// <summary>
    /// Verify that invoking the client outside of an agent run throws.
    /// </summary>
    [Fact]
    public async Task GetResponseAsync_WithoutRunContext_ThrowsAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient> { ["a"] = clientA.Object });

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            routing.GetResponseAsync([new ChatMessage(ChatRole.User, "hi")]));
    }

    /// <summary>
    /// Verify that an unknown routed key with no fallback factory throws.
    /// </summary>
    [Fact]
    public async Task GetResponseAsync_UnknownKeyWithoutFallback_ThrowsAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = clientA.Object },
            options: new RoutingChatClientOptions { Router = (_, _) => new ValueTask<string?>("missing") });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session));
    }

    /// <summary>
    /// Verify that streaming requests route to the selected destination.
    /// </summary>
    [Fact]
    public async Task GetStreamingResponseAsync_RoutesToSelectedDestinationAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var clientB = CreateMockClient();
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = clientA.Object, ["b"] = clientB.Object },
            options: new RoutingChatClientOptions { Router = (_, _) => new ValueTask<string?>("b") });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await foreach (var _ in agent.RunStreamingAsync([new ChatMessage(ChatRole.User, "hi")], session))
        {
        }

        // Assert
        clientB.Verify(c => c.GetStreamingResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientA.Verify(c => c.GetStreamingResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Verify that when the routed key is not registered, the fallback factory constructs a client on the fly.
    /// </summary>
    [Fact]
    public async Task GetResponseAsync_FallbackFactoryCreatesClient_WhenKeyUnknownAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var fallback = CreateMockClient();
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = clientA.Object },
            fallbackFactory: (_, _, _) => new ValueTask<IChatClient>(fallback.Object),
            options: new RoutingChatClientOptions
            {
                Router = (_, _) => new ValueTask<string?>("created"),
            });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        fallback.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    #endregion

    #region GetService

    /// <summary>
    /// Verify that GetService returns the routing client itself when the requested type matches.
    /// </summary>
    [Fact]
    public void GetService_ReturnsSelf_WhenTypeMatches()
    {
        // Arrange
        var clientA = CreateMockClient();
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient> { ["a"] = clientA.Object });

        // Act
        var service = routing.GetService(typeof(RoutingChatClient));

        // Assert
        Assert.Same(routing, service);
    }

    /// <summary>
    /// Verify that GetService forwards to the first inner client when no run context is active.
    /// </summary>
    [Fact]
    public void GetService_ForwardsToFirstInnerClient_WhenNoRunContext()
    {
        // Arrange
        var clientA = CreateMockClient();
        var marker = new object();
        clientA.Setup(c => c.GetService(typeof(string), null)).Returns(marker);
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient> { ["a"] = clientA.Object });

        // Act
        var service = routing.GetService(typeof(string));

        // Assert
        Assert.Same(marker, service);
        clientA.Verify(c => c.GetService(typeof(string), null), Times.Once);
    }

    #endregion

    #region Active destination (session-based)

    /// <summary>
    /// Verify that <see cref="RoutingChatClient.SetActiveDestinationKey"/> switches routing for the session and
    /// that <see cref="RoutingChatClient.GetActiveDestinationKey"/> reflects the change.
    /// </summary>
    [Fact]
    public async Task SetActiveDestinationKey_SwitchesRoutingForSessionAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var clientB = CreateMockClient();
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient>
        {
            ["a"] = clientA.Object,
            ["b"] = clientB.Object,
        });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        routing.SetActiveDestinationKey(session, "b");
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        Assert.Equal("b", routing.GetActiveDestinationKey(session));
        clientB.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Verify that the default active destination key for a new session is the first inner client key.
    /// </summary>
    [Fact]
    public async Task GetActiveDestinationKey_DefaultsToFirstInnerClientKeyAsync()
    {
        // Arrange
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient>
        {
            ["a"] = CreateMockClient().Object,
            ["b"] = CreateMockClient().Object,
        });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        var key = routing.GetActiveDestinationKey(session);

        // Assert
        Assert.Equal("a", key);
    }

    /// <summary>
    /// Verify that a <see langword="null"/> active destination key routes to the fallback factory (invoked with a
    /// <see langword="null"/> key), rather than to the first inner client.
    /// </summary>
    [Fact]
    public async Task SetActiveDestinationKey_Null_RoutesToFallbackWithNullKeyAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var fallback = CreateMockClient();
        string? observedKey = "sentinel";
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = clientA.Object },
            fallbackFactory: (key, _, _) =>
            {
                observedKey = key;
                return new ValueTask<IChatClient>(fallback.Object);
            });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act — set the active destination to null.
        routing.SetActiveDestinationKey(session, null);
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        Assert.Null(routing.GetActiveDestinationKey(session));
        Assert.Null(observedKey);
        fallback.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Verify that a <see langword="null"/> active destination key throws when no fallback factory is configured
    /// (the first inner client is not used as an implicit default).
    /// </summary>
    [Fact]
    public async Task SetActiveDestinationKey_Null_NoFallback_ThrowsAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient>
        {
            ["a"] = clientA.Object,
        });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        routing.SetActiveDestinationKey(session, null);

        // Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session));
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Verify that an unregistered active destination key routes to the fallback factory (no exception).
    /// </summary>
    [Fact]
    public async Task SetActiveDestinationKey_UnregisteredKey_RoutesToFallbackAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var fallback = CreateMockClient();
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = clientA.Object },
            fallbackFactory: (_, _, _) => new ValueTask<IChatClient>(fallback.Object));
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        routing.SetActiveDestinationKey(session, "created");
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        fallback.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Verify that an empty-string active destination key is treated as an ordinary (unregistered) key and
    /// routes to the fallback factory.
    /// </summary>
    [Fact]
    public async Task SetActiveDestinationKey_EmptyString_RoutesToFallbackAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var fallback = CreateMockClient();
        string? observedKey = null;
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = clientA.Object },
            fallbackFactory: (key, _, _) =>
            {
                observedKey = key;
                return new ValueTask<IChatClient>(fallback.Object);
            });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        routing.SetActiveDestinationKey(session, string.Empty);
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        Assert.Equal(string.Empty, observedKey);
        fallback.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verify that the active destination is isolated between sessions.
    /// </summary>
    [Fact]
    public async Task ActiveDestination_IsolatedBetweenSessionsAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var clientB = CreateMockClient();
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient>
        {
            ["a"] = clientA.Object,
            ["b"] = clientB.Object,
        });
        var agent = new ChatClientAgent(routing);
        var sessionOne = await agent.CreateSessionAsync();
        var sessionTwo = await agent.CreateSessionAsync();

        // Act — switch only session one to "b"; session two keeps the default "a".
        routing.SetActiveDestinationKey(sessionOne, "b");
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], sessionOne);
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], sessionTwo);

        // Assert
        Assert.Equal("b", routing.GetActiveDestinationKey(sessionOne));
        Assert.Equal("a", routing.GetActiveDestinationKey(sessionTwo));
        clientB.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    #endregion

    #region Fallback disposal (per request)

    /// <summary>
    /// Verify that the fallback factory is invoked per request (no caching) and each created client is disposed
    /// after the request completes.
    /// </summary>
    [Fact]
    public async Task FallbackFactory_CreatesPerRequest_AndDisposesAfterUseAsync()
    {
        // Arrange
        var created = new List<Mock<IChatClient>>();
        const string RouteKey = "created";
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = CreateMockClient().Object },
            fallbackFactory: (_, _, _) =>
            {
                var mock = CreateMockClient();
                created.Add(mock);
                return new ValueTask<IChatClient>(mock.Object);
            },
            options: new RoutingChatClientOptions
            {
                Router = (_, _) => new ValueTask<string?>(RouteKey),
            });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act — two runs with the same routed key.
        await agent.RunAsync([new ChatMessage(ChatRole.User, "one")], session);
        await agent.RunAsync([new ChatMessage(ChatRole.User, "two")], session);

        // Assert — a fresh client is created for each request and disposed after use.
        Assert.Equal(2, created.Count);
        foreach (var mock in created)
        {
            mock.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
            mock.Verify(c => c.Dispose(), Times.Once);
        }
    }

    /// <summary>
    /// Verify that a client created by the fallback factory is disposed after the request completes by default.
    /// </summary>
    [Fact]
    public async Task FallbackFactory_DisposesCreatedClientAfterUse_ByDefaultAsync()
    {
        // Arrange
        var fallback = CreateMockClient();
        var routing = new RoutingChatClient(
            fallbackFactory: (_, _, _) => new ValueTask<IChatClient>(fallback.Object));
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        fallback.Verify(c => c.Dispose(), Times.Once);
    }

    /// <summary>
    /// Verify that setting <see cref="RoutingChatClientOptions.DisableFallbackChatClientDisposal"/> prevents the
    /// created fallback client from being disposed after use.
    /// </summary>
    [Fact]
    public async Task DisableFallbackChatClientDisposal_DoesNotDisposeCreatedClientAsync()
    {
        // Arrange
        var fallback = CreateMockClient();
        var routing = new RoutingChatClient(
            fallbackFactory: (_, _, _) => new ValueTask<IChatClient>(fallback.Object),
            options: new RoutingChatClientOptions { DisableFallbackChatClientDisposal = true });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        fallback.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        fallback.Verify(c => c.Dispose(), Times.Never);
    }

    /// <summary>
    /// Verify that a registered inner client is not disposed after a request (inner clients are owned by the
    /// routing client and disposed only at teardown).
    /// </summary>
    [Fact]
    public async Task InnerClient_NotDisposedAfterRequestAsync()
    {
        // Arrange
        var clientA = CreateMockClient();
        var routing = new RoutingChatClient(new Dictionary<string, IChatClient> { ["a"] = clientA.Object });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        clientA.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
        clientA.Verify(c => c.Dispose(), Times.Never);
    }

    /// <summary>
    /// Verify that a client with no inner clients routes every request via the fallback factory.
    /// </summary>
    [Fact]
    public async Task NoInnerClients_RoutesViaFallbackAsync()
    {
        // Arrange
        var fallback = CreateMockClient();
        var routing = new RoutingChatClient(
            fallbackFactory: (_, _, _) => new ValueTask<IChatClient>(fallback.Object),
            options: new RoutingChatClientOptions
            {
                Router = (_, _) => new ValueTask<string?>("anything"),
            });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        fallback.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verify that a fallback-only client with no router and a default (null) active destination invokes the
    /// fallback factory with a <see langword="null"/> key.
    /// </summary>
    [Fact]
    public async Task NoInnerClients_NoRouter_InvokesFallbackWithNullKeyAsync()
    {
        // Arrange
        var fallback = CreateMockClient();
        string? observedKey = "sentinel";
        var routing = new RoutingChatClient(
            fallbackFactory: (key, _, _) =>
            {
                observedKey = key;
                return new ValueTask<IChatClient>(fallback.Object);
            });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "hi")], session);

        // Assert
        Assert.Null(observedKey);
        fallback.Verify(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Once);
    }

    #endregion

    #region State key

    /// <summary>
    /// Verify that a custom <see cref="RoutingChatClientOptions.StateKey"/> stores routing state under that key.
    /// </summary>
    [Fact]
    public async Task CustomStateKey_StoresStateUnderProvidedKeyAsync()
    {
        // Arrange
        const string StateKey = "my-routing-key";
        var routing = new RoutingChatClient(
            new Dictionary<string, IChatClient> { ["a"] = CreateMockClient().Object, ["b"] = CreateMockClient().Object },
            options: new RoutingChatClientOptions { StateKey = StateKey });
        var agent = new ChatClientAgent(routing);
        var session = await agent.CreateSessionAsync();

        // Act
        routing.SetActiveDestinationKey(session, "b");

        // Assert
        Assert.True(session.StateBag.TryGetValue<RoutingState>(StateKey, out var state));
        Assert.Equal("b", state!.ActiveDestination);
    }

    #endregion

    #region Helpers

    private static Mock<IChatClient> CreateMockClient(string responseText = "ok")
    {
        var mock = new Mock<IChatClient>();
        mock.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new ChatMessage(ChatRole.Assistant, responseText)]));
        mock.Setup(c => c.GetStreamingResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(new ChatResponseUpdate(ChatRole.Assistant, responseText)));
        return mock;
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
