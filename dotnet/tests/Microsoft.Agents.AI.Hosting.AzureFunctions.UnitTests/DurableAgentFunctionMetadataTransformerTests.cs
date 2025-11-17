// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Azure.Functions.Worker.Core.FunctionMetadata;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.UnitTests;

public sealed class DurableAgentFunctionMetadataTransformerTests
{
    [Theory]
    [InlineData(0, false, false, 1)] // entity only
    [InlineData(0, true, false, 2)] // entity + http
    [InlineData(0, false, true, 2)] // entity + mcp tool
    [InlineData(0, true, true, 3)] // entity + http + mcp tool
    [InlineData(3, true, true, 3)] // entity + http + mcp tool added to existing
    public void Transform_AddsAgentAndHttpTriggers_ForEachAgent(
        int initialMetadataEntryCount,
        bool enableHttp,
        bool enableMcp,
        int expectedMetadataCount)
    {
        // Arrange
        Dictionary<string, Func<IServiceProvider, AIAgent>> agents = new()
        {
            { "testAgent", _ => new TestAgent("testAgent", "Test agent description") }
        };

        FunctionsAgentOptions options = new();

        options.HttpTrigger.IsEnabled = enableHttp;
        options.McpToolTrigger.IsEnabled = enableMcp;

        IFunctionsAgentOptionsProvider agentOptionsProvider = new FakeOptionsProvider(new Dictionary<string, FunctionsAgentOptions>
        {
            { "testAgent", options }
        });

        List<IFunctionMetadata> metadataList = BuildFunctionMetadataList(initialMetadataEntryCount);

        DurableAgentFunctionMetadataTransformer transformer = new(
            agents,
            NullLogger<DurableAgentFunctionMetadataTransformer>.Instance,
            new FakeServiceProvider(),
            agentOptionsProvider);

        // Act
        transformer.Transform(metadataList);

        // Assert
        Assert.Equal(initialMetadataEntryCount + expectedMetadataCount, metadataList.Count);

        DefaultFunctionMetadata agentTrigger = Assert.IsType<DefaultFunctionMetadata>(metadataList[initialMetadataEntryCount]);
        Assert.Equal("dafx-testAgent", agentTrigger.Name);
        Assert.Contains("entityTrigger", agentTrigger.RawBindings![0]);

        if (enableHttp)
        {
            DefaultFunctionMetadata httpTrigger = Assert.IsType<DefaultFunctionMetadata>(metadataList[initialMetadataEntryCount + 1]);
            Assert.Equal("http-testAgent", httpTrigger.Name);
            Assert.Contains("httpTrigger", httpTrigger.RawBindings![0]);
        }

        if (enableMcp)
        {
            int mcpIndex = initialMetadataEntryCount + (enableHttp ? 2 : 1);
            DefaultFunctionMetadata mcpToolTrigger = Assert.IsType<DefaultFunctionMetadata>(metadataList[mcpIndex]);
            Assert.Equal("mcptool-testAgent", mcpToolTrigger.Name);
            Assert.Contains("mcpToolTrigger", mcpToolTrigger.RawBindings![0]);
        }
    }

