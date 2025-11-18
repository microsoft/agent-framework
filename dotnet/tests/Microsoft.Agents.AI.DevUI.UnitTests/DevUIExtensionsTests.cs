// Copyright (c) Microsoft. All rights reserved.

using System;
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
    /// Verifies that an agent registered with a different key than its name can be resolved by key.
    /// </summary>
    [Fact]
    public void AddDevUI_Keyed_AndStandard_BothCanBeResolved()
    {
        // Arrange
        var services = new ServiceCollection();
        var mockChatClient = new Mock<IChatClient>();
        var defaultAgent = new ChatClientAgent(mockChatClient.Object, "default", "default");
        var keyedAgent = new ChatClientAgent(mockChatClient.Object, "keyed", "keyed");

        services.AddSingleton<AIAgent>(defaultAgent);
        services.AddKeyedSingleton<AIAgent>("keyed-registration", keyedAgent);
        services.AddDevUI();

        var serviceProvider = services.BuildServiceProvider();

        var resolvedKeyedAgent = serviceProvider.GetKeyedService<AIAgent>("keyed-registration");
        Assert.NotNull(resolvedKeyedAgent);
        Assert.Equal("keyed", resolvedKeyedAgent.Name);

        // resolving default agent based on its name, not on the registration-key
        var resolvedDefaultAgent = serviceProvider.GetKeyedService<AIAgent>("default");
        Assert.NotNull(resolvedDefaultAgent);
        Assert.Equal("default", resolvedDefaultAgent.Name);
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
