// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct.UnitTests;

public sealed class LocalExecuteCodeFunctionTests
{
    private static LocalCodeActProviderOptions Options(AIFunction tool) =>
        new()
        {
            ValidationDisabled = true, // No subprocess will be launched in these tests
            Tools = [tool],
        };

    [Fact]
    public void Description_WithParameterizedTool_CarriesHostToolSchema()
    {
        var tool = AIFunctionFactory.Create((string query) => "ok", name: "lookup");

        var function = new LocalExecuteCodeFunction("/usr/bin/python3", Options(tool));

        Assert.Contains("query", function.Description);
    }

    [Fact]
    public void JsonSchema_WithParameterizedTool_StaysCodeOnly()
    {
        var tool = AIFunctionFactory.Create((string query) => "ok", name: "lookup");

        var function = new LocalExecuteCodeFunction("/usr/bin/python3", Options(tool));
        var inputSchema = function.JsonSchema.GetRawText();

        Assert.Contains("\"code\"", inputSchema);
        Assert.DoesNotContain("query", inputSchema);
    }
}
