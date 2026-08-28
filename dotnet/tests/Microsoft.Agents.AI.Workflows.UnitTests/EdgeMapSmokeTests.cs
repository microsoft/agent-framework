// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.Specialized;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class EdgeMapSmokeTests
{
    [Fact]
    public async Task Test_EdgeMap_RoutesStaticPortAsync()
    {
        TestRunContext runContext = new();

        RequestPort staticPort = RequestPort.Create<string, int>("port1");
        RequestInfoExecutor executor = new(staticPort);
        EdgeMap edgeMap = new(runContext, [], [staticPort], executor.Id, null);

        runContext.ConfigureExecutor(executor, edgeMap);

        ExternalResponse responseMessage = new(staticPort.ToPortInfo(), "Request1", new(12));

        DeliveryMapping? mapping = await edgeMap.PrepareDeliveryForResponseAsync(responseMessage);
        Assert.NotNull(mapping);

        List<MessageDelivery> deliveries = mapping.Deliveries.ToList();
        MessageDelivery delivery = Assert.Single(deliveries);
        Assert.Equal(executor.Id, delivery.TargetId);
        Assert.Equal(responseMessage, delivery.Envelope.Message);
    }

    [Fact]
    public async Task Test_EdgeMap_RoutesDynamicPortAsync()
    {
        TestRunContext runContext = new();

        DynamicPortsExecutor<string, int> executor = new("executor1", "port1", "port2");
        EdgeMap edgeMap = new(runContext, [], [], executor.Id, null);

        runContext.ConfigureExecutor(executor, edgeMap);

        await RunPortTestAsync("port1");
        await RunPortTestAsync("port2");

        async ValueTask RunPortTestAsync(string portId)
        {
            PortBinding binding = executor.PortBindings[portId];
            ExternalResponse responseMessage = new(binding.Port.ToPortInfo(), $"RequestFor[{portId}]", new(10));

            DeliveryMapping? mapping = await edgeMap.PrepareDeliveryForResponseAsync(responseMessage);
            Assert.NotNull(mapping);

            List<MessageDelivery> deliveries = mapping.Deliveries.ToList();
            MessageDelivery delivery = Assert.Single(deliveries);
            Assert.Equal(executor.Id, delivery.TargetId);
            Assert.Equal(responseMessage, delivery.Envelope.Message);
        }
    }

    [Fact]
    public async Task Test_EdgeMap_DoesNotRouteUnregisteredPortAsync()
    {
        TestRunContext runContext = new();

        RequestPort staticPort = RequestPort.Create<string, int>("port1");
        RequestInfoExecutor staticExecutor = new(staticPort);
        DynamicPortsExecutor<string, int> executor = new("executor1", "port2", "port3");
        EdgeMap edgeMap = new(runContext, [], [staticPort], executor.Id, null);

        runContext.ConfigureExecutors([staticExecutor, executor], edgeMap);

        await RunPortTestAsync("port4");

        async ValueTask RunPortTestAsync(string portId)
        {
            RequestPort fakePort = RequestPort.Create<string, int>(portId);

            ExternalResponse responseMessage = new(fakePort.ToPortInfo(), $"RequestFor[{portId}]", new(10));

            async Task<DeliveryMapping?> mappingTaskAsync() => await edgeMap.PrepareDeliveryForResponseAsync(responseMessage);
            await Assert.ThrowsAsync<InvalidOperationException>((Func<Task<DeliveryMapping?>>)mappingTaskAsync);
        }
    }

    [Fact]
    public async Task Test_EdgeMap_MaintainsFanInEdgeStateAsync()
    {
        TestRunContext runContext = new();
        Dictionary<string, HashSet<Edge>> workflowEdges = [];

        FanInEdgeData edgeData = new(["executor1", "executor2"], "executor3", new EdgeId(0), null);
        Edge fanInEdge = new(edgeData);

        workflowEdges["executor1"] = [fanInEdge];
        workflowEdges["executor2"] = [fanInEdge];
        EdgeMap edgeMap = new(runContext, workflowEdges, [], "executor1", null);

        runContext.ConfigureExecutors(
            [
                new ForwardMessageExecutor<string>("executor1"),
                new ForwardMessageExecutor<string>("executor2"),
                new ForwardMessageExecutor<string>("executor3")
            ], edgeMap);

        DeliveryMapping? mapping = await edgeMap.PrepareDeliveryForEdgeAsync(fanInEdge, new("part1", "executor1"));
        Assert.Null(mapping);

        mapping = await edgeMap.PrepareDeliveryForEdgeAsync(fanInEdge, new("part2", "executor2"));
        Assert.NotNull(mapping);
        List<MessageDelivery> deliveries = mapping.Deliveries.ToList();

        Assert.Equal(2, deliveries.Count);
        Assert.All(deliveries!, delivery => Assert.Equal("executor3", delivery.TargetId));

        HashSet<string> expectedMessages = ["part1", "part2"];
        foreach (MessageDelivery delivery in deliveries)
        {
            string? message = Assert.IsType<PortableValue>(delivery.Envelope.Message).As<string>();
            Assert.NotNull(message);
            expectedMessages.Remove(message);
        }
    }
}
