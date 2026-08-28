// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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

        Assert.True(filter.CanOutput("end", "some output"));
    }

    [Fact]
    public void OutputFilter_CanOutput_ReturnsFalseForUnregisteredExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        Assert.False(filter.CanOutput("start", "some output"));
    }

    [Fact]
    public void OutputFilter_CanOutput_ReturnsFalseForNonExistentExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        Assert.False(filter.CanOutput("nonexistent", "some output"));
    }

    [Fact]
    public void Test_OutputFilter_ReturnsEmptyTagSetWhenRegisteredViaWithOutputFrom()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        Assert.True(filter.TryGetTags("end", out HashSet<OutputTag>? tags));
        Assert.NotNull(tags);
        Assert.Empty(tags);
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

        Assert.True(filter.TryGetTags("end", out HashSet<OutputTag>? tags));
        Assert.Equivalent(new[] { OutputTag.Intermediate }, tags);
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

        Assert.True(filter.TryGetTags("end", out HashSet<OutputTag>? tags));
        Assert.Equivalent(new[] { OutputTag.Intermediate }, tags);
    }

    [Fact]
    public void Test_OutputFilter_TryGetTagsReturnsFalseForUnregisteredExecutor()
    {
        OutputFilter filter = CreateFilterWithOutputFrom("end");

        Assert.False(filter.TryGetTags("start", out HashSet<OutputTag>? tags));
        Assert.Null(tags);
    }

    private sealed class NoOpExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                                               routeBuilder.AddHandler<object>((msg, ctx) => ctx.SendMessageAsync(msg)));
    }
}
