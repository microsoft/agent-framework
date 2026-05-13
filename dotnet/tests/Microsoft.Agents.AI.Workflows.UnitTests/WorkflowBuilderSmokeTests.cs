// Copyright (c) Microsoft. All rights reserved.

using System;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public partial class WorkflowBuilderSmokeTests
{
    private sealed class NoOpExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                                               routeBuilder.AddHandler<object>((msg, ctx) => ctx.SendMessageAsync(msg)));
    }

    private sealed class SomeOtherNoOpExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                                               routeBuilder.AddHandler<object>((msg, ctx) => ctx.SendMessageAsync(msg)));
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

    [Fact]
    public void ForwardMessage_WithSingleTarget_CreatesDirectEdge()
    {
        // Arrange
        NoOpExecutor source = new("start");
        NoOpExecutor target = new("target");

        // Act
        Workflow workflow = new WorkflowBuilder(source.Id)
            .ForwardMessage<string>(source, target)
            .Build();

        // Assert
        Edge edge = GetSingleEdge(workflow, source.Id);
        edge.Kind.Should().Be(EdgeKind.Direct);
        edge.DirectEdgeData.Should().NotBeNull();
        edge.DirectEdgeData!.SinkId.Should().Be(target.Id);
        edge.DirectEdgeData.Condition.Should().NotBeNull();
        edge.DirectEdgeData.Condition!("message").Should().BeTrue();
        edge.DirectEdgeData.Condition!(42).Should().BeFalse();
        edge.DirectEdgeData.Condition!(null).Should().BeFalse();
    }

    [Fact]
    public void ForwardMessage_WithMultipleTargets_CreatesFanOutEdge()
    {
        // Arrange
        NoOpExecutor source = new("start");
        NoOpExecutor target1 = new("target1");
        NoOpExecutor target2 = new("target2");

        // Act
        Workflow workflow = new WorkflowBuilder(source.Id)
            .ForwardMessage<string>(source, [target1, target2], message => message == "match")
            .Build();

        // Assert
        Edge edge = GetSingleEdge(workflow, source.Id);
        edge.Kind.Should().Be(EdgeKind.FanOut);
        edge.FanOutEdgeData.Should().NotBeNull();
        edge.FanOutEdgeData!.SinkIds.Should().Equal([target1.Id, target2.Id]);
        edge.FanOutEdgeData.EdgeAssigner.Should().NotBeNull();
        edge.FanOutEdgeData.EdgeAssigner!("match", 2).Should().Equal([0, 1]);
        edge.FanOutEdgeData.EdgeAssigner!("other", 2).Should().BeEmpty();
        edge.FanOutEdgeData.EdgeAssigner!(42, 2).Should().BeEmpty();
    }

    [Fact]
    public void ForwardExcept_WithSingleTarget_CreatesDirectEdge()
    {
        // Arrange
        NoOpExecutor source = new("start");
        NoOpExecutor target = new("target");

        // Act
        Workflow workflow = new WorkflowBuilder(source.Id)
            .ForwardExcept<string>(source, target)
            .Build();

        // Assert
        Edge edge = GetSingleEdge(workflow, source.Id);
        edge.Kind.Should().Be(EdgeKind.Direct);
        edge.DirectEdgeData.Should().NotBeNull();
        edge.DirectEdgeData!.SinkId.Should().Be(target.Id);
        edge.DirectEdgeData.Condition.Should().NotBeNull();
        edge.DirectEdgeData.Condition!("message").Should().BeFalse();
        edge.DirectEdgeData.Condition!(42).Should().BeTrue();
        edge.DirectEdgeData.Condition!(null).Should().BeTrue();
    }

    [Fact]
    public void ForwardExcept_WithMultipleTargets_CreatesFanOutEdge()
    {
        // Arrange
        NoOpExecutor source = new("start");
        NoOpExecutor target1 = new("target1");
        NoOpExecutor target2 = new("target2");

        // Act
        Workflow workflow = new WorkflowBuilder(source.Id)
            .ForwardExcept<string>(source, [target1, target2])
            .Build();

        // Assert
        Edge edge = GetSingleEdge(workflow, source.Id);
        edge.Kind.Should().Be(EdgeKind.FanOut);
        edge.FanOutEdgeData.Should().NotBeNull();
        edge.FanOutEdgeData!.SinkIds.Should().Equal([target1.Id, target2.Id]);
        edge.FanOutEdgeData.EdgeAssigner.Should().NotBeNull();
        edge.FanOutEdgeData.EdgeAssigner!(42, 2).Should().Equal([0, 1]);
        edge.FanOutEdgeData.EdgeAssigner!("message", 2).Should().BeEmpty();
    }

    [Fact]
    public void AddChain_CreatesSequentialDirectEdges()
    {
        // Arrange
        NoOpExecutor source = new("start");
        NoOpExecutor middle = new("middle");
        NoOpExecutor end = new("end");

        // Act
        Workflow workflow = new WorkflowBuilder(source.Id)
            .AddChain(source, [middle, end])
            .Build();

        // Assert
        GetSingleEdge(workflow, source.Id).DirectEdgeData!.SinkId.Should().Be(middle.Id);
        GetSingleEdge(workflow, middle.Id).DirectEdgeData!.SinkId.Should().Be(end.Id);
    }

    [Fact]
    public void AddChain_WhenExecutorRepeats_Throws()
    {
        // Arrange
        NoOpExecutor source = new("start");
        NoOpExecutor middle = new("middle");

        // Act
        Action act = () => new WorkflowBuilder(source.Id)
            .AddChain(source, [middle, source]);

        // Assert
        act.Should().Throw<ArgumentException>()
            .WithParameterName("executors");
    }

    [Fact]
    public void AddExternalCall_CreatesRequestPortAndRoundTripEdges()
    {
        // Arrange
        const string PortId = "port1";
        NoOpExecutor source = new("start");

        // Act
        Workflow workflow = new WorkflowBuilder(source.Id)
            .AddExternalCall<string, int>(source, PortId)
            .Build();

        // Assert
        workflow.Ports.Should().ContainKey(PortId);
        workflow.Ports[PortId].Request.Should().Be(typeof(string));
        workflow.Ports[PortId].Response.Should().Be(typeof(int));
        workflow.ExecutorBindings.Should().ContainKey(PortId);
        GetSingleEdge(workflow, source.Id).DirectEdgeData!.SinkId.Should().Be(PortId);
        GetSingleEdge(workflow, PortId).DirectEdgeData!.SinkId.Should().Be(source.Id);
    }

    [Fact]
    public void AddSwitch_CreatesFanOutEdgeWithCasesAndDefault()
    {
        // Arrange
        NoOpExecutor source = new("start");
        NoOpExecutor stringTarget = new("string-target");
        NoOpExecutor intTarget = new("int-target");
        NoOpExecutor defaultTarget = new("default-target");

        // Act
        Workflow workflow = new WorkflowBuilder(source.Id)
            .AddSwitch(source, switchBuilder => switchBuilder
                .AddCase<string>(message => message == "match", [stringTarget])
                .AddCase<int>(message => message > 0, [intTarget])
                .WithDefault([defaultTarget]))
            .Build();

        // Assert
        Edge edge = GetSingleEdge(workflow, source.Id);
        edge.Kind.Should().Be(EdgeKind.FanOut);
        edge.FanOutEdgeData.Should().NotBeNull();
        edge.FanOutEdgeData!.SinkIds.Should().Equal([stringTarget.Id, intTarget.Id, defaultTarget.Id]);
        edge.FanOutEdgeData.EdgeAssigner.Should().NotBeNull();
        edge.FanOutEdgeData.EdgeAssigner!("match", 3).Should().Equal([0]);
        edge.FanOutEdgeData.EdgeAssigner!(2, 3).Should().Equal([1]);
        edge.FanOutEdgeData.EdgeAssigner!("other", 3).Should().Equal([2]);
    }

    private static Edge GetSingleEdge(Workflow workflow, string sourceId)
        => workflow.Edges[sourceId].Should().ContainSingle().Subject;
}
