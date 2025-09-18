// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.UnitTests;

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

        FanInEdgeData edgeData = new(["executor1", "executor2"], "executor3", new EdgeId(0));
        Edge fanInEdge = new(edgeData);

        workflowEdges["executor1"] = [fanInEdge];
        workflowEdges["executor2"] = [fanInEdge];

        EdgeMap edgeMap = new(runContext, workflowEdges, [], "executor1", null);

        await edgeMap.InvokeEdgeAsync(fanInEdge, "executor1", new("part1"));
        MessageDeliveryValidation.CheckForwarded(runContext.QueuedMessages);

        await edgeMap.InvokeEdgeAsync(fanInEdge, "executor2", new("part2"));
        MessageDeliveryValidation.CheckForwarded(runContext.QueuedMessages, ("executor3", ["part1", "part2"]));
    }
}
