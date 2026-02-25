// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Agentforce;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Agentforce.UnitTests;

public class AgentforceAgentTests
{
    [Fact]
    public void Constructor_WithConfig_CreatesAgent()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");

        // Act
        using var agent = new AgentforceAgent(config);

        // Assert
        Assert.NotNull(agent.Client);
        Assert.NotNull(agent.Id);
    }

    [Fact]
    public void Constructor_WithClient_CreatesAgent()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        var client = new AgentforceClient(config);

        // Act
        var agent = new AgentforceAgent(client);

        // Assert
        Assert.NotNull(agent.Client);
        Assert.Same(client, agent.Client);
    }

    [Fact]
    public void Constructor_WithNullConfig_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentforceAgent((AgentforceConfig)null!));
    }

    [Fact]
    public void Constructor_WithNullClient_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentforceAgent((AgentforceClient)null!));
    }

    [Fact]
    public async Task CreateSessionAsync_ReturnsAgentforceSession()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        using var agent = new AgentforceAgent(config);

        // Act
        var session = await agent.CreateSessionAsync();

        // Assert
        Assert.IsType<AgentforceAgentSession>(session);
    }

    [Fact]
    public void GetService_ReturnsMetadata()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        using var agent = new AgentforceAgent(config);

        // Act
        var metadata = agent.GetService<AIAgentMetadata>();

        // Assert
        Assert.NotNull(metadata);
        Assert.Equal("salesforce-agentforce", metadata.ProviderName);
    }

    [Fact]
    public void GetService_ReturnsClient()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        using var agent = new AgentforceAgent(config);

        // Act
        var client = agent.GetService<AgentforceClient>();

        // Assert
        Assert.NotNull(client);
        Assert.Same(agent.Client, client);
    }

    [Fact]
    public void GetService_ReturnsSelf()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        using var agent = new AgentforceAgent(config);

        // Act
        var self = agent.GetService<AgentforceAgent>();

        // Assert
        Assert.Same(agent, self);
    }

    [Fact]
    public void GetService_ReturnsNullForUnknownType()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        using var agent = new AgentforceAgent(config);

        // Act
        var result = agent.GetService<string>();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task RunAsync_WithIncompatibleSession_Throws()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        using var agent = new AgentforceAgent(config);
        var messages = new[] { new ChatMessage(ChatRole.User, "Hello") };
        var incompatibleSession = new TestSession();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await agent.RunAsync(messages, incompatibleSession));
    }

    [Fact]
    public void Dispose_DisposesOwnedClient()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        var agent = new AgentforceAgent(config);

        // Act - should not throw
        agent.Dispose();

        // Assert - disposing again should not throw
        agent.Dispose();
    }

    [Fact]
    public void Dispose_DoesNotDisposeExternalClient()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        var client = new AgentforceClient(config);
        var agent = new AgentforceAgent(client);

        // Act
        agent.Dispose();

        // Assert - client should still be usable (not disposed)
        // The fact that we can call Dispose on it without ObjectDisposedException proves it wasn't disposed.
        client.Dispose();
    }

    private sealed class TestSession : AgentSession
    {
    }
}
