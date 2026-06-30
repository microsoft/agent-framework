// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.DurableTask.Workflows.EdgeRouters;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.DurableTask.UnitTests.Workflows;

/// <summary>
/// Tests for <c>AddSwitch</c> support in durable workflows.
/// A switch (<c>AddSwitch</c>) reduces to a single fan-out edge carrying an
/// <c>EdgeAssigner</c> that selects the matching case's target(s). The durable
/// routing layer must honor that selection so only the matching executor runs.
/// </summary>
public sealed class DurableEdgeMapSwitchTests
{
    private const string RouterId = "router";
    private const string EvenId = "evenSink";
    private const string OddId = "oddSink";

    [Theory]
    [InlineData(4, EvenId, OddId)] // even -> first case matches
    [InlineData(7, OddId, EvenId)] // odd  -> second case matches
    public void RouteMessage_Switch_RoutesToMatchingCaseOnly(int number, string expected, string notExpected)
    {
        // Arrange: a switch with two mutually exclusive cases.
        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddSwitch(router, sb =>
        {
            sb.AddCase<int>(n => n % 2 == 0, Sink(EvenId));
            sb.AddCase<int>(n => n % 2 != 0, Sink(OddId));
        });

        // Act
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), number);

        // Assert: only the matching branch receives the message.
        Assert.Equal(1, QueuedCount(queues, expected));
        Assert.Equal(0, QueuedCount(queues, notExpected));
    }

    [Fact]
    public void RouteMessage_NoCaseMatches_RoutesToDefaultExecutorOnly()
    {
        // Arrange: a switch whose only case never matches, plus a default branch.
        const string MatchId = "matchSink";
        const string DefaultId = "defaultSink";

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddSwitch(router, sb =>
        {
            sb.AddCase<int>(n => n > 1000, Sink(MatchId));
            sb.WithDefault(Sink(DefaultId));
        });

        // Act: 5 does not match the case, so it must fall through to the default.
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), 5);

        // Assert: only the default branch receives the message.
        Assert.Equal(1, QueuedCount(queues, DefaultId));
        Assert.Equal(0, QueuedCount(queues, MatchId));
    }

    [Fact]
    public void RouteMessage_FanOutWithoutSelector_RoutesToAllTargets()
    {
        // Arrange: a plain fan-out edge (no target selector) must still reach every target.
        const string TargetAId = "targetA";
        const string TargetBId = "targetB";

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddFanOutEdge(router, [Sink(TargetAId), Sink(TargetBId)]);

        // Act
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), 42);

        // Assert: both targets receive the message.
        Assert.Equal(1, QueuedCount(queues, TargetAId));
        Assert.Equal(1, QueuedCount(queues, TargetBId));
    }

    [Fact]
    public void RouteMessage_SwitchWithSiblingDirectEdge_DeliversToSelectedCaseAndSibling()
    {
        // Arrange: a switch plus an ordinary direct edge from the same source. The switch selects one case,
        // while the sibling edge must always deliver (the switch must not suppress unrelated edges).
        const string AuditId = "audit";

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddSwitch(router, sb =>
        {
            sb.AddCase<int>(n => n % 2 == 0, Sink(EvenId));
            sb.AddCase<int>(n => n % 2 != 0, Sink(OddId));
        });
        builder.AddEdge(router, Sink(AuditId));

        // Act: 4 is even, so the even case matches; the audit sibling always receives the message.
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), 4);

        // Assert
        Assert.Equal(1, QueuedCount(queues, EvenId));
        Assert.Equal(0, QueuedCount(queues, OddId));
        Assert.Equal(1, QueuedCount(queues, AuditId));
    }

    [Fact]
    public void RouteMessage_MultipleSwitchesFromSameSource_HonorsEachIndependently()
    {
        // Arrange: two switches from the same source. Both must be evaluated; neither should overwrite the other.
        const string PositiveId = "positive";
        const string NonPositiveId = "nonPositive";

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddSwitch(router, sb =>
        {
            sb.AddCase<int>(n => n > 0, Sink(PositiveId));
            sb.WithDefault(Sink(NonPositiveId));
        });
        builder.AddSwitch(router, sb =>
        {
            sb.AddCase<int>(n => n % 2 == 0, Sink(EvenId));
            sb.WithDefault(Sink(OddId));
        });

        // Act: 4 is both positive and even.
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), 4);

        // Assert: the matching branch of each switch receives the message.
        Assert.Equal(1, QueuedCount(queues, PositiveId));
        Assert.Equal(0, QueuedCount(queues, NonPositiveId));
        Assert.Equal(1, QueuedCount(queues, EvenId));
        Assert.Equal(0, QueuedCount(queues, OddId));
    }

    [Fact]
    public void RouteMessage_SelectorReturnsDuplicateIndex_DeliversMessageOncePerIndex()
    {
        // Arrange: a selector that returns the same index twice must deliver twice (no de-duplication),
        // mirroring the in-process FanOutEdgeRunner.
        const string TargetId = "dupTarget";
        const string OtherId = "other";

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddFanOutEdge<int>(router, [Sink(TargetId), Sink(OtherId)], (_, _) => [0, 0]);

        // Act
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), 7);

        // Assert: index 0 was selected twice, so the target receives two messages.
        Assert.Equal(2, QueuedCount(queues, TargetId));
        Assert.Equal(0, QueuedCount(queues, OtherId));
    }

    [Fact]
    public void RouteMessage_SelectorReturnsOutOfRangeIndex_DoesNotThrow()
    {
        // Arrange: an out-of-range index must be surfaced (logged) rather than crash the routing layer.
        const string TargetId = "target";

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddFanOutEdge<int>(router, [Sink(TargetId)], (_, _) => [5]);

        // Act + Assert: routing swallows the bad index, nothing is delivered, and no exception escapes.
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), 7);

        Assert.Equal(0, QueuedCount(queues, TargetId));
    }

    [Fact]
    public void RouteMessage_SelectorReturnsMixedValidAndInvalidIndex_DeliversValidTargetsOnly()
    {
        // Arrange: a selector returning [0, 5] for two targets. The out-of-range index 5 must be skipped
        // without dropping the valid delivery to index 0.
        const string ValidId = "valid";
        const string OtherId = "other";

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddFanOutEdge<int>(router, [Sink(ValidId), Sink(OtherId)], (_, _) => [0, 5]);

        // Act
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), 7);

        // Assert: index 0 still receives the message; the invalid index is skipped.
        Assert.Equal(1, QueuedCount(queues, ValidId));
        Assert.Equal(0, QueuedCount(queues, OtherId));
    }

    [Fact]
    public void RouteMessage_SwitchCaseAndSiblingEdgeToSameTarget_BothDeliver()
    {
        // Arrange: a switch case and a sibling direct edge both target the same executor. The sibling edge must
        // still be wired even though the switch already routes to that target.
        FunctionExecutor<int> evenSink = Sink(EvenId);

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddSwitch(router, sb =>
        {
            sb.AddCase<int>(n => n % 2 == 0, evenSink);
            sb.AddCase<int>(n => n % 2 != 0, Sink(OddId));
        });
        builder.AddEdge(router, evenSink);

        // Act: 4 is even, so the switch routes to evenSink; the sibling direct edge also delivers to it.
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), 4);

        // Assert: evenSink receives the message twice (once via the switch case, once via the sibling edge).
        Assert.Equal(2, QueuedCount(queues, EvenId));
        Assert.Equal(0, QueuedCount(queues, OddId));
    }

    [Theory]
    [InlineData(4, 1)] // 4 > 3, sibling condition holds, audit receives the message
    [InlineData(2, 0)] // 2 > 3 is false, sibling condition fails, audit is skipped
    public void RouteMessage_SwitchWithConditionalSiblingEdge_HonorsSiblingCondition(int number, int expectedAuditCount)
    {
        // Arrange: a switch plus a conditional sibling direct edge from the same source. The sibling edge's
        // condition must be honored even though it shares a source with the selector.
        const string AuditId = "audit";

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddSwitch(router, sb =>
        {
            sb.AddCase<int>(n => n % 2 == 0, Sink(EvenId));
            sb.AddCase<int>(n => n % 2 != 0, Sink(OddId));
        });
        builder.AddEdge<int>(router, Sink(AuditId), n => n > 3);

        // Act: both inputs are even, so the switch always routes to the even branch.
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), number);

        // Assert: the switch delivers regardless; the audit sibling only delivers when its condition holds.
        Assert.Equal(1, QueuedCount(queues, EvenId));
        Assert.Equal(expectedAuditCount, QueuedCount(queues, AuditId));
    }

    [Fact]
    public void RouteMessage_SelectorThrows_DoesNotDeliverOrThrow()
    {
        // Arrange: a selector that throws when evaluated. Routing must swallow and log the failure rather
        // than crash the orchestration, and nothing should be delivered.
        const string TargetId = "target";
        const string OtherId = "other";

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddFanOutEdge<int>(router, [Sink(TargetId), Sink(OtherId)], (_, _) => throw new InvalidOperationException("boom"));

        // Act + Assert: the selector exception is swallowed, no message is delivered, and nothing escapes.
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = Route(builder.Build(), 7);

        Assert.Equal(0, QueuedCount(queues, TargetId));
        Assert.Equal(0, QueuedCount(queues, OtherId));
    }

    [Fact]
    public void IsFanInExecutor_SwitchCaseAndSiblingEdgeToSameTarget_NotTreatedAsFanIn()
    {
        // Arrange: a switch case and a sibling direct edge both target the same executor from the same source.
        // Those repeated deliveries originate from a single source, so the target must not be treated as a
        // fan-in (which would aggregate them into one invocation); it should run once per delivery, matching
        // the in-process contract where aggregation is reserved for explicit fan-in edges.
        FunctionExecutor<int> evenSink = Sink(EvenId);

        FunctionExecutor<int, int> router = Router();
        WorkflowBuilder builder = new(router);
        builder.AddSwitch(router, sb =>
        {
            sb.AddCase<int>(n => n % 2 == 0, evenSink);
            sb.AddCase<int>(n => n % 2 != 0, Sink(OddId));
        });
        builder.AddEdge(router, evenSink);

        DurableEdgeMap edgeMap = BuildEdgeMap(builder.Build());

        // Assert: a target fed twice by the same source is not a fan-in point.
        Assert.False(edgeMap.IsFanInExecutor(EvenId));
    }

    [Fact]
    public void IsFanInExecutor_MultipleDistinctSources_TreatedAsFanIn()
    {
        // Arrange: a diamond where two distinct sources converge on one target — a genuine fan-in.
        FunctionExecutor<int, int> start = new("start", (input, _, _) => input, outputTypes: [typeof(int)]);
        FunctionExecutor<int, int> left = new("left", (input, _, _) => input, outputTypes: [typeof(int)]);
        FunctionExecutor<int, int> right = new("right", (input, _, _) => input, outputTypes: [typeof(int)]);
        FunctionExecutor<int> target = Sink("target");

        WorkflowBuilder builder = new(start);
        builder.AddEdge(start, left);
        builder.AddEdge(start, right);
        builder.AddEdge(left, target);
        builder.AddEdge(right, target);

        DurableEdgeMap edgeMap = BuildEdgeMap(builder.Build());

        // Assert: two distinct predecessors still register as a fan-in point.
        Assert.True(edgeMap.IsFanInExecutor("target"));
    }

    private static FunctionExecutor<int, int> Router()
        => new(RouterId, (input, _, _) => input, outputTypes: [typeof(int)]);

    private static FunctionExecutor<int> Sink(string id)
        => new(id, (_, _, _) => default);

    private static DurableEdgeMap BuildEdgeMap(Workflow workflow)
        => new(WorkflowAnalyzer.BuildGraphInfo(workflow));

    private static Dictionary<string, Queue<DurableMessageEnvelope>> Route(Workflow workflow, int number)
    {
        DurableEdgeMap edgeMap = BuildEdgeMap(workflow);
        Dictionary<string, Queue<DurableMessageEnvelope>> queues = [];

        edgeMap.RouteMessage(
            RouterId,
            JsonSerializer.Serialize(number, DurableSerialization.Options),
            typeof(int).AssemblyQualifiedName,
            queues,
            NullLogger.Instance);

        return queues;
    }

    private static int QueuedCount(Dictionary<string, Queue<DurableMessageEnvelope>> queues, string executorId)
        => queues.TryGetValue(executorId, out Queue<DurableMessageEnvelope>? queue) ? queue.Count : 0;
}
