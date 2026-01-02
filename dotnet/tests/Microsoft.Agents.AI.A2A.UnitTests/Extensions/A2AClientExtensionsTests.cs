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
    public void GetAIAgent_WithAllParameters_ReturnsA2AAgentWithSpecifiedProperties()
    {
        // Arrange
        var a2aClient = new A2AClient(new Uri("http://test-endpoint"));

        const string TestId = "test-agent-id";
        const string TestName = "Test Agent";
        const string TestDescription = "This is a test agent description";

        // Act
        var agent = a2aClient.GetAIAgent(TestId, TestName, TestDescription);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<A2AAgent>(agent);
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }
}