    [Fact]
    public void Transform_AddsTriggers_ForMultipleAgents()
    {
        // Arrange
        Dictionary<string, Func<IServiceProvider, AIAgent>> agents = new()
        {
            { "agentA", _ => new TestAgent("testAgentA", "Test agent description") },
            { "agentB", _ => new TestAgent("testAgentB", "Test agent description") },
            { "agentC", _ => new TestAgent("testAgentC", "Test agent description") }
        };

        // Helper to create options with configurable triggers
        static FunctionsAgentOptions CreateFunctionsAgentOptions(bool httpEnabled, bool mcpEnabled)
        {
            FunctionsAgentOptions options = new();
            options.HttpTrigger.IsEnabled = httpEnabled;
            options.McpToolTrigger.IsEnabled = mcpEnabled;
            return options;
        }

        FunctionsAgentOptions agentOptionsA = CreateFunctionsAgentOptions(true, false);
        FunctionsAgentOptions agentOptionsB = CreateFunctionsAgentOptions(true, true);
        FunctionsAgentOptions agentOptionsC = CreateFunctionsAgentOptions(true, true);

        Dictionary<string, FunctionsAgentOptions> functionsAgentOptions = new()
        {
            { "agentA", agentOptionsA },
            { "agentB", agentOptionsB },
            { "agentC", agentOptionsC }
        };

        IFunctionsAgentOptionsProvider agentOptionsProvider = new FakeOptionsProvider(functionsAgentOptions);
        DurableAgentFunctionMetadataTransformer transformer = new(
            agents,
            NullLogger<DurableAgentFunctionMetadataTransformer>.Instance,
            new FakeServiceProvider(),
            agentOptionsProvider);

        const int InitialMetadataEntryCount = 2;
        List<IFunctionMetadata> metadataList = BuildFunctionMetadataList(InitialMetadataEntryCount);

        // Act
        transformer.Transform(metadataList);

        // Assert
        Assert.Equal(InitialMetadataEntryCount + (agents.Count * 2) + 2, metadataList.Count);

        foreach (string agentName in agents.Keys)
        {
            // The agent's entity trigger name is prefixed with "dafx-"
            DefaultFunctionMetadata entityMeta =
                Assert.IsType<DefaultFunctionMetadata>(
                    Assert.Single(metadataList, m => m.Name == $"dafx-{agentName}"));
            Assert.NotNull(entityMeta.RawBindings);
            Assert.Contains("entityTrigger", entityMeta.RawBindings[0]);

            DefaultFunctionMetadata httpMeta =
                Assert.IsType<DefaultFunctionMetadata>(
                    Assert.Single(metadataList, m => m.Name == $"http-{agentName}"));
            Assert.NotNull(httpMeta.RawBindings);
            Assert.Contains("httpTrigger", httpMeta.RawBindings[0]);
            Assert.Contains($"agents/{agentName}/run", httpMeta.RawBindings[0]);

            // We expect 2 mcp tool triggers only for agentB and agentC
            if (agentName == "agentB" || agentName == "agentC")
            {
                DefaultFunctionMetadata? mcpToolMeta =
                    Assert.Single(metadataList, m => m.Name == $"mcptool-{agentName}") as DefaultFunctionMetadata;
                Assert.NotNull(mcpToolMeta);
                Assert.NotNull(mcpToolMeta.RawBindings);
                Assert.Equal(4, mcpToolMeta.RawBindings.Count);
                Assert.Contains("mcpToolTrigger", mcpToolMeta.RawBindings[0]);
                Assert.Contains("mcpToolProperty", mcpToolMeta.RawBindings[1]); // We expect 2 tool property bindings
                Assert.Contains("mcpToolProperty", mcpToolMeta.RawBindings[2]);
            }
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
                RawBindings = ["{\r\n \"name\": \"context\",\r\n \"direction\": \"In\",\r\n \"type\": \"orchestrationTrigger\",\r\n \"properties\": {}\r\n }"],
                ScriptFile = "MyApp.dll"
            });
        }

        return list;
    }

    private sealed class FakeServiceProvider : IServiceProvider
    {
        public object? GetService(Type serviceType) => null;
    }

    private sealed class FakeOptionsProvider : IFunctionsAgentOptionsProvider
    {
        private readonly Dictionary<string, FunctionsAgentOptions> _map;

        public FakeOptionsProvider(Dictionary<string, FunctionsAgentOptions> map)
        {
            this._map = map ?? throw new ArgumentNullException(nameof(map));
        }

        public bool TryGet(string agentName, [NotNullWhen(true)] out FunctionsAgentOptions? options)
            => this._map.TryGetValue(agentName, out options);
    }
}
