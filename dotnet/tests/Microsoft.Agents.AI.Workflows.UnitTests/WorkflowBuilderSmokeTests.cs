// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Observability;
using OpenTelemetry.Trace;

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
    public void Test_LateBinding_Executor()
    {
        Workflow workflow = new WorkflowBuilder("start")
                                .BindExecutor(new NoOpExecutor("start"))
                                .Build();

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
                                .Build();

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

        workflow.Registrations.Should().HaveCount(1);
        workflow.Registrations.Should().ContainKey("start");
        workflow.Registrations["start"].ExecutorType.Should().Be<NoOpExecutor>();
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

    [Fact]
    public void Test_WorkflowDefinition_Tag_IsSet()
    {
        // Arrange
        var sourceName = typeof(WorkflowBuilder).Namespace!;
        var activities = new List<Activity>();
        using var tracerProvider = OpenTelemetry.Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddInMemoryExporter(activities)
            .Build();

        // Act
        Workflow workflow = new WorkflowBuilder("complex")
            .WithName("Complex Workflow")
            .WithDescription("Complex Workflow for Tests")
            .AddEdge(new NoOpExecutor("complex"), new SomeOtherNoOpExecutor("target"))
            .WithOutputFrom(new NoOpExecutor("output"))
            .Build();

        // Assert
        IEnumerable<Activity> buildActivities = activities.Where(a => a.OperationName == ActivityNames.WorkflowBuild);
        buildActivities.Should().NotBeEmpty();

        IEnumerable<object?> tags = buildActivities.Select(a => a.GetTagItem(Tags.WorkflowDefinition));
        tags.Should().NotBeEmpty();

        IEnumerable<string?> definitionJsons = tags.Select(t => t?.ToString()).Where(ts => ts?.Contains("complex") == true);
        definitionJsons.Should().ContainSingle();

        string definitionJson = definitionJsons.Single()!;
        definitionJson.Should().NotBeEmpty();

        WorkflowInfo workflowInfo = JsonSerializer.Deserialize(
            definitionJson,
            WorkflowsJsonUtilities.JsonContext.Default.WorkflowInfo)!;

        workflowInfo.Executors.Should().HaveCount(3);
        workflowInfo.Executors.Should().ContainKey("complex");
        workflowInfo.Executors.Should().ContainKey("target");
        workflowInfo.Executors.Should().ContainKey("output");

        workflowInfo.Executors["complex"].ExecutorType.IsMatch<NoOpExecutor>().Should().BeTrue();
        workflowInfo.Executors["target"].ExecutorType.IsMatch<SomeOtherNoOpExecutor>().Should().BeTrue();
        workflowInfo.Executors["output"].ExecutorType.IsMatch<NoOpExecutor>().Should().BeTrue();

        workflowInfo.StartExecutorId.Should().Be("complex");
        workflowInfo.OutputExecutorIds.Should().HaveCount(1);
        workflowInfo.OutputExecutorIds.Should().Contain("output");

        workflowInfo.Edges.Should().HaveCount(1);
        workflowInfo.Edges.Should().ContainKey("complex");

        workflowInfo.Edges["complex"].Should().HaveCount(1);
        workflowInfo.Edges["complex"][0].Kind.Should().Be(EdgeKind.Direct);

        workflowInfo.RequestPorts.Should().BeEmpty();
        workflowInfo.InputType.Should().BeNull();
    }
}
