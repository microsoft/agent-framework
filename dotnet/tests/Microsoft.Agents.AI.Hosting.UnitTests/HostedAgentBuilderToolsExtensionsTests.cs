// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for AI tool registration extensions on <see cref="IHostedAgentBuilder"/>.
/// </summary>
public sealed class HostedAgentBuilderToolsExtensionsTests
{
    [Fact]
    public void WithAITool_ThrowsWhenBuilderIsNull()
    {
        // Arrange
        var tool = new DummyAITool();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => HostedAgentBuilderExtensions.WithAITool(null!, tool));
    }

    [Fact]
    public void WithAITool_ThrowsWhenToolIsNull()
    {
        // Arrange
        var services = new ServiceCollection();
        var builder = services.AddAIAgent("test-agent", "Test instructions");

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.WithAITool(null!));
    }

    [Fact]
    public void WithAITools_ThrowsWhenBuilderIsNull()
    {
        // Arrange
        var tools = new[] { new DummyAITool() };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => HostedAgentBuilderExtensions.WithAITools(null!, tools));
    }

    [Fact]
    public void WithAITools_ThrowsWhenToolsArrayIsNull()
    {
        // Arrange
        var services = new ServiceCollection();
        var builder = services.AddAIAgent("test-agent", "Test instructions");

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.WithAITools(null!));
    }

    [Fact]
    public void RegisteredTools_ResolvesAllToolsForAgent()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddSingleton<IChatClient>(new MockChatClient());

        var builder = services.AddAIAgent("test-agent", "Test instructions");
        var tool1 = new DummyAITool();
        var tool2 = new DummyAITool();

        builder
            .WithAITool(tool1)
            .WithAITool(tool2);

        var serviceProvider = services.BuildServiceProvider();

        var agent1Tools = ResolveAgentTools(serviceProvider, "test-agent");
        Assert.Contains(tool1, agent1Tools);
        Assert.Contains(tool2, agent1Tools);
    }

    [Fact]
    public void RegisteredTools_IsolatedPerAgent()
    {
        var services = new ServiceCollection();
        services.AddSingleton<IChatClient>(new MockChatClient());

        var builder1 = services.AddAIAgent("agent1", "Agent 1 instructions");
        var builder2 = services.AddAIAgent("agent2", "Agent 2 instructions");

        var tool1 = new DummyAITool();
        var tool2 = new DummyAITool();
        var tool3 = new DummyAITool();

        builder1
            .WithAITool(tool1)
            .WithAITool(tool2);

        builder2
            .WithAITool(tool3);

        var serviceProvider = services.BuildServiceProvider();

        var agent1Tools = ResolveAgentTools(serviceProvider, "agent1");
        var agent2Tools = ResolveAgentTools(serviceProvider, "agent2");

        Assert.Contains(tool1, agent1Tools);
        Assert.Contains(tool2, agent1Tools);
        Assert.Contains(tool3, agent2Tools);
    }

    private static IList<AITool> ResolveAgentTools(IServiceProvider serviceProvider, string name)
    {
        var agent = serviceProvider.GetRequiredKeyedService<AIAgent>(name) as ChatClientAgent;
        Assert.NotNull(agent?.ChatOptions?.Tools);
        return agent.ChatOptions.Tools;
    }

    /// <summary>
    /// Dummy AITool implementation for testing.
    /// </summary>
    private sealed class DummyAITool : AITool
    {
    }

    /// <summary>
    /// Mock chat client for testing.
    /// </summary>
    private sealed class MockChatClient : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            throw new NotImplementedException();
        }

        public object? GetService(Type serviceType, object? serviceKey = null)
        {
            return null;
        }

        public void Dispose()
        {
            throw new NotImplementedException();
        }
    }
}
