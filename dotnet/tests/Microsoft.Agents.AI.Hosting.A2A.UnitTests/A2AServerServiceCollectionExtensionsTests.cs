// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AServerServiceCollectionExtensions"/> class.
/// </summary>
public sealed class A2AServerServiceCollectionExtensionsTests
{
    /// <summary>
    /// Verifies that AddA2AServer with an agent name registers a keyed A2AServer
    /// that can be resolved from the service provider.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithAgentName_ResolvesKeyedA2AServerAsync()
    {
        // Arrange
        const string AgentName = "test-agent";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMock(AgentName).Object);

        // Act
        services.AddA2AServer(AgentName);

        // Assert
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetKeyedService<A2AServer>(AgentName);
        Assert.NotNull(server);
    }

    /// <summary>
    /// Verifies that AddA2AServer with an agent instance registers a keyed A2AServer
    /// that can be resolved from the service provider using the agent's name.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithAgentInstance_ResolvesKeyedA2AServerAsync()
    {
        // Arrange
        const string AgentName = "instance-agent";
        var agentMock = CreateAgentMock(AgentName);
        var services = new ServiceCollection();

        // Act
        services.AddA2AServer(agentMock.Object);

        // Assert
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetKeyedService<A2AServer>(AgentName);
        Assert.NotNull(server);
    }

    /// <summary>
    /// Verifies that when no ITaskStore or AgentSessionStore are registered,
    /// AddA2AServer falls back to in-memory defaults and resolves successfully.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithNoCustomStores_FallsBackToInMemoryDefaultsAsync()
    {
        // Arrange
        const string AgentName = "default-stores-agent";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMock(AgentName).Object);

        // Act
        services.AddA2AServer(AgentName);

        // Assert - resolution succeeds without any stores registered
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetKeyedService<A2AServer>(AgentName);
        Assert.NotNull(server);
    }

    /// <summary>
    /// Verifies that when a custom ITaskStore is registered, AddA2AServer uses it
    /// instead of the default InMemoryTaskStore.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithCustomTaskStore_ResolvesSuccessfullyAsync()
    {
        // Arrange
        const string AgentName = "custom-taskstore-agent";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMock(AgentName).Object);

        var mockTaskStore = new Mock<ITaskStore>();
        services.AddKeyedSingleton(AgentName, mockTaskStore.Object);

        // Act
        services.AddA2AServer(AgentName);

        // Assert
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetKeyedService<A2AServer>(AgentName);
        Assert.NotNull(server);
    }

    /// <summary>
    /// Verifies that when a custom AgentSessionStore is registered, AddA2AServer uses it
    /// instead of the default InMemoryAgentSessionStore.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithCustomAgentSessionStore_ResolvesSuccessfullyAsync()
    {
        // Arrange
        const string AgentName = "custom-sessionstore-agent";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMock(AgentName).Object);

        var mockSessionStore = new Mock<AgentSessionStore>();
        services.AddKeyedSingleton(AgentName, mockSessionStore.Object);

        // Act
        services.AddA2AServer(AgentName);

        // Assert
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetKeyedService<A2AServer>(AgentName);
        Assert.NotNull(server);
    }

    /// <summary>
    /// Verifies that when a custom IAgentHandler is registered, AddA2AServer uses it
    /// instead of creating a default A2AAgentHandler.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithCustomAgentHandler_ResolvesSuccessfullyAsync()
    {
        // Arrange
        const string AgentName = "custom-handler-agent";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMock(AgentName).Object);

        var mockHandler = new Mock<IAgentHandler>();
        services.AddKeyedSingleton(AgentName, mockHandler.Object);

        // Act
        services.AddA2AServer(AgentName);

        // Assert
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetKeyedService<A2AServer>(AgentName);
        Assert.NotNull(server);
    }

    /// <summary>
    /// Verifies that the configureOptions callback is invoked when provided.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithConfigureOptions_InvokesCallbackAsync()
    {
        // Arrange
        const string AgentName = "options-agent";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMock(AgentName).Object);

        bool callbackInvoked = false;

        // Act
        services.AddA2AServer(AgentName, options =>
        {
            callbackInvoked = true;
            options.AgentRunMode = AgentRunMode.AllowBackgroundIfSupported;
        });

        // Assert - callback is invoked during resolution
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetKeyedService<A2AServer>(AgentName);
        Assert.NotNull(server);
        Assert.True(callbackInvoked);
    }

    /// <summary>
    /// Verifies that AddA2AServer with a null configureOptions does not throw.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithNullConfigureOptions_ResolvesSuccessfullyAsync()
    {
        // Arrange
        const string AgentName = "null-options-agent";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMock(AgentName).Object);

        // Act
        services.AddA2AServer(AgentName, configureOptions: null);

        // Assert
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetKeyedService<A2AServer>(AgentName);
        Assert.NotNull(server);
    }

    /// <summary>
    /// Verifies that AddA2AServer throws when the agent name is null.
    /// </summary>
    [Fact]
    public void AddA2AServer_WithNullAgentName_ThrowsArgumentException()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() => services.AddA2AServer(agentName: null!));
    }

    /// <summary>
    /// Verifies that AddA2AServer throws when the agent name is whitespace.
    /// </summary>
    [Fact]
    public void AddA2AServer_WithWhitespaceAgentName_ThrowsArgumentException()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() => services.AddA2AServer(agentName: "  "));
    }

    /// <summary>
    /// Verifies that AddA2AServer throws when the services parameter is null.
    /// </summary>
    [Fact]
    public void AddA2AServer_WithNullServices_ThrowsArgumentNullException()
    {
        // Arrange
        IServiceCollection services = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => services.AddA2AServer("agent"));
    }

    /// <summary>
    /// Verifies that AddA2AServer with an agent instance throws when the agent is null.
    /// </summary>
    [Fact]
    public void AddA2AServer_WithNullAgent_ThrowsArgumentNullException()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => services.AddA2AServer(agent: null!));
    }

    /// <summary>
    /// Verifies that AddA2AServer with an agent instance throws when the agent's Name is null.
    /// </summary>
    [Fact]
    public void AddA2AServer_WithAgent_NullName_ThrowsArgumentNullException()
    {
        // Arrange
        var services = new ServiceCollection();
        var agentMock = new Mock<AIAgent>();
        agentMock.Setup(a => a.Name).Returns((string?)null);

        // Act & Assert
        ArgumentNullException exception = Assert.Throws<ArgumentNullException>(() =>
            services.AddA2AServer(agentMock.Object));

        Assert.Equal("agent.Name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddA2AServer with an agent instance throws when the agent's Name is whitespace.
    /// </summary>
    [Fact]
    public void AddA2AServer_WithAgent_WhitespaceName_ThrowsArgumentException()
    {
        // Arrange
        var services = new ServiceCollection();
        var agentMock = new Mock<AIAgent>();
        agentMock.Setup(a => a.Name).Returns("   ");

        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() =>
            services.AddA2AServer(agentMock.Object));

        Assert.Equal("agent.Name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that when a custom <see cref="IAgentHandler"/> is registered as a keyed service,
    /// the <see cref="A2AServer"/> uses it to process requests instead of the default handler.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithCustomHandler_CustomHandlerIsInvokedOnRequestAsync()
    {
        // Arrange
        const string AgentName = "custom-handler-wiring";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMock(AgentName).Object);

        var mockHandler = new Mock<IAgentHandler>();
        mockHandler
            .Setup(h => h.ExecuteAsync(
                It.IsAny<RequestContext>(),
                It.IsAny<AgentEventQueue>(),
                It.IsAny<CancellationToken>()))
            .Returns((RequestContext _, AgentEventQueue eq, CancellationToken ct) =>
                eq.EnqueueMessageAsync(
                    new Message { MessageId = "resp", Role = Role.Agent, Parts = [new Part { Text = "Reply" }] }, ct).AsTask());

        services.AddKeyedSingleton(AgentName, mockHandler.Object);

        services.AddA2AServer(AgentName);
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetRequiredKeyedService<A2AServer>(AgentName);

        // Act
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var response = await server.SendMessageAsync(CreateTestSendMessageRequest(), cts.Token);

        // Assert - the custom handler was invoked, not the default A2AAgentHandler
        mockHandler.Verify(
            h => h.ExecuteAsync(
                It.IsAny<RequestContext>(),
                It.IsAny<AgentEventQueue>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
        Assert.Equal(SendMessageResponseCase.Message, response.PayloadCase);
        Assert.NotNull(response.Message);
    }

    /// <summary>
    /// Verifies that when a custom <see cref="AgentSessionStore"/> is registered as a keyed service
    /// and no custom <see cref="IAgentHandler"/> is registered, the default handler uses the custom
    /// session store for session management during request processing.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithCustomSessionStore_NoHandler_SessionStoreIsUsedOnRequestAsync()
    {
        // Arrange
        const string AgentName = "custom-sessionstore-wiring";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMock(AgentName).Object);

        var mockSessionStore = new Mock<AgentSessionStore>();
        mockSessionStore
            .Setup(x => x.GetSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new TestAgentSession());
        mockSessionStore
            .Setup(x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<string>(),
                It.IsAny<AgentSession>(),
                It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);

        services.AddKeyedSingleton(AgentName, mockSessionStore.Object);

        services.AddA2AServer(AgentName);
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetRequiredKeyedService<A2AServer>(AgentName);

        // Act
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var response = await server.SendMessageAsync(CreateTestSendMessageRequest(), cts.Token);

        // Assert - the custom session store was used, not InMemoryAgentSessionStore
        mockSessionStore.Verify(
            x => x.GetSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
        Assert.Equal(SendMessageResponseCase.Message, response.PayloadCase);
        Assert.NotNull(response.Message);
    }

    /// <summary>
    /// Verifies that when no custom stores or handlers are registered, the server uses
    /// the default in-memory stores and processes requests successfully end-to-end.
    /// </summary>
    [Fact]
    public async Task AddA2AServer_WithNoCustomStores_DefaultStoresProcessRequestSuccessfullyAsync()
    {
        // Arrange
        const string AgentName = "default-stores-request";
        var services = new ServiceCollection();
        services.AddKeyedSingleton(AgentName, (_, _) => CreateAgentMockForRequests(AgentName).Object);

        services.AddA2AServer(AgentName);
        await using var provider = services.BuildServiceProvider();
        var server = provider.GetRequiredKeyedService<A2AServer>(AgentName);

        // Act
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var response = await server.SendMessageAsync(CreateTestSendMessageRequest(), cts.Token);

        // Assert - request was processed successfully with default in-memory stores
        Assert.NotNull(response);
        Assert.Equal(SendMessageResponseCase.Message, response.PayloadCase);
        Assert.NotNull(response.Message);
    }

    private static SendMessageRequest CreateTestSendMessageRequest() =>
        new()
        {
            Message = new Message
            {
                MessageId = "test-id",
                Role = Role.User,
                Parts = [new Part { Text = "Hello" }]
            }
        };

    private static Mock<AIAgent> CreateAgentMock(string name)
    {
        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns(name);
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Test response")]));

        return agentMock;
    }

    /// <summary>
    /// Creates a mock <see cref="AIAgent"/> with session serialization support, suitable for
    /// tests that exercise the full request processing path with <see cref="InMemoryAgentSessionStore"/>.
    /// </summary>
    private static Mock<AIAgent> CreateAgentMockForRequests(string name)
    {
        Mock<AIAgent> agentMock = CreateAgentMock(name);
        agentMock
            .Protected()
            .Setup<ValueTask<JsonElement>>("SerializeSessionCoreAsync",
                ItExpr.IsAny<AgentSession>(),
                ItExpr.IsAny<JsonSerializerOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(JsonDocument.Parse("{}").RootElement);

        return agentMock;
    }

    private sealed class TestAgentSession : AgentSession;
}
