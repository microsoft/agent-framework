// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public partial class WorkflowBuilderSmokeTests
{
    private sealed class NoOpExecutor(string id) : Executor(id)
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<object>(
                (msg, ctx) => ctx.SendMessageAsync(msg));
    }

    private sealed class SomeOtherNoOpExecutor(string id) : Executor(id)
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<object>(
                (msg, ctx) => ctx.SendMessageAsync(msg));
    }

    [Fact]
    public void Test_Validation_FailsWhenUnboundExecutors()
    {
        Func<Workflow> act = () =>
        {
            return new WorkflowBuilder("start")
                       .AddEdge(new NoOpExecutor("start"), "unbound")
                       .Build();
        };

        act.Should().Throw<InvalidOperationException>();
    }

    [Fact]
    public void Test_Validation_FailsWhenUnreachableExecutors()
    {
        Func<Workflow> act = () =>
        {
            return new WorkflowBuilder("start")
                       .BindExecutor(new NoOpExecutor("start"))
                       .AddEdge(new NoOpExecutor("unreachable"), new NoOpExecutor("also-unreachable"))
                       .Build();
        };
        act.Should().Throw<InvalidOperationException>();
    }

    [Fact]
    public void Test_Validation_AddEdgesOutOfOrderDoesNotImpactReachability()
    {
        Workflow workflow = new WorkflowBuilder("start")
                                .BindExecutor(new NoOpExecutor("start"))
                                .AddEdge(new NoOpExecutor("not-unreachable"), new NoOpExecutor("also-not-unreachable"))
                                .AddEdge("start", "not-unreachable")
                                .Build();

        workflow.StartExecutorId.Should().Be("start");

        workflow.ExecutorBindings.Should().HaveCount(3);
        workflow.ExecutorBindings.Should().ContainKey("start");
        workflow.ExecutorBindings.Should().ContainKey("not-unreachable");
        workflow.ExecutorBindings.Should().ContainKey("also-not-unreachable");

        workflow.ExecutorBindings.Values.Should().AllSatisfy(binding => binding.ExecutorType.Should().Be<NoOpExecutor>());
    }

    [Fact]
    public void Test_LateBinding_Executor()
    {
        Workflow workflow = new WorkflowBuilder("start")
                                .BindExecutor(new NoOpExecutor("start"))
                                .Build();

        workflow.StartExecutorId.Should().Be("start");

        workflow.ExecutorBindings.Should().HaveCount(1);
        workflow.ExecutorBindings.Should().ContainKey("start");
        workflow.ExecutorBindings["start"].ExecutorType.Should().Be<NoOpExecutor>();
    }

    [Fact]
    public void Test_LateImplicitBinding_Executor()
    {
        NoOpExecutor start = new("start");
        Workflow workflow = new WorkflowBuilder("start")
                                .AddEdge(start, start)
                                .Build();

        workflow.StartExecutorId.Should().Be("start");

        workflow.ExecutorBindings.Should().HaveCount(1);
        workflow.ExecutorBindings.Should().ContainKey("start");
        workflow.ExecutorBindings["start"].ExecutorType.Should().Be<NoOpExecutor>();
    }

    [Fact]
    public void Test_RebindToDifferent_Disallowed()
    {
        NoOpExecutor executor1 = new("start");
        SomeOtherNoOpExecutor executor2 = new("start");

        Func<Workflow> act = () =>
        {
            return new WorkflowBuilder("start")
                       .AddEdge(executor1, executor2)
                       .Build();
        };

        act.Should().Throw<InvalidOperationException>();
    }

    [Fact]
    public void Test_RebindToSameish_Allowed()
    {
        NoOpExecutor executor1 = new("start");

        Workflow workflow = new WorkflowBuilder("start")
                                .AddEdge(executor1, executor1)
                                .Build();

        workflow.StartExecutorId.Should().Be("start");

        workflow.ExecutorBindings.Should().HaveCount(1);
        workflow.ExecutorBindings.Should().ContainKey("start");
        workflow.ExecutorBindings["start"].ExecutorType.Should().Be<NoOpExecutor>();
    }

    [Fact]
    public void Test_Workflow_NameAndDescription()
    {
        // Test with name and description
        Workflow workflow1 = new WorkflowBuilder("start")
            .WithName("Test Pipeline")
            .WithDescription("Test workflow description")
            .BindExecutor(new NoOpExecutor("start"))
            .Build();

        workflow1.Name.Should().Be("Test Pipeline");
        workflow1.Description.Should().Be("Test workflow description");

        // Test without (defaults to null)
        Workflow workflow2 = new WorkflowBuilder("start2")
            .BindExecutor(new NoOpExecutor("start2"))
            .Build();

        workflow2.Name.Should().BeNull();
        workflow2.Description.Should().BeNull();

        // Test with only name (no description)
        Workflow workflow3 = new WorkflowBuilder("start3")
            .WithName("Named Only")
            .BindExecutor(new NoOpExecutor("start3"))
            .Build();

        workflow3.Name.Should().Be("Named Only");
        workflow3.Description.Should().BeNull();
    }
}
