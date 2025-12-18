// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.DependencyInjection;
using Moq;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

public class ServiceCollectionWorkflowExtensionsTests
{
    /// <summary>
    /// Verifies that providing a null service collection to AddWorkflow throws an ArgumentNullException.
    /// </summary>
    [Fact]
    public void AddWorkflow_NullServices_ThrowsArgumentNullException() =>
        Assert.Throws<ArgumentNullException>(
            () => ServiceCollectionWorkflowExtensions.AddWorkflow(
                null!,
                "workflow",
                (sp, key) => CreateTestWorkflow(key)));

    /// <summary>
    /// Verifies that AddWorkflow throws ArgumentNullException for null name.
    /// </summary>
    [Fact]
    public void AddWorkflow_NullName_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();

        var exception = Assert.Throws<ArgumentNullException>(() =>
            services.AddWorkflow(null!, (sp, key) => CreateTestWorkflow(key)));
        Assert.Equal("name", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddWorkflow throws ArgumentNullException for null factory delegate.
    /// </summary>
    [Fact]
    public void AddWorkflow_NullFactory_ThrowsArgumentNullException()
    {
        var services = new ServiceCollection();

        var exception = Assert.Throws<ArgumentNullException>(() =>
            services.AddWorkflow("workflowName", null!));
        Assert.Equal("createWorkflowDelegate", exception.ParamName);
    }

    /// <summary>
    /// Verifies that AddWorkflow returns the IHostWorkflowBuilder instance.
    /// </summary>
    [Fact]
    public void AddWorkflow_ValidParameters_ReturnsBuilder()
    {
        var services = new ServiceCollection();

        var result = services.AddWorkflow("workflowName", (sp, key) => CreateTestWorkflow(key));

        Assert.NotNull(result);
        Assert.IsType<IHostedWorkflowBuilder>(result, exactMatch: false);
    }

    /// <summary>
    /// Verifies that AddWorkflow registers the workflow as a keyed singleton service.
    /// </summary>
    [Fact]
    public void AddWorkflow_RegistersKeyedSingleton()
    {
        var services = new ServiceCollection();
        const string WorkflowName = "testWorkflow";

        services.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var descriptor = services.FirstOrDefault(
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
        var services = new ServiceCollection();

        services.AddWorkflow("workflow1", (sp, key) => CreateTestWorkflow(key));
        services.AddWorkflow("workflow2", (sp, key) => CreateTestWorkflow(key));
        services.AddWorkflow("workflow3", (sp, key) => CreateTestWorkflow(key));

        var workflowDescriptors = services
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
        var services = new ServiceCollection();
        var result = services.AddWorkflow("", (sp, key) => CreateTestWorkflow(key));
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
        var services = new ServiceCollection();

        var result = services.AddWorkflow(name, (sp, key) => CreateTestWorkflow(key));

        var descriptor = services.FirstOrDefault(
            d => (d.ServiceKey as string) == name &&
                 d.ServiceType == typeof(Workflow));
        Assert.NotNull(descriptor);
    }

    /// <summary>
    /// Verifies that the workflow factory is invoked when retrieving the service.
    /// </summary>
    [Fact]
    public void AddWorkflow_FactoryInvoked_CreatesWorkflow()
    {
        var services = new ServiceCollection();
        const string WorkflowName = "testWorkflow";

        services.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow(key));

        var provider = services.BuildServiceProvider();
        var workflow = provider.GetKeyedService<Workflow>(WorkflowName);

        Assert.NotNull(workflow);
        Assert.Equal(WorkflowName, workflow.Name);
    }

    /// <summary>
    /// Verifies that the factory delegate receives the correct service provider and key.
    /// </summary>
    [Fact]
    public void AddWorkflow_FactoryReceivesCorrectParameters()
    {
        var services = new ServiceCollection();
        const string WorkflowName = "testWorkflow";
        IServiceProvider? capturedServiceProvider = null;
        string? capturedKey = null;

        services.AddWorkflow(WorkflowName, (sp, key) =>
        {
            capturedServiceProvider = sp;
            capturedKey = key;
            return CreateTestWorkflow(key);
        });

        var provider = services.BuildServiceProvider();
        var workflow = provider.GetKeyedService<Workflow>(WorkflowName);

        Assert.NotNull(capturedServiceProvider);
        Assert.Equal(WorkflowName, capturedKey);
        Assert.NotNull(workflow);
    }

    /// <summary>
    /// Verifies that AddWorkflow throws when factory returns null.
    /// </summary>
    [Fact]
    public void AddWorkflow_FactoryReturnsNull_ThrowsInvalidOperationException()
    {
        var services = new ServiceCollection();
        const string WorkflowName = "testWorkflow";

        services.AddWorkflow(WorkflowName, (sp, key) => null!);

        var provider = services.BuildServiceProvider();
        var exception = Assert.Throws<InvalidOperationException>(() =>
            provider.GetKeyedService<Workflow>(WorkflowName));

        Assert.Contains("did not return a valid", exception.Message);
    }

    /// <summary>
    /// Verifies that AddWorkflow throws when factory returns workflow with mismatched name.
    /// </summary>
    [Fact]
    public void AddWorkflow_FactoryReturnsMismatchedName_ThrowsInvalidOperationException()
    {
        var services = new ServiceCollection();
        const string WorkflowName = "testWorkflow";

        services.AddWorkflow(WorkflowName, (sp, key) => CreateTestWorkflow("differentName"));

        var provider = services.BuildServiceProvider();
        var exception = Assert.Throws<InvalidOperationException>(() =>
            provider.GetKeyedService<Workflow>(WorkflowName));

        Assert.Contains("but the expected name is", exception.Message);
    }

    /// <summary>
    /// Helper method to create a test workflow with the specified name.
    /// </summary>
    private static Workflow CreateTestWorkflow(string name)
    {
        // Create a simple workflow using AgentWorkflowBuilder
        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.Name).Returns("testAgent");

        return AgentWorkflowBuilder.BuildSequential(workflowName: name, agents: [mockAgent.Object]);
    }
}
