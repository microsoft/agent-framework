// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Behaviors;

namespace Microsoft.Agents.AI.Workflows.UnitTests.Behaviors;

/// <summary>
/// Tests for the WorkflowBehaviorOptions API and registration mechanisms.
/// </summary>
public class WorkflowBehaviorOptionsTests
{
    [Fact]
    public void AddExecutorBehavior_WithInstance_RegistersBehavior()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var behavior = new TestExecutorBehavior();

        // Act
        options.AddExecutorBehavior(behavior);
        var pipeline = options.BuildPipeline();

        // Assert
        pipeline.Should().NotBeNull();
        pipeline!.HasExecutorBehaviors.Should().BeTrue();
    }

    [Fact]
    public void AddWorkflowBehavior_WithInstance_RegistersBehavior()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var behavior = new TestWorkflowBehavior();

        // Act
        options.AddWorkflowBehavior(behavior);
        var pipeline = options.BuildPipeline();

        // Assert
        pipeline.Should().NotBeNull();
        pipeline!.HasWorkflowBehaviors.Should().BeTrue();
    }

    [Fact]
    public void AddExecutorBehavior_MultipleInstances_RegistersAllBehaviors()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var behavior1 = new TestExecutorBehavior();
        var behavior2 = new TestExecutorBehavior();
        var behavior3 = new TestExecutorBehavior();

        // Act
        options.AddExecutorBehavior(behavior1);
        options.AddExecutorBehavior(behavior2);
        options.AddExecutorBehavior(behavior3);
        var pipeline = options.BuildPipeline();

        // Assert
        pipeline.Should().NotBeNull();
        pipeline!.HasExecutorBehaviors.Should().BeTrue();
    }

    [Fact]
    public void AddWorkflowBehavior_MultipleInstances_RegistersAllBehaviors()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var behavior1 = new TestWorkflowBehavior();
        var behavior2 = new TestWorkflowBehavior();

        // Act
        options.AddWorkflowBehavior(behavior1);
        options.AddWorkflowBehavior(behavior2);
        var pipeline = options.BuildPipeline();

        // Assert
        pipeline.Should().NotBeNull();
        pipeline!.HasWorkflowBehaviors.Should().BeTrue();
    }

    [Fact]
    public void BuildPipeline_WithNoBehaviors_ReturnsEmptyPipeline()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();

        // Act
        var pipeline = options.BuildPipeline();

        // Assert
        pipeline.Should().NotBeNull();
        pipeline!.HasExecutorBehaviors.Should().BeFalse();
        pipeline.HasWorkflowBehaviors.Should().BeFalse();
    }

    [Fact]
    public async Task WorkflowBuilder_WithBehaviors_ConfiguresBehaviorsAsync()
    {
        // Arrange
        var behavior = new TestExecutorBehavior();
        var executor = new SimpleExecutor("test");

        // Act
        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options => options.AddExecutorBehavior(behavior))
            .Build();

        // Assert
        workflow.Should().NotBeNull();
        workflow.BehaviorPipeline.Should().NotBeNull();
        workflow.BehaviorPipeline!.HasExecutorBehaviors.Should().BeTrue();
    }

    [Fact]
    public async Task WorkflowBuilder_WithBehaviors_SupportsFluentAPIAsync()
    {
        // Arrange
        var executor = new SimpleExecutor("test");

        // Act
        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options =>
            {
                options.AddExecutorBehavior(new TestExecutorBehavior());
                options.AddWorkflowBehavior(new TestWorkflowBehavior());
            })
            .Build();

        // Assert
        workflow.Should().NotBeNull();
        workflow.BehaviorPipeline.Should().NotBeNull();
        workflow.BehaviorPipeline!.HasExecutorBehaviors.Should().BeTrue();
        workflow.BehaviorPipeline.HasWorkflowBehaviors.Should().BeTrue();
    }

    [Fact]
    public async Task WorkflowBuilder_WithoutBehaviors_HasNullPipelineAsync()
    {
        // Arrange
        var executor = new SimpleExecutor("test");

        // Act
        var workflow = new WorkflowBuilder(executor).Build();

        // Assert
        workflow.Should().NotBeNull();
        workflow.BehaviorPipeline.Should().BeNull();
    }

    [Fact]
    public void AddExecutorBehavior_NullBehavior_ThrowsArgumentNullException()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();

        // Act
        Action act = () => options.AddExecutorBehavior(null!);

        // Assert
        act.Should().Throw<ArgumentNullException>();
    }

    [Fact]
    public void AddWorkflowBehavior_NullBehavior_ThrowsArgumentNullException()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();

        // Act
        Action act = () => options.AddWorkflowBehavior(null!);

        // Assert
        act.Should().Throw<ArgumentNullException>();
    }

    // Test helper classes
    private sealed class TestExecutorBehavior : IExecutorBehavior
    {
        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            return await continuation(cancellationToken);
        }
    }

    private sealed class TestWorkflowBehavior : IWorkflowBehavior
    {
        public async ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            return await continuation(cancellationToken);
        }
    }

    private sealed class SimpleExecutor : Executor
    {
        public SimpleExecutor(string id) : base(id) { }

        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<string, string>(async (message, context) =>
            {
                await context.SendMessageAsync(message);
                return message;
            });
    }
}
