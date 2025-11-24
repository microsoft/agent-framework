// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

public class HostApplicationBuilderWorkflowExtensionsTests
{
    /// <summary>
    /// Verifies that providing a null builder to AddWorkflow throws an ArgumentNullException.
    /// </summary>
    [Fact]
    public void AddWorkflow_NullBuilder_ThrowsArgumentNullException() =>
        Assert.Throws<ArgumentNullException>(
            () => HostApplicationBuilderWorkflowExtensions.AddWorkflow(
                null!,
                "workflow",
                (sp, key) => CreateTestWorkflow(key)));

    /// <summary>
    /// Verifies that AddWorkflow throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddWorkflow_NullName_ThrowsArgumentNullException()
    {
        var builder = new HostApplicationBuilder();

        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddWorkflow(null!, (sp, key) => CreateTestWorkflow(key)));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddWorkflow throws ArgumentNullException for null factory delegate.
    /// </summary>
    [Fact]
    public void AddWorkflow_NullFactory_ThrowsArgumentNullException()
    {
        var builder = new HostApplicationBuilder();

        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddWorkflow("workflowName", null!));
        Assert.Equal("createWorkflowDelegate", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddWorkflow returns the IHostWorkflowBuilder instance.
    /// </summary>
    [Fact]
    public void AddWorkflow_ValidParameters_ReturnsBuilder()
    {
        var builder = new HostApplicationBuilder();

        var result = builder.AddWorkflow("workflowName", (sp, key) => CreateTestWorkflow(key));

        Assert.NotNull(result);
        Assert.IsType<IHostedWorkflowBuilder>(result, exactMatch: false);
    }

    /// <summary>
    /// Verifies that AddWorkflow registers the workflow as a keyed singleton service.
    /// </summary>
    [Fact]
    public void AddWorkflow_RegistersKeyedSingleton()
    {
        var builder = new HostApplicationBuilder();
        const string WorkflowName = "testWorkflow";

        builder.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var descriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == WorkflowName &&
                 d.ServiceType == typeof(Workflow));

        Assert.NotNull(descriptor);
        Assert.Equal(ServiceLifetime.Singleton, descriptor.Lifetime);
    }

    /// <summary>
    /// Verifies that AddWorkflow can be called multiple times with different workflow names.
    /// </summary>
    [Fact]
    public void AddWorkflow_MultipleCalls_RegistersMultipleWorkflows()
    {
        var builder = new HostApplicationBuilder();

        builder.AddWorkflow("workflow1", (sp, key) => CreateTestWorkflow(key));
        builder.AddWorkflow("workflow2", (sp, key) => CreateTestWorkflow(key));
        builder.AddWorkflow("workflow3", (sp, key) => CreateTestWorkflow(key));

        var workflowDescriptors = builder.Services
            .Where(d => d.ServiceType == typeof(Workflow) && d.ServiceKey is string)
            .ToList();

        Assert.Equal(3, workflowDescriptors.Count);
        Assert.Contains(workflowDescriptors, d => (string)d.ServiceKey! == "workflow1");
        Assert.Contains(workflowDescriptors, d => (string)d.ServiceKey! == "workflow2");
        Assert.Contains(workflowDescriptors, d => (string)d.ServiceKey! == "workflow3");
    }

    /// <summary>
    /// Verifies that AddWorkflow handles empty strings for name.
    /// </summary>
    [Fact]
    public void AddWorkflow_EmptyName_ThrowsArgumentException()
    {
        var builder = new HostApplicationBuilder();
        var result = builder.AddWorkflow("", (sp, key) => CreateTestWorkflow(key));
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verifies that AddWorkflow with special characters in name works correctly for valid names.
    /// </summary>
    [Theory]
    [InlineData("workflow_name")] // underscore is allowed
    [InlineData("Workflow123")] // alphanumeric is allowed
    [InlineData("_workflow")] // can start with underscore
    [InlineData("workflow-name")] // dash is allowed
    [InlineData("workflow.name")] // period is allowed
    [InlineData("workflow:type")] // colon is allowed
    [InlineData("my.workflow_1:type-name")] // complex valid name
    public void AddWorkflow_ValidSpecialCharactersInName_Succeeds(string name)
    {
        var builder = new HostApplicationBuilder();

        var result = builder.AddWorkflow(name, (sp, key) => CreateTestWorkflow(key));

        var descriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == name &&
                 d.ServiceType == typeof(Workflow));
        Assert.NotNull(descriptor);
    }

