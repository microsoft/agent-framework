// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

public class AgentHostingServiceCollectionExtensionsTests
{
    /// <summary>
    /// Verifies that providing a null builder to AddAIAgent throws an ArgumentNullException.
    /// </summary>
    [Fact]
    public void AddAIAgent_NullBuilder_ThrowsArgumentNullException() => Assert.Throws<ArgumentNullException>(
        () => AgentHostingServiceCollectionExtensions.AddAIAgent(null!, "agent", "instructions"));

    /// <summary>
    /// Verifies that AddAIAgent without chat client key throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddAIAgent_NullName_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();

        var exception = Assert.Throws<ArgumentNullException>(() => services.AddAIAgent(null!, "instructions"));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent without chat client key allows null instructions.
    /// </summary>
    [Fact]
    public void AddAIAgent_NullInstructions_AllowsNull()
    {
        var services = new ServiceCollection();
        var result = services.AddAIAgent("agentName", (string)null!);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddAIAgent with chat client key throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddAIAgentWithKey_NullName_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        var exception = Assert.Throws<ArgumentNullException>(() => services.AddAIAgent(null!, "instructions", "key"));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent with chat client key allows null instructions.
    /// </summary>
    [Fact]
    public void AddAIAgentWithKey_NullInstructions_AllowsNull()
    {
        var services = new ServiceCollection();
        var result = services.AddAIAgent("agentName", null!, "key");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate throws ArgumentNullException for null builder.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_NullBuilder_ThrowsArgumentNullException() =>
        Assert.Throws<ArgumentNullException>(() =>
            AgentHostingServiceCollectionExtensions.AddAIAgent(null!, "agentName", (sp, key) => new Mock<AIAgent>().Object));

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_NullName_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        var exception = Assert.Throws<ArgumentNullException>(() => services.AddAIAgent(null!, (sp, key) => new Mock<AIAgent>().Object));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate throws ArgumentNullException for null factory.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_NullFactory_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();
        var exception = Assert.Throws<ArgumentNullException>(() => services.AddAIAgent("agentName", (Func<IServiceProvider, string, AIAgent>)null!));
        Assert.Equal("createAgentDelegate", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate returns the same builder instance.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_ValidParameters_ReturnsBuilder()
    {
        var services = new ServiceCollection();
        var mockAgent = new Mock<AIAgent>();
        var result = services.AddAIAgent("agentName", (sp, key) => mockAgent.Object);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddAIAgent registers the agent as a keyed singleton service.
    /// </summary>
    [Fact]
    public void AddAIAgent_RegistersKeyedSingleton()
    {
        var services = new ServiceCollection();
        var mockAgent = new Mock<AIAgent>();
        const string AgentName = "testAgent";

        services.AddAIAgent(AgentName, (sp, key) => mockAgent.Object);

        var descriptor = services.FirstOrDefault(
            d => (d.ServiceKey as string) == AgentName &&
                 d.ServiceType == typeof(AIAgent));

        Assert.NotNull(descriptor);
        Assert.Equal(ServiceLifetime.Singleton, descriptor.Lifetime);
    }

    /// <summary>
    /// Verifies that AddAIAgent can be called multiple times with different agent names.
    /// </summary>
    [Fact]
    public void AddAIAgent_MultipleCalls_RegistersMultipleAgents()
    {
        var services = new ServiceCollection();

        services.AddAIAgent("agent1", "instructions1");
        services.AddAIAgent("agent2", "instructions2");
        services.AddAIAgent("agent3", "instructions3");

        var agentDescriptors = services
            .Where(d => d.ServiceType == typeof(AIAgent) && d.ServiceKey is string)
            .ToList();

        Assert.Equal(3, agentDescriptors.Count);
        Assert.Contains(agentDescriptors, d => (string)d.ServiceKey! == "agent1");
        Assert.Contains(agentDescriptors, d => (string)d.ServiceKey! == "agent2");
        Assert.Contains(agentDescriptors, d => (string)d.ServiceKey! == "agent3");
    }

    /// <summary>
    /// Verifies that AddAIAgent handles empty strings for name.
    /// </summary>
    [Fact]
    public void AddAIAgent_EmptyName_ThrowsArgumentException()
    {
        var services = new ServiceCollection();
        Assert.Throws<ArgumentException>(() => services.AddAIAgent("", "instructions"));
    }

    /// <summary>
    /// Verifies that AddAIAgent allows empty strings for instructions.
    /// </summary>
    [Fact]
    public void AddAIAgent_EmptyInstructions_Succeeds()
    {
        var services = new ServiceCollection();
        var result = services.AddAIAgent("agentName", "");
        Assert.NotNull(result);
    }
    /// <summary>
    /// Verifies that AddAIAgent without chat client key calls the overload with null key.
    /// </summary>
    [Fact]
    public void AddAIAgent_WithoutKey_CallsOverloadWithNullKey()
    {
        var builder = new HostApplicationBuilder();
        var result = builder.AddAIAgent("agentName", "instructions");

        // The agent should be registered (proving the method chain worked)
        var descriptor = builder.Services.FirstOrDefault(
            d => d.ServiceKey is "agentName" &&
                 d.ServiceType == typeof(AIAgent));
        Assert.NotNull(descriptor);
    }

    /// <summary>
    /// Verifies that AddAIAgent with special characters in name works correctly for valid names.
    /// </summary>
    [Theory]
    [InlineData("agent_name")] // underscore is allowed
    [InlineData("Agent123")] // alphanumeric is allowed
    [InlineData("_agent")] // can start with underscore
    [InlineData("agent-name")] // dash is allowed
    [InlineData("agent.name")] // period is allowed
    [InlineData("agent:type")] // colon is allowed
    [InlineData("my.agent_1:type-name")] // complex valid name
    public void AddAIAgent_ValidSpecialCharactersInName_Succeeds(string name)
    {
        var builder = new HostApplicationBuilder();
        var result = builder.AddAIAgent(name, "instructions");

        var descriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == name &&
                 d.ServiceType == typeof(AIAgent));
        Assert.NotNull(descriptor);
    }
}
