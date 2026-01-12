// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
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
        var tool = new DummyAITool();

        Assert.Throws<ArgumentNullException>(() => HostedAgentBuilderExtensions.WithAITool(null!, tool));
    }

    [Fact]
    public void WithAITool_ThrowsWhenToolIsNull()
    {
        var services = new ServiceCollection();
        var builder = services.AddAIAgent("test-agent", "Test instructions");

        Assert.Throws<ArgumentNullException>(() => builder.WithAITool(tool: null!));
    }

    [Fact]
    public void WithAITools_ThrowsWhenBuilderIsNull()
    {
        var tools = new[] { new DummyAITool() };

        Assert.Throws<ArgumentNullException>(() => HostedAgentBuilderExtensions.WithAITools(null!, tools));
    }

    [Fact]
    public void WithAITools_ThrowsWhenToolsArrayIsNull()
    {
        var services = new ServiceCollection();
        var builder = services.AddAIAgent("test-agent", "Test instructions");

        Assert.Throws<ArgumentNullException>(() => builder.WithAITools(null!));
    }

    [Fact]
    public void RegisteredTools_ResolvesAllToolsForAgent()
    {
        var services = new ServiceCollection();
        services.AddSingleton<IChatClient>(new MockChatClient());

        var builder = services.AddAIAgent("test-agent", "Test instructions");
        var tool1 = new DummyAITool();
        var tool2 = new DummyAITool();

        builder
            .WithAITool(tool1)
            .WithAITool(tool2);

        var serviceProvider = services.BuildServiceProvider();

        var agent1Tools = ResolveToolsFromAgent(serviceProvider, "test-agent");
        Assert.Contains(tool1, agent1Tools);
        Assert.Contains(tool2, agent1Tools);

        var agent1ToolsDI = ResolveToolsFromDI(serviceProvider, "test-agent");
        Assert.Contains(tool1, agent1ToolsDI);
        Assert.Contains(tool2, agent1ToolsDI);
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

        var agent1Tools = ResolveToolsFromAgent(serviceProvider, "agent1");
        var agent2Tools = ResolveToolsFromAgent(serviceProvider, "agent2");

        var agent1ToolsDI = ResolveToolsFromDI(serviceProvider, "agent1");
        var agent2ToolsDI = ResolveToolsFromDI(serviceProvider, "agent2");

        Assert.Contains(tool1, agent1Tools);
        Assert.Contains(tool2, agent1Tools);
        Assert.Contains(tool1, agent1ToolsDI);
        Assert.Contains(tool2, agent1ToolsDI);

        Assert.Contains(tool3, agent2Tools);
        Assert.Contains(tool3, agent2ToolsDI);
    }

    private static IList<AITool> ResolveToolsFromAgent(IServiceProvider serviceProvider, string name)
    {
        var agent = serviceProvider.GetRequiredKeyedService<AIAgent>(name) as ChatClientAgent;
        Assert.NotNull(agent?.ChatOptions?.Tools);
        return agent.ChatOptions.Tools;
    }

    private static List<AITool> ResolveToolsFromDI(IServiceProvider serviceProvider, string name)
    {
        var tools = serviceProvider.GetKeyedServices<AITool>(name);
        Assert.NotNull(tools);
        return tools.ToList();
    }

    [Fact]
    public void WithAIToolFactory_ThrowsWhenBuilderIsNull()
    {
        Assert.Throws<ArgumentNullException>(() => HostedAgentBuilderExtensions.WithAITool(null!, CreateTool));

        static AITool CreateTool(IServiceProvider _) => new DummyAITool();
    }

    [Fact]
    public void WithAIToolFactory_ThrowsWhenFactoryIsNull()
    {
        var services = new ServiceCollection();
        var builder = services.AddAIAgent("test-agent", "Test instructions");

        Assert.Throws<ArgumentNullException>(() => builder.WithAITool(factory: null!));
    }

    [Fact]
    public void WithAIToolFactory_RegistersToolFromFactory()
    {
        var services = new ServiceCollection();
        services.AddSingleton<IChatClient>(new MockChatClient());

        DummyAITool? createdTool = null;
        var builder = services.AddAIAgent("test-agent", "Test instructions");
        builder.WithAITool(sp =>
        {
            createdTool = new DummyAITool();
            return createdTool;
        });

        var serviceProvider = services.BuildServiceProvider();
        var tools = ResolveToolsFromDI(serviceProvider, "test-agent");

        Assert.Single(tools);
        Assert.Same(createdTool, tools[0]);
    }

    [Fact]
    public void WithAIToolFactory_CanAccessServicesFromFactory()
    {
        var services = new ServiceCollection();
        var mockChatClient = new MockChatClient();
        services.AddSingleton<IChatClient>(mockChatClient);

        IChatClient? resolvedChatClient = null;
        var builder = services.AddAIAgent("test-agent", "Test instructions");
        builder.WithAITool(sp =>
        {
            resolvedChatClient = sp.GetService<IChatClient>();
            return new DummyAITool();
        });

        var serviceProvider = services.BuildServiceProvider();
        _ = ResolveToolsFromDI(serviceProvider, "test-agent");

        Assert.Same(mockChatClient, resolvedChatClient);
    }

    [Fact]
    public void WithAIToolFactory_ToolsAreIsolatedPerAgent()
    {
        var services = new ServiceCollection();
        services.AddSingleton<IChatClient>(new MockChatClient());

        var tool1 = new DummyAITool();
        var tool2 = new DummyAITool();

        var builder1 = services.AddAIAgent("agent1", "Agent 1 instructions");
        var builder2 = services.AddAIAgent("agent2", "Agent 2 instructions");

        builder1.WithAITool(_ => tool1);
        builder2.WithAITool(_ => tool2);

        var serviceProvider = services.BuildServiceProvider();
        var agent1Tools = ResolveToolsFromDI(serviceProvider, "agent1");
        var agent2Tools = ResolveToolsFromDI(serviceProvider, "agent2");

        Assert.Single(agent1Tools);
        Assert.Contains(tool1, agent1Tools);
        Assert.DoesNotContain(tool2, agent1Tools);

        Assert.Single(agent2Tools);
        Assert.Contains(tool2, agent2Tools);
        Assert.DoesNotContain(tool1, agent2Tools);
    }

    [Fact]
    public void WithAIToolFactory_CanCombineWithDirectToolRegistration()
    {
        var services = new ServiceCollection();
        services.AddSingleton<IChatClient>(new MockChatClient());

        var directTool = new DummyAITool();
        var factoryTool = new DummyAITool();

        var builder = services.AddAIAgent("test-agent", "Test instructions");
        builder
            .WithAITool(directTool)
            .WithAITool(_ => factoryTool);

        var serviceProvider = services.BuildServiceProvider();
        var tools = ResolveToolsFromDI(serviceProvider, "test-agent");

        Assert.Equal(2, tools.Count);
        Assert.Contains(directTool, tools);
        Assert.Contains(factoryTool, tools);
    }

    [Fact]
    public void WithAIToolFactory_ToolsAvailableOnAgent()
    {
        var services = new ServiceCollection();
        services.AddSingleton<IChatClient>(new MockChatClient());

        var factoryTool = new DummyAITool();
        var builder = services.AddAIAgent("test-agent", "Test instructions");
        builder.WithAITool(_ => factoryTool);

        var serviceProvider = services.BuildServiceProvider();
        var agentTools = ResolveToolsFromAgent(serviceProvider, "test-agent");

        Assert.Contains(factoryTool, agentTools);
    }

    /// <summary>
    /// Dummy AITool implementation for testing.
    /// </summary>
    private sealed class DummyAITool : AITool;

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
