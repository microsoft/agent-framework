// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
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
    public void MapAGUIServer_MarksFeatureUsed()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();
        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        // Act
        _ = endpointsMock.Object.MapAGUIServer("/api/agent", new TestAgent());

        // Assert
        AssertFeatureUsed(63);
    }

    private static void AssertFeatureUsed(int featureIndex)
    {
#pragma warning disable MAAI001
        string userAgent = FeatureUsage.ApplyToUserAgent(string.Empty);
#pragma warning restore MAAI001
        const string Prefix = "(feat=v1.";
        Assert.StartsWith(Prefix, userAgent);
        Assert.EndsWith(")", userAgent);

        string hexMask = userAgent[Prefix.Length..^1];
        int digitOffset = featureIndex / 4;
        Assert.True(hexMask.Length > digitOffset);
        char digit = char.ToLowerInvariant(hexMask[hexMask.Length - digitOffset - 1]);
        int nibble = digit <= '9' ? digit - '0' : digit - 'a' + 10;
        Assert.NotEqual(0, nibble & (1 << (featureIndex & 3)));
    }

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
    public void MapAGUIServer_WithAgentName_DoesNotResolveAgentAtMapTime()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer("test-agent", "/api/agent");

        // Assert
        Assert.NotNull(result);
        serviceProviderMock.As<IKeyedServiceProvider>()
            .Verify(sp => sp.GetRequiredKeyedService(typeof(AIAgent), It.IsAny<object?>()), Times.Never);
    }

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public void MapAGUIServer_WithNonSingletonHostedAgentBuilder_DoesNotResolveAgentAtMapTime(ServiceLifetime lifetime)
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        Mock<IHostedAgentBuilder> agentBuilderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();

        agentBuilderMock.Setup(b => b.Name).Returns("test-agent");
        agentBuilderMock.Setup(b => b.Lifetime).Returns(lifetime);

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer(agentBuilderMock.Object, "/api/agent");

        // Assert
        Assert.NotNull(result);
        serviceProviderMock.As<IKeyedServiceProvider>()
            .Verify(sp => sp.GetRequiredKeyedService(typeof(AIAgent), It.IsAny<object?>()), Times.Never);
    }

    [Fact]
    public void MapAGUIServer_WithSingletonHostedAgentBuilder_ResolvesAgentOnceAtMapTime()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        Mock<IHostedAgentBuilder> agentBuilderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>()
            .Setup(sp => sp.GetRequiredKeyedService(typeof(AIAgent), "test-agent"))
            .Returns(new NamedTestAgent());

        agentBuilderMock.Setup(b => b.Name).Returns("test-agent");
        agentBuilderMock.Setup(b => b.Lifetime).Returns(ServiceLifetime.Singleton);

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
    public void MapAGUIServer_WithAgent_DoesNotResolveSessionStoreAtMapTime()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        AIAgent agent = new NamedTestAgent();
        serviceProviderMock.As<IKeyedServiceProvider>();

        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer("/api/agent", agent);

        // Assert
        Assert.NotNull(result);
        serviceProviderMock.As<IKeyedServiceProvider>()
            .Verify(sp => sp.GetKeyedService(typeof(AgentSessionStore), It.IsAny<object?>()), Times.Never);
    }

    [Fact]
    public void MapAGUIServer_WithAgentSelector_DoesNotInvokeSelectorAtMapTime()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        serviceProviderMock.As<IKeyedServiceProvider>();
        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);
        endpointsMock.Setup(e => e.DataSources).Returns([]);
        int selectorInvocations = 0;

        // Act
        IEndpointConventionBuilder? result = endpointsMock.Object.MapAGUIServer("/api/{agentId}", _ =>
        {
            selectorInvocations++;
            return new NamedTestAgent();
        });

        // Assert
        Assert.NotNull(result);
        Assert.Equal(0, selectorInvocations);
    }

    [Fact]
    public void MapAGUIServer_WithNullAgentSelector_ThrowsArgumentNullException()
    {
        // Arrange
        Mock<IEndpointRouteBuilder> endpointsMock = new();
        Mock<IServiceProvider> serviceProviderMock = new();
        endpointsMock.Setup(e => e.ServiceProvider).Returns(serviceProviderMock.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            endpointsMock.Object.MapAGUIServer("/api/agent", (Func<HttpContext, AIAgent?>)null!));
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
