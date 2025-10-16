// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class EdgeMapSmokeTests
{
    [Fact]
    public async Task Test_EdgeMap_MaintainsFanInEdgeStateAsync()
    {
        TestRunContext runContext = new();

        runContext.Executors["executor1"] = new ForwardMessageExecutor<string>("executor1");
        runContext.Executors["executor2"] = new ForwardMessageExecutor<string>("executor2");
        runContext.Executors["executor3"] = new ForwardMessageExecutor<string>("executor3");

        Dictionary<string, HashSet<Edge>> workflowEdges = [];

        FanInEdgeData edgeData = new(["executor1", "executor2"], "executor3", new EdgeId(0), null);
        Edge fanInEdge = new(edgeData);

        workflowEdges["executor1"] = [fanInEdge];
        workflowEdges["executor2"] = [fanInEdge];

        EdgeMap edgeMap = new(runContext, workflowEdges, [], "executor1", null);

        DeliveryMapping? mapping = await edgeMap.PrepareDeliveryForEdgeAsync(fanInEdge, new("part1", "executor1"));
        mapping.Should().BeNull();

        mapping = await edgeMap.PrepareDeliveryForEdgeAsync(fanInEdge, new("part2", "executor2"));
        mapping.Should().NotBeNull();
        List<MessageDelivery> deliveries = mapping.Deliveries.ToList();

        deliveries.Should().HaveCount(2).And.AllSatisfy(delivery => delivery.TargetId.Should().Be("executor3"));

        HashSet<string> expectedMessages = ["part1", "part2"];
        foreach (MessageDelivery delivery in deliveries)
        {
            string message = delivery.Envelope.As<string>()!;
            expectedMessages.Remove(message);
        }
    }
}
