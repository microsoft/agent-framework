// Copyright (c) Microsoft. All rights reserved.

using System;
using A2A;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the A2AClientExtensions class.
/// </summary>
public sealed class A2AClientExtensionsTests
{
    [Fact]
    public void AsAIAgent_WithAllParameters_ReturnsA2AAgentWithSpecifiedProperties()
    {
        // Arrange
        var a2aClient = new A2AClient(new Uri("http://test-endpoint"));

        const string TestId = "test-agent-id";
        const string TestName = "Test Agent";
        const string TestDescription = "This is a test agent description";

        // Act
        var agent = a2aClient.AsAIAgent(TestId, TestName, TestDescription);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<A2AAgent>(agent);
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }

    [Fact]
    public void AsAIAgent_WithIA2AClient_ReturnsA2AAgentWithSpecifiedProperties()
    {
        // Arrange - use IA2AClient reference type to verify the extension method works with the interface
        IA2AClient a2aClient = new A2AClient(new Uri("http://test-endpoint"));

        const string TestId = "ia2a-agent-id";
        const string TestName = "IA2A Agent";
        const string TestDescription = "Agent created from IA2AClient";

        // Act
        var agent = a2aClient.AsAIAgent(TestId, TestName, TestDescription);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<A2AAgent>(agent);
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }

    [Fact]
    public void AsAIAgent_WithIA2AClient_ExposesClientViaGetService()
    {
        // Arrange
        IA2AClient a2aClient = new A2AClient(new Uri("http://test-endpoint"));

        // Act
        var agent = a2aClient.AsAIAgent();

        // Assert
        var service = agent.GetService(typeof(IA2AClient));
        Assert.NotNull(service);
        Assert.Same(a2aClient, service);
    }

    [Fact]
    public void AsAIAgent_WithOptions_ReturnsA2AAgentWithSpecifiedProperties()
    {
        // Arrange
        var a2aClient = new A2AClient(new Uri("http://test-endpoint"));
        var options = new A2AAgentOptions
        {
            Id = "options-agent-id",
            Name = "Options Agent",
            Description = "Agent created with options"
        };

        // Act
        var agent = a2aClient.AsAIAgent(options);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<A2AAgent>(agent);
        Assert.Equal("options-agent-id", agent.Id);
        Assert.Equal("Options Agent", agent.Name);
        Assert.Equal("Agent created with options", agent.Description);
    }

    [Fact]
    public void AsAIAgent_WithEmptyOptions_ReturnsA2AAgentWithDefaultProperties()
    {
        // Arrange
        var a2aClient = new A2AClient(new Uri("http://test-endpoint"));

        // Act
        var agent = a2aClient.AsAIAgent(new A2AAgentOptions());

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<A2AAgent>(agent);
        Assert.NotNull(agent.Id);
        Assert.NotEmpty(agent.Id);
        Assert.Null(agent.Name);
        Assert.Null(agent.Description);
    }
}
