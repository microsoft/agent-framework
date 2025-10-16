// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

public class HostApplicationBuilderAgentExtensionsTests
{
    /// <summary>
    /// Verifies that providing a null builder to AddAIAgent throws an ArgumentNullException.
    /// </summary>
    [Fact]
    public void AddAIAgent_NullBuilder_ThrowsArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(
            () => HostApplicationBuilderAgentExtensions.AddAIAgent(null!, "agent", "instructions"));

    /// <summary>
    /// Verifies that AddAIAgent without chat client key throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddAIAgent_NullName_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = new HostApplicationBuilder();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddAIAgent(null!, "instructions"));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent without chat client key allows null instructions.
    /// </summary>
    [Fact]
    public void AddAIAgent_NullInstructions_AllowsNull()
    {
        var builder = new HostApplicationBuilder();
        var result = builder.AddAIAgent("agentName", (string)null!);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddAIAgent with chat client key throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddAIAgentWithKey_NullName_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = new HostApplicationBuilder();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddAIAgent(null!, "instructions", "key"));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent with chat client key allows null instructions.
    /// </summary>
    [Fact]
    public void AddAIAgentWithKey_NullInstructions_AllowsNull()
    {
        var builder = new HostApplicationBuilder();
        var result = builder.AddAIAgent("agentName", null!, "key");
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate throws ArgumentNullException for null builder.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_NullBuilder_ThrowsArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            HostApplicationBuilderAgentExtensions.AddAIAgent(
                null!,
                "agentName",
                (sp, key) => new Mock<AIAgent>().Object));

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_NullName_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = new HostApplicationBuilder();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddAIAgent(null!, (sp, key) => new Mock<AIAgent>().Object));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate throws ArgumentNullException for null factory.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_NullFactory_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = new HostApplicationBuilder();

        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddAIAgent("agentName", (Func<IServiceProvider, string, AIAgent>)null!));
        Assert.Equal("createAgentDelegate", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddAIAgent with factory delegate returns the same builder instance.
    /// </summary>
    [Fact]
    public void AddAIAgentWithFactory_ValidParameters_ReturnsBuilder()
    {
        var builder = new HostApplicationBuilder();
        var mockAgent = new Mock<AIAgent>();
        var result = builder.AddAIAgent("agentName", (sp, key) => mockAgent.Object);

        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddAIAgent registers the agent as a keyed singleton service.
    /// </summary>
    [Fact]
    public void AddAIAgent_RegistersKeyedSingleton()
    {
        // Arrange
        var builder = new HostApplicationBuilder();
        var mockAgent = new Mock<AIAgent>();
        const string AgentName = "testAgent";

        // Act
        builder.AddAIAgent(AgentName, (sp, key) => mockAgent.Object);

        // Assert
        var descriptor = builder.Services.FirstOrDefault(
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
        // Arrange
        var builder = new HostApplicationBuilder();

        // Act
        builder.AddAIAgent("agent1", "instructions1");
        builder.AddAIAgent("agent2", "instructions2");
        builder.AddAIAgent("agent3", "instructions3");

        // Assert
        var agentDescriptors = builder.Services
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
        // Arrange
        var builder = new HostApplicationBuilder();

        // Act & Assert
        Assert.Throws<ArgumentException>(() =>
            builder.AddAIAgent("", "instructions"));
    }

    /// <summary>
    /// Verifies that AddAIAgent allows empty strings for instructions.
    /// </summary>
    [Fact]
    public void AddAIAgent_EmptyInstructions_Succeeds()
    {
        var builder = new HostApplicationBuilder();
        var result = builder.AddAIAgent("agentName", "");
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
