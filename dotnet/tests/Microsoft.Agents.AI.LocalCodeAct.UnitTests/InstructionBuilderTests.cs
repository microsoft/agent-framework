// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using Microsoft.Agents.AI.LocalCodeAct.Internal;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class InstructionBuilderTests
{
    [Fact]
    public void BuildContextInstructions_ContainsExecuteCodeName()
    {
        var instructions = InstructionBuilder.BuildContextInstructions();
        Assert.Contains("execute_code", instructions);
    }

    [Fact]
    public void BuildExecuteCodeDescription_MentionsToolsWhenProvided()
    {
        var tools = new List<AIFunction> { new TestTool("get_weather", "Returns current weather.") };
        var description = InstructionBuilder.BuildExecuteCodeDescription(tools, new List<FileMount>());

        Assert.Contains("get_weather", description);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithToolParameters_IncludesParameterMetadata()
    {
        static string Lookup(
            [Description("Search text")] string query,
            [Description("Maximum results")] int limit = 10) => $"{query}:{limit}";

        var tool = AIFunctionFactory.Create(Lookup, name: "lookup", description: "Look up an item.");
        var description = InstructionBuilder.BuildExecuteCodeDescription(
            new List<AIFunction> { tool },
            new List<FileMount>());

        Assert.Contains("lookup", description);
        Assert.Contains("query", description);
        Assert.Contains("Search text", description);
        Assert.Contains("Maximum results", description);
        Assert.Contains("\"required\":[\"query\"]", description);
        Assert.Contains("\"default\":10", description);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithZeroParameterTool_ReportsNoParameters()
    {
        var tool = AIFunctionFactory.Create(() => "ok", name: "ping", description: "Pings.");
        var description = InstructionBuilder.BuildExecuteCodeDescription(
            new List<AIFunction> { tool },
            new List<FileMount>());

        Assert.Contains("Parameters: none.", description);
        Assert.DoesNotContain("Parameters (JSON Schema)", description);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithUnconstrainedSchema_OmitsParameterBlock()
    {
        var tools = new List<AIFunction> { new TestTool("legacy_tool", "Does not describe its input.") };
        var description = InstructionBuilder.BuildExecuteCodeDescription(tools, new List<FileMount>());

        Assert.Contains("legacy_tool", description);
        Assert.DoesNotContain("Parameters", description);
    }

    [Fact]
    public void BuildExecuteCodeDescription_MentionsMountsWhenProvided()
    {
        var mounts = new List<FileMount> { new("/host/data", "/app/data") };
        var description = InstructionBuilder.BuildExecuteCodeDescription(new List<AIFunction>(), mounts);

        Assert.Contains("/app/data", description);
    }

    private sealed class TestTool : AIFunction
    {
        public TestTool(string name, string description)
        {
            this.Name = name;
            this.Description = description;
        }

        public override string Name { get; }

        public override string Description { get; }

        protected override System.Threading.Tasks.ValueTask<object?> InvokeCoreAsync(AIFunctionArguments arguments, System.Threading.CancellationToken cancellationToken) =>
            new((object?)null);
    }
}
