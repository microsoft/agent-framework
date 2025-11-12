// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Specialized;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public sealed class WorkflowHostExecutorTests
{
    [Fact]
    public async Task ForwardWorkflowEventAsync_WithAutoYieldOutputHandlerResultObjectTrue_YieldsOutput()
    {
        // Arrange
        const string testData = "test output data";
        WorkflowOutputEvent outputEvent = new(testData, "SubworkflowExecutor");

        TestRunContext testContext = new();

        ExecutorOptions options = new()
        {
            AutoSendMessageHandlerResultObject = false,
            AutoYieldOutputHandlerResultObject = true
        };

        Workflow emptyWorkflow = new WorkflowBuilder(new SimpleTestExecutor("start")).Build();
        TestableWorkflowHostExecutor hostExecutor = new("TestHost", emptyWorkflow, "run1", new object(), options);

        await hostExecutor.AttachSuperStepContextAsync(testContext);

        // Act
        await hostExecutor.SimulateForwardWorkflowEventAsync(outputEvent);

        // Assert
        testContext.Events.OfType<WorkflowOutputEvent>().Should().HaveCount(1, "YieldOutputAsync should create one WorkflowOutputEvent");
        WorkflowOutputEvent? yieldedEvent = testContext.Events.OfType<WorkflowOutputEvent>().FirstOrDefault();
        yieldedEvent.Should().NotBeNull();
        yieldedEvent!.SourceId.Should().Be("TestHost");
        yieldedEvent.As<string>().Should().Be(testData);

        testContext.QueuedMessages.Should().BeEmpty("SendMessageAsync should not be called");
    }

    [Fact]
    public async Task ForwardWorkflowEventAsync_WithAutoSendMessageHandlerResultObjectTrue_SendsMessage()
    {
        // Arrange
        const string testData = "test output data";
        WorkflowOutputEvent outputEvent = new(testData, "SubworkflowExecutor");

        TestRunContext testContext = new();

        ExecutorOptions options = new()
        {
            AutoSendMessageHandlerResultObject = true,
            AutoYieldOutputHandlerResultObject = false
        };

        Workflow emptyWorkflow = new WorkflowBuilder(new SimpleTestExecutor("start")).Build();
        TestableWorkflowHostExecutor hostExecutor = new("TestHost", emptyWorkflow, "run1", new object(), options);

        await hostExecutor.AttachSuperStepContextAsync(testContext);

        // Act
        await hostExecutor.SimulateForwardWorkflowEventAsync(outputEvent);

        // Assert
        testContext.QueuedMessages.Should().ContainKey("TestHost");
        testContext.QueuedMessages["TestHost"].Should().HaveCount(1);
        testContext.QueuedMessages["TestHost"][0].Message.Should().Be(testData);

        testContext.Events.OfType<WorkflowOutputEvent>().Should().BeEmpty("YieldOutputAsync should not be called");
    }

    [Fact]
    public async Task ForwardWorkflowEventAsync_WithBothOptionsFalse_DoesNothing()
    {
        // Arrange
        const string testData = "test output data";
        WorkflowOutputEvent outputEvent = new(testData, "SubworkflowExecutor");

        TestRunContext testContext = new();

        ExecutorOptions options = new()
        {
            AutoSendMessageHandlerResultObject = false,
            AutoYieldOutputHandlerResultObject = false
        };

        Workflow emptyWorkflow = new WorkflowBuilder(new SimpleTestExecutor("start")).Build();
        TestableWorkflowHostExecutor hostExecutor = new("TestHost", emptyWorkflow, "run1", new object(), options);

        await hostExecutor.AttachSuperStepContextAsync(testContext);

        // Act
        await hostExecutor.SimulateForwardWorkflowEventAsync(outputEvent);

        // Assert
        testContext.QueuedMessages.Should().BeEmpty("SendMessageAsync should not be called");
        testContext.Events.OfType<WorkflowOutputEvent>().Should().BeEmpty("YieldOutputAsync should not be called");
    }

    [Fact]
    public async Task ForwardWorkflowEventAsync_WithNullOutputData_DoesNothing()
    {
        // Arrange
        WorkflowOutputEvent outputEvent = new(null!, "SubworkflowExecutor");

        TestRunContext testContext = new();

        ExecutorOptions options = new()
        {
            AutoSendMessageHandlerResultObject = false,
            AutoYieldOutputHandlerResultObject = true
        };

        Workflow emptyWorkflow = new WorkflowBuilder(new SimpleTestExecutor("start")).Build();
        TestableWorkflowHostExecutor hostExecutor = new("TestHost", emptyWorkflow, "run1", new object(), options);

        await hostExecutor.AttachSuperStepContextAsync(testContext);

        // Act
        await hostExecutor.SimulateForwardWorkflowEventAsync(outputEvent);

        // Assert
        testContext.Events.OfType<WorkflowOutputEvent>().Should().BeEmpty("YieldOutputAsync should not be called when data is null");
        testContext.QueuedMessages.Should().BeEmpty("SendMessageAsync should not be called when data is null");
    }

    /// <summary>
    /// Simple executor for testing that doesn't require type parameters.
    /// </summary>
    private sealed class SimpleTestExecutor : Executor
    {
        public SimpleTestExecutor(string id) : base(id)
        {
        }

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) => routeBuilder;
    }

    /// <summary>
    /// Testable wrapper for WorkflowHostExecutor that exposes internal methods for testing.
    /// </summary>
    private sealed class TestableWorkflowHostExecutor : WorkflowHostExecutor
    {
        public TestableWorkflowHostExecutor(string id, Workflow workflow, string runId, object ownershipToken, ExecutorOptions? options = null)
            : base(id, workflow, runId, ownershipToken, options)
        {
        }

        public async ValueTask SimulateForwardWorkflowEventAsync(WorkflowEvent evt)
        {
            // Use reflection to invoke the private ForwardWorkflowEventAsync method
            System.Reflection.MethodInfo? method = typeof(WorkflowHostExecutor)
                .GetMethod("ForwardWorkflowEventAsync", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);

            if (method != null)
            {
                object? result = method.Invoke(this, [null, evt]);
                if (result is ValueTask valueTask)
                {
                    await valueTask;
                }
            }
        }
    }
}