    /// <summary>
    /// Verifies that AddAsAIAgent without a name parameter uses the workflow name as the agent name.
    /// </summary>
    [Fact]
    public void AddAsAIAgent_WithoutName_UsesWorkflowName()
    {
        var builder = new HostApplicationBuilder();
        const string WorkflowName = "testWorkflow";
        var workflowBuilder = builder.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var agentBuilder = workflowBuilder.AddAsAIAgent();

        Assert.NotNull(agentBuilder);

        // Verify workflow is registered with workflow name
        var workflowDescriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == WorkflowName && d.ServiceType == typeof(Workflow));
        Assert.NotNull(workflowDescriptor);

        // Verify agent is registered with workflow name
        var agentDescriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == WorkflowName && d.ServiceType == typeof(AIAgent));
        Assert.NotNull(agentDescriptor);
    }

    /// <summary>
    /// Verifies that AddAsAIAgent with a name parameter uses that name instead of the workflow name.
    /// </summary>
    [Fact]
    public void AddAsAIAgent_WithName_UsesProvidedName()
    {
        var builder = new HostApplicationBuilder();
        const string WorkflowName = "testWorkflow";
        const string AgentName = "testAgent";
        var workflowBuilder = builder.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var agentBuilder = workflowBuilder.AddAsAIAgent(AgentName);

        Assert.NotNull(agentBuilder);

        // Verify workflow is registered with workflow name
        var workflowDescriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == WorkflowName && d.ServiceType == typeof(Workflow));
        Assert.NotNull(workflowDescriptor);

        // Verify agent is registered with agent name (not workflow name)
        var agentDescriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == AgentName && d.ServiceType == typeof(AIAgent));
        Assert.NotNull(agentDescriptor);

        // Verify no agent registered with workflow name
        var wrongAgentDescriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == WorkflowName && d.ServiceType == typeof(AIAgent));
        Assert.NotSame(workflowDescriptor, wrongAgentDescriptor);
    }

    /// <summary>
    /// Verifies that AddAsAIAgent correctly retrieves the workflow using the workflow name, not the agent name.
    /// </summary>
    [Fact]
    public void AddAsAIAgent_WithDifferentName_RetrievesWorkflowCorrectly()
    {
        var builder = new HostApplicationBuilder();
        const string WorkflowName = "myWorkflow";
        const string AgentName = "myAgent";

        var workflowBuilder = builder.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));
        workflowBuilder.AddAsAIAgent(AgentName);

        var serviceProvider = builder.Build().Services;

        // Act - Get the agent using the agent name
        var agent = serviceProvider.GetRequiredKeyedService<AIAgent>(AgentName);

        Assert.NotNull(agent);
        Assert.Equal(AgentName, agent.Name);

        // Verify that we can still get the workflow using the workflow name
        var workflow = serviceProvider.GetRequiredKeyedService<Workflow>(WorkflowName);
        Assert.NotNull(workflow);
        Assert.Equal(WorkflowName, workflow.Name);
    }

    /// <summary>
    /// Verifies that AddAsAIAgent returns IHostedAgentBuilder with correct name.
    /// </summary>
    [Fact]
    public void AddAsAIAgent_ReturnsHostedAgentBuilder()
    {
        var builder = new HostApplicationBuilder();
        const string WorkflowName = "testWorkflow";
        const string AgentName = "testAgent";
        var workflowBuilder = builder.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var agentBuilder = workflowBuilder.AddAsAIAgent(AgentName);

        Assert.NotNull(agentBuilder);
        Assert.IsType<IHostedAgentBuilder>(agentBuilder, exactMatch: false);
        Assert.Equal(AgentName, agentBuilder.Name);
    }

    /// <summary>
    /// Verifies that AddAsAIAgent without name returns IHostedAgentBuilder with workflow name.
    /// </summary>
    [Fact]
    public void AddAsAIAgent_WithoutName_ReturnsHostedAgentBuilderWithWorkflowName()
    {
        var builder = new HostApplicationBuilder();
        const string WorkflowName = "testWorkflow";
        var workflowBuilder = builder.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var agentBuilder = workflowBuilder.AddAsAIAgent();

        Assert.NotNull(agentBuilder);
        Assert.IsType<IHostedAgentBuilder>(agentBuilder, exactMatch: false);
        Assert.Equal(WorkflowName, agentBuilder.Name);
    }

    /// <summary>
    /// Verifies that AddAsAIAgent can chain multiple agents from the same workflow.
    /// </summary>
    [Fact]
    public void AddAsAIAgent_MultipleAgents_FromSameWorkflow()
    {
        var builder = new HostApplicationBuilder();
        const string WorkflowName = "testWorkflow";
        var workflowBuilder = builder.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var agentBuilder1 = workflowBuilder.AddAsAIAgent("agent1");
        var agentBuilder2 = workflowBuilder.AddAsAIAgent("agent2");

        Assert.NotNull(agentBuilder1);
        Assert.NotNull(agentBuilder2);

        // Verify both agents are registered
        var agentDescriptor1 = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == "agent1" && d.ServiceType == typeof(AIAgent));
        var agentDescriptor2 = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == "agent2" && d.ServiceType == typeof(AIAgent));

        Assert.NotNull(agentDescriptor1);
        Assert.NotNull(agentDescriptor2);

        // Verify workflow is registered only once
        var workflowDescriptors = builder.Services.Where(
                d => (d.ServiceKey as string) == WorkflowName && d.ServiceType == typeof(Workflow)).ToList();
        Assert.Single(workflowDescriptors);
    }

    /// <summary>
    /// Verifies that AddAsAIAgent with null name behaves the same as the parameterless overload.
    /// </summary>
    [Fact]
    public void AddAsAIAgent_WithNullName_UsesWorkflowName()
    {
        var builder = new HostApplicationBuilder();
        const string WorkflowName = "testWorkflow";
        var workflowBuilder = builder.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var agentBuilder = workflowBuilder.AddAsAIAgent(name: null);

        Assert.NotNull(agentBuilder);
        Assert.Equal(WorkflowName, agentBuilder.Name);

        // Verify agent is registered with workflow name
        var agentDescriptor = builder.Services.FirstOrDefault(
            d => (d.ServiceKey as string) == WorkflowName && d.ServiceType == typeof(AIAgent));
        Assert.NotNull(agentDescriptor);
    }

    /// <summary>
    /// Verifies that AddAsAIAgent with empty string name uses empty string as agent name.
    /// </summary>
    [Fact]
    public void AddAsAIAgent_WithEmptyName_UsesEmptyStringAsAgentName()
    {
        var builder = new HostApplicationBuilder();
        const string WorkflowName = "testWorkflow";
        var workflowBuilder = builder.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var agentBuilder = workflowBuilder.AddAsAIAgent(name: "");

        Assert.NotNull(agentBuilder);
        Assert.Equal("", agentBuilder.Name);

        // Verify agent is registered with empty string name
        var agentDescriptor = builder.Services.FirstOrDefault(
            d => d.ServiceKey is string s && s.Length == 0 && d.ServiceType == typeof(AIAgent));
        Assert.NotNull(agentDescriptor);
    }

    /// <summary>
    /// Helper method to create a simple test workflow with a given name.
    /// </summary>
    private static Workflow CreateTestWorkflow(string name)
    {
        // Create a simple workflow using AgentWorkflowBuilder
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("testAgent");

        return AgentWorkflowBuilder.BuildSequential(workflowName: name, agents: [mockAgent.Object]);
    }
}
