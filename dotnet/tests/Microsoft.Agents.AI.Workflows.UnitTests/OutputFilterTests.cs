// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class OutputFilterTests
{
    private static OutputFilter CreateFilterWithOutputFrom(string outputExecutorId)
    {
        NoOpExecutor start = new("start");
        NoOpExecutor end = new("end");

        Workflow workflow = new WorkflowBuilder("start")
            .AddEdge(start, end)
            .WithOutputFrom(outputExecutorId == "end" ? end : start)
            .Build();

        return new OutputFilter(workflow);
    }

    [Fact]
    public void OutputFilter_CanOutput_ReturnsTrueForRegisteredExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        filter.CanOutput("end", "some output").Should().BeTrue("the executor was registered via WithOutputFrom");
    }

    [Fact]
    public void OutputFilter_CanOutput_ReturnsFalseForUnregisteredExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        filter.CanOutput("start", "some output").Should().BeFalse("start was not registered as an output executor");
    }

    [Fact]
    public void OutputFilter_CanOutput_ReturnsFalseForNonExistentExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        filter.CanOutput("nonexistent", "some output").Should().BeFalse("an executor not in the workflow should not be an output executor");
    }

    [Fact]
    public void Test_OutputFilter_ReturnsEmptyTagSetWhenRegisteredViaWithOutputFrom()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        filter.TryGetTags("end", out HashSet<OutputTag>? tags).Should().BeTrue();
        tags.Should().NotBeNull().And.BeEmpty("terminal designation carries no tag");
    }

    [Fact]
    public void Test_OutputFilter_ReturnsIntermediateTagWhenRegisteredViaWithIntermediateOutputFrom()
    {
        NoOpExecutor start = new("start");
        NoOpExecutor end = new("end");

        Workflow workflow = new WorkflowBuilder("start")
            .AddEdge(start, end)
            .WithIntermediateOutputFrom([end])
            .Build();

        OutputFilter filter = new(workflow);

        filter.TryGetTags("end", out HashSet<OutputTag>? tags).Should().BeTrue();
        tags.Should().BeEquivalentTo(new[] { OutputTag.Intermediate });
    }

    [Fact]
    public void Test_OutputFilter_ReturnsIntermediateTagForAccumulatedDesignation()
    {
        NoOpExecutor start = new("start");
        NoOpExecutor end = new("end");

        Workflow workflow = new WorkflowBuilder("start")
            .AddEdge(start, end)
            .WithOutputFrom(end)
            .WithIntermediateOutputFrom([end])
            .Build();

        OutputFilter filter = new(workflow);

        filter.TryGetTags("end", out HashSet<OutputTag>? tags).Should().BeTrue();
        tags.Should().BeEquivalentTo(new[] { OutputTag.Intermediate },
            "terminal designation contributes no tag; the union is the intermediate set");
    }

    [Fact]
    public void Test_OutputFilter_TryGetTagsReturnsFalseForUnregisteredExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        filter.TryGetTags("start", out HashSet<OutputTag>? tags).Should().BeFalse();
        tags.Should().BeNull();
    }

    private sealed class NoOpExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                                               routeBuilder.AddHandler<object>((msg, ctx) => ctx.SendMessageAsync(msg)));
    }
}
