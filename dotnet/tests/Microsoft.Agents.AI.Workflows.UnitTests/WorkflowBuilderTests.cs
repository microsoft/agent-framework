// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Numerics;
using System.Reflection;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public partial class WorkflowBuilderTests
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
        static Workflow act()
        {
            return new WorkflowBuilder("start")
                       .AddEdge(new NoOpExecutor("start"), "unbound")
                       .Build();
        }

        Assert.Throws<InvalidOperationException>((Func<Workflow>)act);
    }

    [Fact]
    public void Test_Validation_FailsWhenUnreachableExecutors()
    {
        static Workflow act()
        {
            return new WorkflowBuilder("start")
                       .BindExecutor(new NoOpExecutor("start"))
                       .AddEdge(new NoOpExecutor("unreachable"), new NoOpExecutor("also-unreachable"))
                       .Build();
        }
        Assert.Throws<InvalidOperationException>((Func<Workflow>)act);
    }

    [Fact]
    public void Test_Validation_AddEdgesOutOfOrderDoesNotImpactReachability()
    {
        Workflow workflow = new WorkflowBuilder("start")
                                .BindExecutor(new NoOpExecutor("start"))
                                .AddEdge(new NoOpExecutor("not-unreachable"), new NoOpExecutor("also-not-unreachable"))
                                .AddEdge("start", "not-unreachable")
                                .Build();

        Assert.Equal("start", workflow.StartExecutorId);

        Assert.Equal(3, workflow.ExecutorBindings.Count);
        Assert.Contains("start", workflow.ExecutorBindings);
        Assert.Contains("not-unreachable", workflow.ExecutorBindings);
        Assert.Contains("also-not-unreachable", workflow.ExecutorBindings);

        Assert.All(workflow.ExecutorBindings.Values, binding => Assert.Equal(typeof(NoOpExecutor), binding.ExecutorType));
    }

    [Fact]
    public void Test_LateBinding_Executor()
    {
        Workflow workflow = new WorkflowBuilder("start")
                                .BindExecutor(new NoOpExecutor("start"))
                                .Build();

        Assert.Equal("start", workflow.StartExecutorId);

        Assert.Single(workflow.ExecutorBindings);
        Assert.Contains("start", workflow.ExecutorBindings!);
        Assert.Equal(typeof(NoOpExecutor), workflow.ExecutorBindings["start"].ExecutorType);
    }

    [Fact]
    public void Test_LateImplicitBinding_Executor()
    {
        NoOpExecutor start = new("start");
        Workflow workflow = new WorkflowBuilder("start")
                                .AddEdge(start, start)
                                .Build();

        Assert.Equal("start", workflow.StartExecutorId);

        Assert.Single(workflow.ExecutorBindings);
        Assert.Contains("start", workflow.ExecutorBindings!);
        Assert.Equal(typeof(NoOpExecutor), workflow.ExecutorBindings["start"].ExecutorType);
    }

    [Fact]
    public void Test_RebindToDifferent_Disallowed()
    {
        NoOpExecutor executor1 = new("start");
        SomeOtherNoOpExecutor executor2 = new("start");

        Workflow act()
        {
            return new WorkflowBuilder("start")
                       .AddEdge(executor1, executor2)
                       .Build();
        }

        Assert.Throws<InvalidOperationException>((Func<Workflow>)act);
    }

    [Fact]
    public void Test_RebindToSameish_Allowed()
    {
        NoOpExecutor executor1 = new("start");

        Workflow workflow = new WorkflowBuilder("start")
                                .AddEdge(executor1, executor1)
                                .Build();

        Assert.Equal("start", workflow.StartExecutorId);

        Assert.Single(workflow.ExecutorBindings);
        Assert.Contains("start", workflow.ExecutorBindings!);
        Assert.Equal(typeof(NoOpExecutor), workflow.ExecutorBindings["start"].ExecutorType);
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

        Assert.Equal("Test Pipeline", workflow1.Name);
        Assert.Equal("Test workflow description", workflow1.Description);

        // Test without (defaults to null)
        Workflow workflow2 = new WorkflowBuilder("start2")
            .BindExecutor(new NoOpExecutor("start2"))
            .Build();

        Assert.Null(workflow2.Name);
        Assert.Null(workflow2.Description);

        // Test with only name (no description)
        Workflow workflow3 = new WorkflowBuilder("start3")
            .WithName("Named Only")
            .BindExecutor(new NoOpExecutor("start3"))
            .Build();

        Assert.Equal("Named Only", workflow3.Name);
        Assert.Null(workflow3.Description);
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
        Assert.Equal(EdgeKind.Direct, edge.Kind);
        Assert.NotNull(edge.DirectEdgeData);
        Assert.Equal(source.Id, edge.DirectEdgeData!.SourceId);
        Assert.Equal(target.Id, edge.DirectEdgeData!.SinkId);
        Assert.NotNull(edge.DirectEdgeData.Condition);
        Assert.True(edge.DirectEdgeData.Condition!("message"));
        Assert.False(edge.DirectEdgeData.Condition!(42));
        Assert.False(edge.DirectEdgeData.Condition!(null));
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
        Assert.Equal(EdgeKind.FanOut, edge.Kind);
        Assert.NotNull(edge.FanOutEdgeData);
        Assert.Equal(source.Id, edge.FanOutEdgeData!.SourceId);
        Assert.Equal([target1.Id, target2.Id], edge.FanOutEdgeData!.SinkIds);
        Assert.NotNull(edge.FanOutEdgeData.EdgeAssigner);
        Assert.Equal([0, 1], edge.FanOutEdgeData.EdgeAssigner!("match", 2));
        Assert.Empty(edge.FanOutEdgeData.EdgeAssigner!("other", 2) ?? []);
        Assert.Empty(edge.FanOutEdgeData.EdgeAssigner!(42, 2) ?? []);
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
        Assert.Equal(EdgeKind.Direct, edge.Kind);
        Assert.NotNull(edge.DirectEdgeData);
        Assert.Equal(source.Id, edge.DirectEdgeData!.SourceId);
        Assert.Equal(target.Id, edge.DirectEdgeData!.SinkId);
        Assert.NotNull(edge.DirectEdgeData.Condition);
        Assert.False(edge.DirectEdgeData.Condition!("message"));
        Assert.True(edge.DirectEdgeData.Condition!(42));
        Assert.True(edge.DirectEdgeData.Condition!(null));
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
        Assert.Equal(EdgeKind.FanOut, edge.Kind);
        Assert.NotNull(edge.FanOutEdgeData);
        Assert.Equal(source.Id, edge.FanOutEdgeData!.SourceId);
        Assert.Equal([target1.Id, target2.Id], edge.FanOutEdgeData!.SinkIds);
        Assert.NotNull(edge.FanOutEdgeData.EdgeAssigner);
        Assert.Equal([0, 1], edge.FanOutEdgeData.EdgeAssigner!(42, 2));
        Assert.Empty(edge.FanOutEdgeData.EdgeAssigner!("message", 2) ?? []);
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
        Assert.Equal(EdgeKind.Direct, firstEdge.Kind);
        Assert.Equal(source.Id, firstEdge.DirectEdgeData!.SourceId);
        Assert.Equal(middle.Id, firstEdge.DirectEdgeData.SinkId);

        Edge secondEdge = GetSingleEdge(workflow, middle.Id);
        Assert.Equal(EdgeKind.Direct, secondEdge.Kind);
        Assert.Equal(middle.Id, secondEdge.DirectEdgeData!.SourceId);
        Assert.Equal(end.Id, secondEdge.DirectEdgeData.SinkId);
    }

    [Fact]
    public void AddChain_WhenExecutorRepeats_Throws()
    {
        // Arrange
        NoOpExecutor source = new("start");
        NoOpExecutor middle = new("middle");

        // Act
        void act() => new WorkflowBuilder(source.Id)
            .AddChain(source, [middle, source]);

        // Assert
        Assert.Equal("executors", Assert.Throws<ArgumentException>(act).ParamName);
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
        Assert.Contains(PortId, workflow.Ports);
        Assert.Equal(typeof(string), workflow.Ports[PortId].Request);
        Assert.Equal(typeof(int), workflow.Ports[PortId].Response);
        Assert.Contains(PortId, workflow.ExecutorBindings);

        Edge requestEdge = GetSingleEdge(workflow, source.Id);
        Assert.Equal(EdgeKind.Direct, requestEdge.Kind);
        Assert.Equal(source.Id, requestEdge.DirectEdgeData!.SourceId);
        Assert.Equal(PortId, requestEdge.DirectEdgeData.SinkId);

        Edge responseEdge = GetSingleEdge(workflow, PortId);
        Assert.Equal(EdgeKind.Direct, responseEdge.Kind);
        Assert.Equal(PortId, responseEdge.DirectEdgeData!.SourceId);
        Assert.Equal(source.Id, responseEdge.DirectEdgeData.SinkId);
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
        Assert.Equal(EdgeKind.FanOut, edge.Kind);
        Assert.NotNull(edge.FanOutEdgeData);
        Assert.Equal(source.Id, edge.FanOutEdgeData!.SourceId);
        Assert.Equal([stringTarget.Id, intTarget.Id, defaultTarget.Id], edge.FanOutEdgeData!.SinkIds);
        Assert.NotNull(edge.FanOutEdgeData.EdgeAssigner);
        Assert.Equal([0], edge.FanOutEdgeData.EdgeAssigner!("match", 3));
        Assert.Equal([1], edge.FanOutEdgeData.EdgeAssigner!(2, 3));
        Assert.Equal([2], edge.FanOutEdgeData.EdgeAssigner!("other", 3));
    }

    [Fact]
    public void ForwardMessage_InvalidArguments_Throw()
    {
        // Arrange
        WorkflowBuilder builder = new("start");
        NoOpExecutor source = new("start");
        NoOpExecutor target = new("target");

        // Act/Assert
        Assert.Throws<ArgumentNullException>(() => ((WorkflowBuilder)null!).ForwardMessage<string>(source, target));
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
        Assert.Throws<ArgumentNullException>(() => ((WorkflowBuilder)null!).ForwardExcept<string>(source, target));
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
        Assert.Throws<ArgumentNullException>(() => ((WorkflowBuilder)null!).AddChain(source, [target]));
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
        Assert.Throws<ArgumentNullException>(() => ((WorkflowBuilder)null!).AddExternalCall<string, int>(source, "port"));
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
        Assert.Throws<ArgumentNullException>(() => ((WorkflowBuilder)null!).AddSwitch(source, _ => { }));
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
        Assert.Throws<ArgumentNullException>("executors[1]", () => switchBuilder.AddCase<string>(_ => true, [target, null!]));
        Assert.Throws<ArgumentNullException>("executors", () => switchBuilder.WithDefault(null!));
        Assert.Throws<ArgumentNullException>("executors[1]", () => switchBuilder.WithDefault([target, null!]));
    }

    /// <summary>
    /// Gets the only edge emitted by the specified workflow source.
    /// </summary>
    private static Edge GetSingleEdge(Workflow workflow, string sourceId)
        => Assert.Single(workflow.Edges[sourceId]);

    // --- Tag-aware WithOutputFrom / WithIntermediateOutputFrom tests ---

    [Fact]
    public void Test_WithOutputFrom_RegistersWithEmptyTagSet()
    {
        NoOpExecutor a = new("a");
        NoOpExecutor b = new("b");
        Workflow workflow = new WorkflowBuilder("a")
            .AddEdge(a, b)
            .WithOutputFrom(b)
            .Build();

        Assert.Contains("b", workflow.OutputExecutors);
        Assert.Empty(workflow.OutputExecutors["b"] ?? []);
    }

    [Fact]
    public void Test_WithIntermediateOutputFrom_AddsIntermediateTag()
    {
        NoOpExecutor a = new("a");
        NoOpExecutor b = new("b");
        Workflow workflow = new WorkflowBuilder("a")
            .AddEdge(a, b)
            .WithIntermediateOutputFrom([b])
            .Build();

        Assert.Equivalent(new[] { OutputTag.Intermediate }, workflow.OutputExecutors["b"]);
    }

    [Fact]
    public void Test_WithOutputFrom_MultipleExecutorsAllUntagged()
    {
        NoOpExecutor a = new("a");
        NoOpExecutor b = new("b");
        NoOpExecutor c = new("c");

        Workflow workflow = new WorkflowBuilder("a")
            .AddEdge(a, b).AddEdge(a, c)
            .WithOutputFrom(b, c)
            .Build();

        Assert.Equal(2, workflow.OutputExecutors.Count);
        Assert.Empty(workflow.OutputExecutors["b"] ?? []);
        Assert.Empty(workflow.OutputExecutors["c"] ?? []);
    }

    [Fact]
    public void Test_WithOutputFrom_ThenIntermediate_AccumulatesTags()
    {
        NoOpExecutor a = new("a");
        NoOpExecutor b = new("b");
        Workflow workflow = new WorkflowBuilder("a")
            .AddEdge(a, b)
            .WithOutputFrom(b)
            .WithIntermediateOutputFrom([b])
            .Build();

        // WithOutputFrom doesn't add a tag; WithIntermediateOutputFrom adds Intermediate.
        Assert.Equivalent(new[] { OutputTag.Intermediate }, workflow.OutputExecutors["b"]);
    }

    [Fact]
    public void Test_WithIntermediateOutputFrom_RepeatedDedupes()
    {
        NoOpExecutor a = new("a");
        NoOpExecutor b = new("b");
        Workflow workflow = new WorkflowBuilder("a")
            .AddEdge(a, b)
            .WithIntermediateOutputFrom([b])
            .WithIntermediateOutputFrom([b])
            .Build();

        Assert.Equivalent(new[] { OutputTag.Intermediate }, workflow.OutputExecutors["b"]);
    }

    [Fact]
    public void Test_WithIntermediateOutputFrom_OnlyRegistersWithoutPriorWithOutputFrom()
    {
        // WithIntermediateOutputFrom on its own is sufficient to register the executor as an
        // output source — the call ensures the id is in the dict with the Intermediate tag.
        NoOpExecutor a = new("a");
        NoOpExecutor b = new("b");
        Workflow workflow = new WorkflowBuilder("a")
            .AddEdge(a, b)
            .WithIntermediateOutputFrom([b])
            .Build();

        Assert.Contains("b", workflow.OutputExecutors);
        Assert.Equivalent(new[] { OutputTag.Intermediate }, workflow.OutputExecutors["b"]);
    }

    [Fact]
    public void Test_WithOutputFrom_TracksExecutorBinding()
    {
        // A placeholder binding referenced via WithOutputFrom must end up bound by the time we Build.
        NoOpExecutor a = new("a");
        NoOpExecutor future = new("future");

        Workflow workflow = new WorkflowBuilder("a")
            .AddEdge(a, "future")
            .WithIntermediateOutputFrom(["future"])
            .BindExecutor(future)
            .Build();

        Assert.Contains("future", workflow.OutputExecutors);
        Assert.Equivalent(new[] { OutputTag.Intermediate }, workflow.OutputExecutors["future"]);
    }
}

