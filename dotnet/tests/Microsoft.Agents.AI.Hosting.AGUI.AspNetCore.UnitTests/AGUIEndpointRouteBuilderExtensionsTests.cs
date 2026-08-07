// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AGUIEndpointRouteBuilderExtensions"/> class.
/// </summary>
public sealed class AGUIEndpointRouteBuilderExtensionsTests
{
    [Fact]
    public void MapAGUIServer_MapsEndpoint_AtSpecifiedPattern()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        const string Pattern = "/api/agent";
        AIAgent agent = new TestAgent();

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer(Pattern, agent);

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public void MapAGUIServer_WithAgentName_ResolvesKeyedAgentFromDI()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        AIAgent agent = new NamedTestAgent();

        serviceProviderMock.As<IKeyedServiceProvider>()
            .Setup(sp => sp.GetRequiredKeyedService(typeof(AIAgent), "test-agent"))
            .Returns(agent);

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer("test-agent", "/api/agent");

        // Assert
        Assert.NotNull(result);
        serviceProviderMock.As<IKeyedServiceProvider>()
            .Verify(sp => sp.GetRequiredKeyedService(typeof(AIAgent), "test-agent"), Times.Once);
    }

    [Fact]
    public void MapAGUIServer_WithHostedAgentBuilder_ResolvesAgentByBuilderName()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        Mock<IHostedAgentBuilder> agentBuilderMock = new();
        AIAgent agent = new NamedTestAgent();

        agentBuilderMock.Setup(b => b.Name).Returns("test-agent");

        serviceProviderMock.As<IKeyedServiceProvider>()
            .Setup(sp => sp.GetRequiredKeyedService(typeof(AIAgent), "test-agent"))
            .Returns(agent);

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer(agentBuilderMock.Object, "/api/agent");

        // Assert
        Assert.NotNull(result);
        serviceProviderMock.As<IKeyedServiceProvider>()
            .Verify(sp => sp.GetRequiredKeyedService(typeof(AIAgent), "test-agent"), Times.Once);
    }

    [Fact]
    public void MapAGUIServer_WithAgent_ResolvesSessionStoreFromDI()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        Mock<AgentSessionStore> sessionStoreMock = new();
        AIAgent agent = new NamedTestAgent();

        serviceProviderMock.As<IKeyedServiceProvider>()
            .Setup(sp => sp.GetKeyedService(typeof(AgentSessionStore), "test-agent"))
            .Returns(sessionStoreMock.Object);

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer("/api/agent", agent);

        // Assert
        Assert.NotNull(result);
        serviceProviderMock.As<IKeyedServiceProvider>()
            .Verify(sp => sp.GetKeyedService(typeof(AgentSessionStore), "test-agent"), Times.Once);
    }

    [Fact]
    public void MapAGUIServer_WithoutSessionStore_FallsBackToNoopStore()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        AIAgent agent = new TestAgent();

        // No session store registered - IKeyedServiceProvider returns null by default
        serviceProviderMock.As<IKeyedServiceProvider>();

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        // Act - should not throw (falls back to NoopAgentSessionStore)
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer("/api/agent", agent);

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public void MapAGUIServer_WithNullEndpoints_ThrowsArgumentNullException()
    {
        // Arrange
        AIAgent agent = new TestAgent();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            AGUIEndpointRouteBuilderExtensions.MapAGUIServer(null!, "/api/agent", agent));
    }

    [Fact]
    public void MapAGUIServer_WithNullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();
        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            endpointsMock.Object.MapAGUIServer("/api/agent", (AIAgent)null!));
    }

    [Fact]
    public void MapAGUIServer_WithNullAgentName_ThrowsArgumentNullException()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();
        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            endpointsMock.Object.MapAGUIServer((string)null!, "/api/agent"));
    }

    [Fact]
    public void MapAGUIServer_WithNullAgentBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            endpointsMock.Object.MapAGUIServer((IHostedAgentBuilder)null!, "/api/agent"));
    }

    [Fact]
    public void MapAGUIServer_WithFactoryDelegate_MapsEndpoint_AtSpecifiedPattern()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer(
            "test-agent", "/api/agent", static (_, _) => new NamedTestAgent());

        // Assert
        Assert.NotNull(result);
    }

    [Fact]
    public void MapAGUIServer_WithFactoryDelegate_DefersResolution_DoesNotInvokeFactoryAtMapTime()
    {
        // Arrange — the factory overload resolves the agent per request, so mapping must NOT invoke the
        // factory nor resolve a keyed AIAgent from DI (unlike the startup-capture agentName overload).
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        int factoryInvocations = 0;

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer(
            "test-agent",
            "/api/agent",
            (_, _) =>
            {
                factoryInvocations++;
                return new NamedTestAgent();
            });

        // Assert
        Assert.NotNull(result);
        Assert.Equal(0, factoryInvocations);
        serviceProviderMock.As<IKeyedServiceProvider>()
            .Verify(sp => sp.GetRequiredKeyedService(typeof(AIAgent), It.IsAny<object>()), Times.Never);
    }

    [Fact]
    public void MapAGUIServer_WithNullFactoryDelegate_ThrowsArgumentNullException()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();
        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            endpointsMock.Object.MapAGUIServer("test-agent", "/api/agent", (Func<IServiceProvider, string, AIAgent>)null!));
    }

    [Fact]
    public void MapAGUIServer_FactoryOverload_StableIdentity_ReportsAgentNameAcrossInnerInstances()
    {
        // Arrange — two per-request agent instances have distinct default ids (AIAgent.Id is per-instance).
        MarkerAgent inner1 = new();
        MarkerAgent inner2 = new();
        Assert.NotEqual(inner1.Id, inner2.Id);

        // Act — wrap each with a stable identity keyed by the logical agent name.
        StableIdentityAIAgent wrapped1 = new(inner1, "orders-agent");
        StableIdentityAIAgent wrapped2 = new(inner2, "orders-agent");

        // Assert — both report the stable name, so session keys stay constant across requests.
        Assert.Equal("orders-agent", wrapped1.Id);
        Assert.Equal(wrapped1.Id, wrapped2.Id);
    }

    [Fact]
    public async Task MapAGUIServer_FactoryOverload_PersistsSessionAcrossPerRequestAgentInstancesAsync()
    {
        // Arrange — the factory overload builds a fresh agent per request. The session store keys by
        // (agent.Id, conversationId), so a stable identity is required for AG-UI thread continuation to
        // recover the previously persisted session. This reproduces the two-turn flow.
        InMemoryAgentSessionStore store = new();
        const string AgentName = "orders-agent";
        const string ThreadId = "thread-1";

        // Turn 1: fresh per-request agent, wrapped with the stable identity, saves a marker.
        MarkerAgent turn1Inner = new();
        StableIdentityAIAgent turn1 = new(turn1Inner, AgentName);
        AgentSession session1 = await turn1.CreateSessionAsync();
        session1.StateBag.SetValue("marker", "persisted");
        await store.SaveSessionAsync(turn1, ThreadId, session1);

        // Turn 2: a different per-request agent instance, same logical name.
        MarkerAgent turn2Inner = new();
        Assert.NotEqual(turn1Inner.Id, turn2Inner.Id);
        StableIdentityAIAgent turn2 = new(turn2Inner, AgentName);

        // Act — recover the session for the same thread id through the second request's agent.
        AgentSession session2 = await store.GetSessionAsync(turn2, ThreadId);

        // Assert — the stable identity keeps the key constant, so turn 2 recovers turn 1's session.
        Assert.True(session2.StateBag.TryGetValue<string>("marker", out string? marker));
        Assert.Equal("persisted", marker);
    }

    [Fact]
    public async Task MapAGUIServer_FactoryOverload_WithoutStableIdentity_LosesSessionAcrossInstancesAsync()
    {
        // Arrange — demonstrates the failure mode the stable identity prevents: two raw per-request
        // agent instances have different ids, so the session store keys them separately.
        InMemoryAgentSessionStore store = new();
        const string ThreadId = "thread-1";

        MarkerAgent raw1 = new();
        AgentSession session1 = await raw1.CreateSessionAsync();
        session1.StateBag.SetValue("marker", "persisted");
        await store.SaveSessionAsync(raw1, ThreadId, session1);

        MarkerAgent raw2 = new();
        Assert.NotEqual(raw1.Id, raw2.Id);

        // Act
        AgentSession session2 = await store.GetSessionAsync(raw2, ThreadId);

        // Assert — the marker is lost because the per-instance id changed the session key.
        Assert.False(session2.StateBag.TryGetValue<string>("marker", out _));
    }

    private sealed class MarkerSession : AgentSession
    {
        public MarkerSession()
        {
        }

        public MarkerSession(AgentSessionStateBag stateBag)
            : base(stateBag)
        {
        }
    }

    private sealed class MarkerAgent : AIAgent
    {
        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new MarkerSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            new(session.StateBag.Serialize());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
            new(new MarkerSession(AgentSessionStateBag.Deserialize(serializedState)));

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();
    }

    private sealed class TestAgent : AIAgent
    {
        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) => throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }

    private sealed class NamedTestAgent : AIAgent
    {
        protected override string? IdCore => "named-test-agent";

        public override string? Name => "test-agent";

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) => throw new NotImplementedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) => throw new NotImplementedException();
    }
}
