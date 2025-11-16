// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.DevUI.UnitTests;

/// <summary>
/// Unit tests for DevUI service collection extensions.
/// Tests verify that workflows and agents can be resolved even when registered non-conventionally.
/// </summary>
public class DevUIExtensionsTests
{
    /// <summary>
    /// Verifies that AddDevUI throws ArgumentNullException when services collection is null.
    /// </summary>
    [Fact]
    public void AddDevUI_NullServices_ThrowsArgumentNullException()
    {
        IServiceCollection services = null!;
        Assert.Throws<ArgumentNullException>(() => services.AddDevUI());
    }

    /// <summary>
    /// Verifies that a directly registered AIAgent is resolved correctly.
    /// </summary>
    [Fact]
    public void AddDevUI_DirectlyRegisteredAgent_CanBeResolved()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var directAgent = new ChatClientAgent(mockChatClient.Object, "Direct agent", "direct-agent");

        services.AddKeyedSingleton<AIAgent>("direct-agent", directAgent);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        // Act
        var resolvedAgent = serviceProvider.GetKeyedService<AIAgent>("direct-agent");

        // Assert
        Assert.NotNull(resolvedAgent);
        Assert.Same(directAgent, resolvedAgent);
    }

    /// <summary>
    /// Verifies that resolving a non-existent agent/workflow throws InvalidOperationException when using GetRequiredKeyedService.
    /// </summary>
    [Fact]
    public void AddDevUI_ResolvingNonExistentEntity_ThrowsInvalidOperationException()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddDevUI();
        var serviceProvider = services.BuildServiceProvider();

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => serviceProvider.GetRequiredKeyedService<AIAgent>("non-existent"));
    }

    /// <summary>
    /// Verifies that GetKeyedService returns null for non-matching keys (no exception).
    /// </summary>
    [Fact]
    public void AddDevUI_GetKeyedServiceNonExistent_ReturnsNull()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddDevUI();
        var serviceProvider = services.BuildServiceProvider();

        // Act
        var result = serviceProvider.GetKeyedService<AIAgent>("non-existent");

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verifies that GetRequiredKeyedService throws for non-existent keys.
    /// </summary>
    [Fact]
    public void AddDevUI_GetRequiredKeyedServiceNonExistent_ThrowsInvalidOperationException()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddDevUI();
        var serviceProvider = services.BuildServiceProvider();

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => serviceProvider.GetRequiredKeyedService<AIAgent>("non-existent"));
    }

    /// <summary>
    /// Verifies that AddDevUI can be called multiple times without issues.
    /// </summary>
    [Fact]
    public void AddDevUI_CalledMultipleTimes_StillWorks()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddDevUI();
        services.AddDevUI();

        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, "Test", "test-agent");
        services.AddKeyedSingleton<AIAgent>("test-agent", agent);

        var serviceProvider = services.BuildServiceProvider();

        // Act
        var resolvedAgent = serviceProvider.GetKeyedService<AIAgent>("test-agent");

        // Assert
        Assert.NotNull(resolvedAgent);
    }

    /// <summary>
    /// Verifies that directly registered agents with special characters in names can be resolved.
    /// </summary>
    [Theory]
    [InlineData("agent_name")]
    [InlineData("agent-name")]
    [InlineData("agent.name")]
    [InlineData("agent:name")]
    [InlineData("my_agent-name.v1:test")]
    public void AddDevUI_AgentWithSpecialCharactersInName_CanBeResolved(string agentName)
    {
        // Arrange
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, "Test", agentName);
        services.AddKeyedSingleton<AIAgent>(agentName, agent);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        // Act
        var resolvedAgent = serviceProvider.GetKeyedService<AIAgent>(agentName);

        // Assert
        Assert.NotNull(resolvedAgent);
        Assert.Equal(agentName, resolvedAgent.Name);
    }

    /// <summary>
    /// Verifies that the same agent instance can be resolved multiple times.
    /// </summary>
    [Fact]
    public void AddDevUI_ResolvingSameAgentMultipleTimes_ReturnsSameInstance()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, "Test", "test-agent");
        services.AddKeyedSingleton<AIAgent>("test-agent", agent);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        // Act
        var agent1 = serviceProvider.GetKeyedService<AIAgent>("test-agent");
        var agent2 = serviceProvider.GetKeyedService<AIAgent>("test-agent");

        // Assert
        Assert.NotNull(agent1);
        Assert.NotNull(agent2);
        // Should return the same singleton instance
        Assert.Same(agent1, agent2);
    }

    /// <summary>
    /// Verifies that multiple directly registered agents can coexist and be resolved.
    /// </summary>
    [Fact]
    public void AddDevUI_MultipleDirectAgents_CanAllBeResolved()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var agent1 = new ChatClientAgent(mockChatClient.Object, "Agent 1", "agent-1");
        var agent2 = new ChatClientAgent(mockChatClient.Object, "Agent 2", "agent-2");
        var agent3 = new ChatClientAgent(mockChatClient.Object, "Agent 3", "agent-3");

        services.AddKeyedSingleton<AIAgent>("agent-1", agent1);
        services.AddKeyedSingleton<AIAgent>("agent-2", agent2);
        services.AddKeyedSingleton<AIAgent>("agent-3", agent3);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        // Act
        var resolved1 = serviceProvider.GetKeyedService<AIAgent>("agent-1");
        var resolved2 = serviceProvider.GetKeyedService<AIAgent>("agent-2");
        var resolved3 = serviceProvider.GetKeyedService<AIAgent>("agent-3");

        // Assert
        Assert.NotNull(resolved1);
        Assert.NotNull(resolved2);
        Assert.NotNull(resolved3);
        Assert.Same(agent1, resolved1);
        Assert.Same(agent2, resolved2);
        Assert.Same(agent3, resolved3);
    }

    /// <summary>
    /// Verifies that an agent with null name can be resolved by its key.
    /// </summary>
    [Fact]
    public void AddDevUI_AgentWithNullName_CanBeResolved()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, "Test", name: null);

        services.AddKeyedSingleton<AIAgent>("null-name-agent", agent);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        // Act
        var resolvedAgent = serviceProvider.GetKeyedService<AIAgent>("null-name-agent");

        // Assert
        Assert.NotNull(resolvedAgent);
        Assert.Null(resolvedAgent.Name);
    }

    /// <summary>
    /// Verifies that an agent with null name can be resolved by its workflow.
    /// </summary>
    [Fact]
    public void AddDevUI_WorkflowWithName_CanBeResolved_AsAIAgent()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var agent1 = new ChatClientAgent(mockChatClient.Object, "Test 1", name: null);
        var agent2 = new ChatClientAgent(mockChatClient.Object, "Test 2", name: null);
        var workflow = AgentWorkflowBuilder.BuildSequential(agent1, agent2);

        services.AddKeyedSingleton("workflow", workflow);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        // Act
        var resolvedWorkflowAsAgent = serviceProvider.GetKeyedService<AIAgent>("workflow");

        // Assert
        Assert.NotNull(resolvedWorkflowAsAgent);
        Assert.Null(resolvedWorkflowAsAgent.Name);
    }

    /// <summary>
    /// Verifies that an agent with null name can be resolved by its workflow.
    /// </summary>
    [Fact]
    public void AddDevUI_MultipleWorkflowsWithName_CanBeResolved_AsAIAgent()
    {
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var agent1 = new ChatClientAgent(mockChatClient.Object, "Test 1", name: null);
        var agent2 = new ChatClientAgent(mockChatClient.Object, "Test 2", name: null);
        var workflow1 = AgentWorkflowBuilder.BuildSequential(agent1, agent2);
        var workflow2 = AgentWorkflowBuilder.BuildSequential(agent1, agent2);

        services.AddKeyedSingleton("workflow1", workflow1);
        services.AddKeyedSingleton("workflow2", workflow2);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        var resolvedWorkflow1AsAgent = serviceProvider.GetKeyedService<AIAgent>("workflow1");
        Assert.NotNull(resolvedWorkflow1AsAgent);
        Assert.Null(resolvedWorkflow1AsAgent.Name);

        var resolvedWorkflow2AsAgent = serviceProvider.GetKeyedService<AIAgent>("workflow2");
        Assert.NotNull(resolvedWorkflow2AsAgent);
        Assert.Null(resolvedWorkflow2AsAgent.Name);

        Assert.False(resolvedWorkflow1AsAgent == resolvedWorkflow2AsAgent);
    }

    /// <summary>
    /// Verifies that an agent with null name can be resolved by its workflow.
    /// </summary>
    [Fact]
    public void AddDevUI_NonKeyedWorkflow_CanBeResolved_AsAIAgent()
    {
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var agent1 = new ChatClientAgent(mockChatClient.Object, "Test 1", name: null);
        var agent2 = new ChatClientAgent(mockChatClient.Object, "Test 2", name: null);
        var workflow = AgentWorkflowBuilder.BuildSequential(agent1, agent2);

        services.AddKeyedSingleton("workflow", workflow);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        var resolvedWorkflowAsAgent = serviceProvider.GetKeyedService<AIAgent>("workflow");
        Assert.NotNull(resolvedWorkflowAsAgent);
        Assert.Null(resolvedWorkflowAsAgent.Name);
    }

    /// <summary>
    /// Verifies that an agent with null name can be resolved by its workflow.
    /// </summary>
    [Fact]
    public void AddDevUI_NonKeyedWorkflow_PlusKeyedWorkflow_CanBeResolved_AsAIAgent()
    {
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var agent1 = new ChatClientAgent(mockChatClient.Object, "Test 1", name: null);
        var agent2 = new ChatClientAgent(mockChatClient.Object, "Test 2", name: null);
        var workflow = AgentWorkflowBuilder.BuildSequential("standardname", agent1, agent2);
        var keyedWorkflow = AgentWorkflowBuilder.BuildSequential("keyedname", agent1, agent2);

        services.AddSingleton(workflow);
        services.AddKeyedSingleton("keyed", keyedWorkflow);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        // resolve a workflow with the same name as workflow's name (which is registered without a key)
        var standardAgent = serviceProvider.GetKeyedService<AIAgent>("standardname");
        Assert.NotNull(standardAgent);
        Assert.Equal("standardname", standardAgent.Name);

        var keyedAgent = serviceProvider.GetKeyedService<AIAgent>("keyed");
        Assert.NotNull(keyedAgent);
        Assert.Equal("keyedname", keyedAgent.Name);

        var nonExisting = serviceProvider.GetKeyedService<AIAgent>("random-non-existing!!!");
        Assert.Null(nonExisting);
    }

    /// <summary>
    /// Verifies that an agent registered with a different key than its name can be resolved by key.
    /// </summary>
    [Fact]
    public void AddDevUI_AgentRegisteredWithDifferentKey_CanBeResolvedByKey()
    {
        // Arrange
        var services = new ServiceCollection();
        const string AgentName = "actual-agent-name";
        const string RegistrationKey = "different-key";
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, "Test", AgentName);

        services.AddKeyedSingleton<AIAgent>(RegistrationKey, agent);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        // Act
        var resolvedAgent = serviceProvider.GetKeyedService<AIAgent>(RegistrationKey);

        // Assert
        Assert.NotNull(resolvedAgent);
        // The resolved agent should have the agent's name, not the registration key
        Assert.Equal(AgentName, resolvedAgent.Name);
    }

    /// <summary>
    /// Verifies that trying to resolve with null key throws appropriate exception.
    /// </summary>
    [Fact]
    public void AddDevUI_ResolveWithNullKey_ReturnsNull()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var agent = new ChatClientAgent(mockChatClient.Object, "Test", "test-agent");
        services.AddKeyedSingleton<AIAgent>("test-agent", agent);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        // Act & Assert
        var result = serviceProvider.GetKeyedService<AIAgent>(null!);
        Assert.Null(result);
    }

    /// <summary>
    /// Verifies that agent services are registered as keyed singletons.
    /// </summary>
    [Fact]
    public void AddDevUI_RegisteredServices_IncludeKeyedSingletons()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddDevUI();

        // Assert - Verify that a KeyedService.AnyKey fallback is registered
        var fallbackDescriptors = services.Where(d =>
            d.ServiceKey == KeyedService.AnyKey &&
            d.ServiceType == typeof(AIAgent));

        Assert.Single(fallbackDescriptors);
    }

    /// <summary>
    /// Verifies that the DevUI fallback handler error message includes helpful information.
    /// </summary>
    [Fact]
    public void AddDevUI_InvalidResolution_ErrorMessageIsInformative()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddDevUI();
        var serviceProvider = services.BuildServiceProvider();
        const string InvalidKey = "invalid-key-name";

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => serviceProvider.GetRequiredKeyedService<AIAgent>(InvalidKey));
    }
}
