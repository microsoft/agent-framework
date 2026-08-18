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
