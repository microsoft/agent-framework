// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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
        edge.DirectEdgeData!.SourceId.Should().Be(source.Id);
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
        edge.FanOutEdgeData!.SourceId.Should().Be(source.Id);
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
        edge.DirectEdgeData!.SourceId.Should().Be(source.Id);
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
        edge.FanOutEdgeData!.SourceId.Should().Be(source.Id);
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
        Edge firstEdge = GetSingleEdge(workflow, source.Id);
        firstEdge.Kind.Should().Be(EdgeKind.Direct);
        firstEdge.DirectEdgeData!.SourceId.Should().Be(source.Id);
        firstEdge.DirectEdgeData.SinkId.Should().Be(middle.Id);

        Edge secondEdge = GetSingleEdge(workflow, middle.Id);
        secondEdge.Kind.Should().Be(EdgeKind.Direct);
        secondEdge.DirectEdgeData!.SourceId.Should().Be(middle.Id);
        secondEdge.DirectEdgeData.SinkId.Should().Be(end.Id);
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

        Edge requestEdge = GetSingleEdge(workflow, source.Id);
        requestEdge.Kind.Should().Be(EdgeKind.Direct);
        requestEdge.DirectEdgeData!.SourceId.Should().Be(source.Id);
        requestEdge.DirectEdgeData.SinkId.Should().Be(PortId);

        Edge responseEdge = GetSingleEdge(workflow, PortId);
        responseEdge.Kind.Should().Be(EdgeKind.Direct);
        responseEdge.DirectEdgeData!.SourceId.Should().Be(PortId);
        responseEdge.DirectEdgeData.SinkId.Should().Be(source.Id);
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
        edge.FanOutEdgeData!.SourceId.Should().Be(source.Id);
        edge.FanOutEdgeData!.SinkIds.Should().Equal([stringTarget.Id, intTarget.Id, defaultTarget.Id]);
        edge.FanOutEdgeData.EdgeAssigner.Should().NotBeNull();
        edge.FanOutEdgeData.EdgeAssigner!("match", 3).Should().Equal([0]);
        edge.FanOutEdgeData.EdgeAssigner!(2, 3).Should().Equal([1]);
        edge.FanOutEdgeData.EdgeAssigner!("other", 3).Should().Equal([2]);
    }

    [Fact]
    public void ForwardMessage_InvalidArguments_Throw()
    {
        // Arrange
        WorkflowBuilder builder = new("start");
        NoOpExecutor source = new("start");
        NoOpExecutor target = new("target");

        // Act/Assert
        Assert.Throws<ArgumentNullException>("builder", () => ((WorkflowBuilder)null!).ForwardMessage<string>(source, target));
        Assert.Throws<ArgumentNullException>("source", () => builder.ForwardMessage<string>(null!, target));
        Assert.Throws<ArgumentNullException>("target", () => builder.ForwardMessage<string>(source, (ExecutorBinding)null!));
        Assert.Throws<ArgumentNullException>("targets", () => builder.ForwardMessage<string>(source, (IEnumerable<ExecutorBinding>)null!));
        Assert.Throws<ArgumentNullException>("targets", () => builder.ForwardMessage<string>(source, [target, null!]));
        Assert.Throws<ArgumentException>("targets", () => builder.ForwardMessage<string>(source, []));
    }

    [Fact]
    public void ForwardExcept_InvalidArguments_Throw()
    {
        // Arrange
        WorkflowBuilder builder = new("start");
        NoOpExecutor source = new("start");
        NoOpExecutor target = new("target");

        // Act/Assert
        Assert.Throws<ArgumentNullException>("builder", () => ((WorkflowBuilder)null!).ForwardExcept<string>(source, target));
        Assert.Throws<ArgumentNullException>("source", () => builder.ForwardExcept<string>(null!, target));
        Assert.Throws<ArgumentNullException>("target", () => builder.ForwardExcept<string>(source, (ExecutorBinding)null!));
        Assert.Throws<ArgumentNullException>("targets", () => builder.ForwardExcept<string>(source, (IEnumerable<ExecutorBinding>)null!));
        Assert.Throws<ArgumentNullException>("targets", () => builder.ForwardExcept<string>(source, [target, null!]));
        Assert.Throws<ArgumentException>("targets", () => builder.ForwardExcept<string>(source, []));
    }

    [Fact]
    public void AddChain_InvalidArguments_Throw()
    {
        // Arrange
        WorkflowBuilder builder = new("start");
        NoOpExecutor source = new("start");
        NoOpExecutor target = new("target");
        NoOpExecutor otherTarget = new("other-target");

        // Act/Assert
        Assert.Throws<ArgumentNullException>("builder", () => ((WorkflowBuilder)null!).AddChain(source, [target]));
        Assert.Throws<ArgumentNullException>("source", () => builder.AddChain(null!, [target]));
        Assert.Throws<ArgumentNullException>("executors", () => builder.AddChain(source, null!));
        Assert.Throws<ArgumentNullException>("executors", () => builder.AddChain(source, [target, null!]));
        Assert.Throws<ArgumentException>("executors", () => builder.AddChain(source, [target, source]));
        Assert.Throws<ArgumentException>("executors", () => builder.AddChain(source, [target, otherTarget, target]));
    }

    [Fact]
    public void AddExternalCall_InvalidArguments_Throw()
    {
        // Arrange
        WorkflowBuilder builder = new("start");
        NoOpExecutor source = new("start");

        // Act/Assert
        Assert.Throws<ArgumentNullException>("builder", () => ((WorkflowBuilder)null!).AddExternalCall<string, int>(source, "port"));
        Assert.Throws<ArgumentNullException>("source", () => builder.AddExternalCall<string, int>(null!, "port"));
        Assert.Throws<ArgumentNullException>("portId", () => builder.AddExternalCall<string, int>(source, null!));
    }

    [Fact]
    public void AddSwitch_InvalidArguments_Throw()
    {
        // Arrange
        WorkflowBuilder builder = new("start");
        NoOpExecutor source = new("start");

        // Act/Assert
        Assert.Throws<ArgumentNullException>("builder", () => ((WorkflowBuilder)null!).AddSwitch(source, _ => { }));
        Assert.Throws<ArgumentNullException>("source", () => builder.AddSwitch(null!, _ => { }));
        Assert.Throws<ArgumentNullException>("configureSwitch", () => builder.AddSwitch(source, null!));
        Assert.Throws<ArgumentException>("targets", () => builder.AddSwitch(source, _ => { }));
        Assert.Throws<ArgumentException>("targets", () => builder.AddSwitch(source, switchBuilder => switchBuilder.AddCase<string>(_ => true, [])));
    }

    [Fact]
    public void SwitchBuilder_InvalidArguments_Throw()
    {
        // Arrange
        SwitchBuilder switchBuilder = new();
        NoOpExecutor target = new("target");

        // Act/Assert
        Assert.Throws<ArgumentNullException>("predicate", () => switchBuilder.AddCase<string>(null!, [target]));
        Assert.Throws<ArgumentNullException>("executors", () => switchBuilder.AddCase<string>(_ => true, null!));
        Assert.Throws<ArgumentNullException>("executors", () => switchBuilder.AddCase<string>(_ => true, [target, null!]));
        Assert.Throws<ArgumentNullException>("executors", () => switchBuilder.WithDefault(null!));
        Assert.Throws<ArgumentNullException>("executors", () => switchBuilder.WithDefault([target, null!]));
    }

    /// <summary>
    /// Gets the only edge emitted by the specified workflow source.
    /// </summary>
    private static Edge GetSingleEdge(Workflow workflow, string sourceId)
        => workflow.Edges[sourceId].Should().ContainSingle().Subject;
}
