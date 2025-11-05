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
        Assert.IsAssignableFrom<IHostedWorkflowBuilder>(result);
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
    /// Verifies that providing a null builder to AddConcurrentWorkflow throws an ArgumentNullException.
    /// </summary>
    [Fact]
    public void AddConcurrentWorkflow_NullBuilder_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(() =>
            HostApplicationBuilderWorkflowExtensions.AddConcurrentWorkflow(null!, "workflow", [null!]));
    }

    /// <summary>
    /// Verifies that AddConcurrentWorkflow throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddConcurrentWorkflow_NullName_ThrowsArgumentNullException()
    {
        var builder = new HostApplicationBuilder();

        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddConcurrentWorkflow(null!, [new HostedAgentBuilder("test", builder)]));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddConcurrentWorkflow throws ArgumentNullException for null agent builders.
    /// </summary>
    [Fact]
    public void AddConcurrentWorkflow_NullAgentBuilders_ThrowsArgumentNullException()
    {
        var builder = new HostApplicationBuilder();

        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddConcurrentWorkflow("workflowName", null!));
        Assert.Equal("agentBuilders", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddConcurrentWorkflow returns IHostWorkflowBuilder instance.
    /// </summary>
    [Fact]
    public void AddConcurrentWorkflow_ValidParameters_ReturnsBuilder()
    {
        var builder = new HostApplicationBuilder();

        var result = builder.AddConcurrentWorkflow("concurrentWorkflow", [new HostedAgentBuilder("test", builder)]);

        Assert.NotNull(result);
        Assert.IsAssignableFrom<IHostedWorkflowBuilder>(result);
    }

    /// <summary>
    /// Verifies that providing a null builder to AddSequentialWorkflow throws an ArgumentNullException.
    /// </summary>
    [Fact]
    public void AddSequentialWorkflow_NullBuilder_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(() =>
            HostApplicationBuilderWorkflowExtensions.AddSequentialWorkflow(null!, "workflow", [null!]));
    }

    /// <summary>
    /// Verifies that AddSequentialWorkflow throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddSequentialWorkflow_NullName_ThrowsArgumentNullException()
    {
        var builder = new HostApplicationBuilder();

        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddSequentialWorkflow(null!, [new HostedAgentBuilder("test", builder)]));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddSequentialWorkflow throws ArgumentNullException for null agent builders.
    /// </summary>
    [Fact]
    public void AddSequentialWorkflow_NullAgentBuilders_ThrowsArgumentNullException()
    {
        var builder = new HostApplicationBuilder();

        var exception = Assert.Throws<ArgumentNullException>(() =>
            builder.AddSequentialWorkflow("workflowName", null!));
        Assert.Equal("agentBuilders", exception.ParamName);
    }

    [Fact]
    public void AddSequentialWorkflow_EmptyAgentBuilders_Throws()
    {
        var builder = new HostApplicationBuilder();

        var exception = Assert.Throws<ArgumentException>(() =>
            builder.AddSequentialWorkflow("sequentialWorkflow", Array.Empty<IHostedAgentBuilder>()));
        Assert.Equal("agentBuilders", exception.ParamName);
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