[CollectionDefinition("WorkflowFeatureUsage", DisableParallelization = true)]
public sealed class WorkflowFeatureUsageScope;

[Collection("WorkflowFeatureUsage")]
public sealed class WorkflowFeatureUsageTests
{
    private sealed class NoOpExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder =>
                routeBuilder.AddHandler<object>((message, context) => context.SendMessageAsync(message)));
    }

    [Fact]
    public void Build_MarksOnlyTheActivatedWorkflowFeature()
    {
        // Arrange
        ResetFeatureUsage();
        WorkflowBuilder custom = new(new NoOpExecutor("custom"));
        OrchestrationTestHelpers.DoubleEchoAgent sequentialAgent = new("sequential");
        OrchestrationTestHelpers.DoubleEchoAgent concurrentAgent = new("concurrent");
        OrchestrationTestHelpers.DoubleEchoAgent groupChatAgent = new("group-chat");
        OrchestrationTestHelpers.DoubleEchoAgent magenticManager = new("magentic-manager");
        OrchestrationTestHelpers.DoubleEchoAgent magenticAgent = new("magentic-agent");
        OrchestrationTestHelpers.DoubleEchoAgent handoffCoordinator = new("handoff-coordinator");
        OrchestrationTestHelpers.DoubleEchoAgent handoffSpecialist = new("handoff-specialist");

        SequentialWorkflowBuilder sequential = new(sequentialAgent);
        ConcurrentWorkflowBuilder concurrent = new(concurrentAgent);
        GroupChatWorkflowBuilder groupChat = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents))
            .AddParticipants(groupChatAgent);
        MagenticWorkflowBuilder magentic = new MagenticWorkflowBuilder(magenticManager)
            .AddParticipants(magenticAgent)
            .RequirePlanSignoff(false);
        HandoffWorkflowBuilder handoff = AgentWorkflowBuilder
            .CreateHandoffBuilderWith(handoffCoordinator)
            .WithHandoff(handoffCoordinator, handoffSpecialist);

        (string Name, int FeatureIndex, Func<Workflow> Build)[] specialized =
        [
            ("sequential", (int)FeatureIndex.OrchestrationSequential, sequential.Build),
            ("concurrent", (int)FeatureIndex.OrchestrationConcurrent, concurrent.Build),
            ("group chat", (int)FeatureIndex.OrchestrationGroupChat, groupChat.Build),
            ("magentic", (int)FeatureIndex.OrchestrationMagentic, magentic.Build),
            ("handoff", (int)FeatureIndex.OrchestrationHandoff, handoff.Build),
        ];

        // Act and assert
        Assert.Equal(BigInteger.Zero, GetFeatureMask());

        _ = custom.Build();
        AssertFeatureMask(FeatureIndex.CoreWorkflow, "custom");

        foreach ((string name, int featureIndex, Func<Workflow> build) in specialized)
        {
            ResetFeatureUsage();
            _ = build();
            AssertFeatureMask(featureIndex, name);
        }
    }

    [Fact]
    public void Build_WhenValidationFails_DoesNotMarkCoreWorkflow()
    {
        // Arrange
        ResetFeatureUsage();
        WorkflowBuilder builder = new("unbound");

        // Act
        void build() => builder.Build();

        // Assert
        Assert.Throws<InvalidOperationException>(build);
        Assert.Equal(BigInteger.Zero, GetFeatureMask());
    }

    private static void AssertFeatureMask(FeatureIndex featureIndex, string workflowKind)
        => AssertFeatureMask((int)featureIndex, workflowKind);

    private static void AssertFeatureMask(int featureIndex, string workflowKind)
    {
        BigInteger expected = BigInteger.One << featureIndex;
        BigInteger actual = GetFeatureMask();
        Assert.True(
            actual == expected,
            $"Expected {workflowKind} workflow build to mark only feature bit {featureIndex}, but found mask 0x{actual:x}.");
    }

    private static BigInteger GetFeatureMask()
    {
#pragma warning disable MAAI001
        string userAgent = FeatureUsage.ApplyToUserAgent("test");
#pragma warning restore MAAI001
        const string Prefix = "test (feat=v1.";
        if (userAgent == "test")
        {
            return BigInteger.Zero;
        }

        Assert.StartsWith(Prefix, userAgent);
        Assert.EndsWith(")", userAgent);
        string mask = userAgent.Substring(Prefix.Length, userAgent.Length - Prefix.Length - 1);
        return BigInteger.Parse($"0{mask}", NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture);
    }

    private static void ResetFeatureUsage()
        => typeof(FeatureUsage)
            .GetMethod("ResetStateForTests", BindingFlags.Static | BindingFlags.NonPublic)!
            .Invoke(null, null);
}
