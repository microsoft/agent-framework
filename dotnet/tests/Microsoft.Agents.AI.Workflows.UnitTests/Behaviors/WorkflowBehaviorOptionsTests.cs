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
    public void WorkflowBuilder_WithBehaviors_ConfiguresBehaviors()
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
    public void WorkflowBuilder_WithBehaviors_SupportsFluentAPI()
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
    public void WorkflowBuilder_WithoutBehaviors_HasNullPipeline()
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

    [Fact]
    public void AddExecutorBehavior_GenericOverload_RegistersBehavior()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();

        // Act
        options.AddExecutorBehavior<TestExecutorBehavior>();
        var pipeline = options.BuildPipeline();

        // Assert
        pipeline.Should().NotBeNull();
        pipeline!.HasExecutorBehaviors.Should().BeTrue();
    }

    [Fact]
    public void AddWorkflowBehavior_GenericOverload_RegistersBehavior()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();

        // Act
        options.AddWorkflowBehavior<TestWorkflowBehavior>();
        var pipeline = options.BuildPipeline();

        // Assert
        pipeline.Should().NotBeNull();
        pipeline!.HasWorkflowBehaviors.Should().BeTrue();
    }

    [Fact]
    public void AddBehavior_ReturnsSameOptionsInstance_ForChaining()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();

        // Act - every registration overload is documented as chainable
        var chained = options
            .AddExecutorBehavior(new TestExecutorBehavior())
            .AddWorkflowBehavior(new TestWorkflowBehavior())
            .AddExecutorBehavior<TestExecutorBehavior>()
            .AddWorkflowBehavior<TestWorkflowBehavior>();

        // Assert
        chained.Should().BeSameAs(options);
        var pipeline = options.BuildPipeline();
        pipeline!.HasExecutorBehaviors.Should().BeTrue();
        pipeline.HasWorkflowBehaviors.Should().BeTrue();
    }

    [Fact]
    public void WorkflowBuilder_WithBehaviors_NullConfigure_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = new WorkflowBuilder(new SimpleExecutor("test"));

        // Act
        Action act = () => builder.WithBehaviors(null!);

        // Assert - a null configure callback must not be silently ignored
        act.Should().Throw<ArgumentNullException>();
    }

    [Fact]
    public void WorkflowBuilder_WithBehaviors_CalledTwice_AccumulatesBehaviors()
    {
        // Arrange
        var executor = new SimpleExecutor("test");

        // Act - successive calls share one options instance rather than replacing it
        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options => options.AddExecutorBehavior(new TestExecutorBehavior()))
            .WithBehaviors(options => options.AddWorkflowBehavior(new TestWorkflowBehavior()))
            .Build();

        // Assert
        workflow.BehaviorPipeline.Should().NotBeNull();
        workflow.BehaviorPipeline!.HasExecutorBehaviors.Should().BeTrue();
        workflow.BehaviorPipeline.HasWorkflowBehaviors.Should().BeTrue();
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

        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
            protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string, string>(async (message, context) =>
            {
                await context.SendMessageAsync(message);
                return message;
            }));
    }
}
