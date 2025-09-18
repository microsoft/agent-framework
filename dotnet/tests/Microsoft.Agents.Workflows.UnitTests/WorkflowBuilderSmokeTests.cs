// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;

namespace Microsoft.Agents.Workflows.UnitTests;

public partial class WorkflowBuilderSmokeTests
{
    private sealed class NoOpExecutor(string? id = null) : Executor(id)
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<object>(
                (msg, ctx) => ctx.SendMessageAsync(msg));
    }

    private sealed class SomeOtherNoOpExecutor(string? id = null) : Executor(id)
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
            routeBuilder.AddHandler<object>(
                (msg, ctx) => ctx.SendMessageAsync(msg));
    }

    [Fact]
    public void Test_LateBinding_Executor()
    {
        Workflow workflow = new WorkflowBuilder("start")
                                .BindExecutor(new NoOpExecutor("start"))
                                .Build<object>();

        workflow.StartExecutorId.Should().Be("start");

        workflow.Registrations.Should().HaveCount(1);
        workflow.Registrations.Should().ContainKey("start");
        workflow.Registrations["start"].ExecutorType.Should().Be<NoOpExecutor>();
    }

    [Fact]
    public void Test_LateImplicitBinding_Executor()
    {
        NoOpExecutor start = new("start");
        Workflow workflow = new WorkflowBuilder("start")
                                .AddEdge(start, start)
                                .Build<object>();

        workflow.StartExecutorId.Should().Be("start");

        workflow.Registrations.Should().HaveCount(1);
        workflow.Registrations.Should().ContainKey("start");
        workflow.Registrations["start"].ExecutorType.Should().Be<NoOpExecutor>();
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
                       .Build<object>();
        };

        act.Should().Throw<InvalidOperationException>();
    }

    [Fact]
    public void Test_RebindToSameish_Allowed()
    {
        NoOpExecutor executor1 = new("start");

        Workflow workflow = new WorkflowBuilder("start")
                                .AddEdge(executor1, executor1)
                                .Build<object>();

        workflow.StartExecutorId.Should().Be("start");

        workflow.Registrations.Should().HaveCount(1);
        workflow.Registrations.Should().ContainKey("start");
        workflow.Registrations["start"].ExecutorType.Should().Be<NoOpExecutor>();
    }
}
