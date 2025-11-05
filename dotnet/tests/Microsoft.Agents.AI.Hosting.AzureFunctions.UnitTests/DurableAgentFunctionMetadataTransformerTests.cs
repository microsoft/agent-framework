// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.UnitTests;

public sealed class DurableAgentFunctionMetadataTransformerTests
{
    [Theory]
    [InlineData(0)] // Empty original metadata list
    [InlineData(3)] // Non-empty original metadata list
    public void Transform_AddsAgentAndHttpTriggers_ForEachAgent(int initialMetadataEntryCount)
    {
        Dictionary<string, Func<IServiceProvider, AIAgent>> agents = new()
        {
            { "testAgent", _ => null! }
        };
        DurableAgentFunctionMetadataTransformer transformer = new(agents, GetTestLogger());
        List<IFunctionMetadata> metadataList = BuildFunctionMetadataList(initialMetadataEntryCount);

        transformer.Transform(metadataList);

        Assert.Equal(initialMetadataEntryCount + 2, metadataList.Count); // each agent adds 2 functions (http + entity).

        DefaultFunctionMetadata agentTrigger = Assert.IsType<DefaultFunctionMetadata>(metadataList[initialMetadataEntryCount]);
        Assert.Equal("dafx-testAgent", agentTrigger.Name);
        Assert.Equal("dotnet-isolated", agentTrigger.Language);
        Assert.Contains("type\":\"entityTrigger", agentTrigger.RawBindings![0]);

        DefaultFunctionMetadata httpTrigger = Assert.IsType<DefaultFunctionMetadata>(metadataList[initialMetadataEntryCount + 1]);
        Assert.Equal("testAgent_http", httpTrigger.Name);
        Assert.Equal("dotnet-isolated", httpTrigger.Language);
        Assert.Contains("type\":\"httpTrigger", httpTrigger.RawBindings![0]);
        Assert.Contains("route\":\"agents/testAgent/run", httpTrigger.RawBindings[0]);
    }

    [Fact]
    public void Transform_AddsTriggers_ForMultipleAgents()
    {
        Dictionary<string, Func<IServiceProvider, AIAgent>> agents = new()
        {
            { "agentA", _ => null! },
            { "agentB", _ => null! },
            { "agentC", _ => null! }
        };
        DurableAgentFunctionMetadataTransformer transformer = new(agents, GetTestLogger());
        const int InitialMetadataEntryCount = 2;
        List<IFunctionMetadata> metadataList = BuildFunctionMetadataList(InitialMetadataEntryCount);

        transformer.Transform(metadataList);

        Assert.Equal(InitialMetadataEntryCount + (agents.Count * 2), metadataList.Count);

        foreach (string agentName in agents.Keys)
        {
            // The agent's entity trigger name is prefixed with "dafx-"
            DefaultFunctionMetadata entityMeta =
                Assert.IsType<DefaultFunctionMetadata>(
                    Assert.Single(metadataList, m => m.Name == "dafx-" + agentName));
            Assert.NotNull(entityMeta.RawBindings);
            Assert.Contains("entityTrigger", entityMeta.RawBindings[0]);

            DefaultFunctionMetadata httpMeta =
                Assert.IsType<DefaultFunctionMetadata>(
                    Assert.Single(metadataList, m => m.Name == agentName + "_http"));
            Assert.NotNull(httpMeta.RawBindings);
            Assert.Contains("httpTrigger", httpMeta.RawBindings[0]);
            Assert.Contains($"agents/{agentName}/run", httpMeta.RawBindings[0]);
        }
    }

    private static List<IFunctionMetadata> BuildFunctionMetadataList(int numberOfFunctions)
    {
        List<IFunctionMetadata> list = [];
        for (int i = 0; i < numberOfFunctions; i++)
        {
            list.Add(new DefaultFunctionMetadata
            {
                Language = "dotnet-isolated",
                Name = $"SingleAgentOrchestration{i + 1}",
                EntryPoint = "MyApp.Functions.SingleAgentOrchestration",
                RawBindings =
                [
                    "{\r\n        \"name\": \"context\",\r\n        \"direction\": \"In\",\r\n        \"type\": \"orchestrationTrigger\",\r\n        \"properties\": {}\r\n      }"
                ],
                ScriptFile = "MyApp.dll"
            });
        }

        return list;
    }

    private static NullLogger<DurableAgentFunctionMetadataTransformer> GetTestLogger() => new();
}
