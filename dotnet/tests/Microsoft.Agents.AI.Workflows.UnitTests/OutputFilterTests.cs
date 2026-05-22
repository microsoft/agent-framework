// Copyright (c) Microsoft. All rights reserved.

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

    private sealed class NoOpExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                                               routeBuilder.AddHandler<object>((msg, ctx) => ctx.SendMessageAsync(msg)));
    }
}
