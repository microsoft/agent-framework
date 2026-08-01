// Copyright (c) Microsoft. All rights reserved.

using System.Reflection;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.UnitTests.Workflows;

public sealed class WorkflowPublicApiTests
{
    [Fact]
    public void WorkflowRoutingMetadata_IsAccessibleToExternalConsumers()
    {
        // Arrange
        FunctionExecutor<string> source = new("source", static (_, _, _) => default);
        FunctionExecutor<string> directTarget = new("direct-target", static (_, _, _) => default);
        FunctionExecutor<string> fanOutTarget1 = new("fan-out-target-1", static (_, _, _) => default);
        FunctionExecutor<string> fanOutTarget2 = new("fan-out-target-2", static (_, _, _) => default);

        Workflow workflow = new WorkflowBuilder(source)
            .AddEdge<string>(source, directTarget, static message => message == "direct")
            .AddFanOutEdge<string>(
                source,
                [fanOutTarget1, fanOutTarget2],
                static (message, _) => message == "fan-out" ? [0, 1] : [])
            .Build();

        // Act
        IReadOnlyDictionary<string, IReadOnlyCollection<Edge>> edges = workflow.Edges;
        Edge directEdge = Assert.Single(edges[source.Id], edge => edge.Kind == EdgeKind.Direct);
        Edge fanOutEdge = Assert.Single(edges[source.Id], edge => edge.Kind == EdgeKind.FanOut);
        DirectEdgeData directData = Assert.IsType<DirectEdgeData>(directEdge.Data);
        FanOutEdgeData fanOutData = Assert.IsType<FanOutEdgeData>(fanOutEdge.Data);

        // Assert
        Assert.Equal([source.Id], directEdge.Data.Connection.SourceIds);
        Assert.Equal([directTarget.Id], directEdge.Data.Connection.SinkIds);
        Assert.NotNull(directData.Condition);
        Assert.True(directData.Condition!("direct"));
        Assert.False(directData.Condition!("other"));

        Assert.Equal(source.Id, fanOutData.SourceId);
        Assert.Equal([fanOutTarget1.Id, fanOutTarget2.Id], fanOutData.SinkIds);
        Assert.Equal([source.Id], fanOutEdge.Data.Connection.SourceIds);
        Assert.Equal([fanOutTarget1.Id, fanOutTarget2.Id], fanOutEdge.Data.Connection.SinkIds);
        Assert.NotNull(fanOutData.EdgeAssigner);
        Assert.Equal([0, 1], fanOutData.EdgeAssigner!("fan-out", 2));

        PropertyInfo edgesProperty = typeof(Workflow).GetProperty(nameof(Workflow.Edges))!;
        Assert.True(edgesProperty.GetMethod!.IsPublic);
        Assert.True(edgesProperty.SetMethod!.IsAssembly);
        Assert.Equal(typeof(IReadOnlyDictionary<string, IReadOnlyCollection<Edge>>), edgesProperty.PropertyType);
    }
}
