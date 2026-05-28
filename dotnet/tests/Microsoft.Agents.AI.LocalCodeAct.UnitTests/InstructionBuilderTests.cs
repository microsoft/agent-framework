// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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
