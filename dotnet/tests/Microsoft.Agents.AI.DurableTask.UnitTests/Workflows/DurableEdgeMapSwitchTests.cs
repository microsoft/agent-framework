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

    private static FunctionExecutor<int, int> Router()
        => new(RouterId, (input, _, _) => input, outputTypes: [typeof(int)]);

    private static FunctionExecutor<int> Sink(string id)
        => new(id, (_, _, _) => default);

    private static Dictionary<string, Queue<DurableMessageEnvelope>> Route(Workflow workflow, int number)
    {
        WorkflowGraphInfo graphInfo = WorkflowAnalyzer.BuildGraphInfo(workflow);
        DurableEdgeMap edgeMap = new(graphInfo);
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
