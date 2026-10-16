// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.UnitTests;

public sealed class HyperlightExecuteCodeFunctionTests
{
    [Fact]
    public void Description_WithParameterizedTool_CarriesHostToolSchema()
    {
        // Arrange
        var tool = AIFunctionFactory.Create((string query) => "ok", name: "lookup");

        // Act
        using var function = new HyperlightExecuteCodeFunction(new HyperlightCodeActProviderOptions
        {
            Tools = [tool],
        });

        // Assert
        Assert.Contains("query", function.Description);
    }

    [Fact]
    public void JsonSchema_WithParameterizedTool_StaysCodeOnly()
    {
        // Arrange
        var tool = AIFunctionFactory.Create((string query) => "ok", name: "lookup");

        // Act
        using var function = new HyperlightExecuteCodeFunction(new HyperlightCodeActProviderOptions
        {
            Tools = [tool],
        });
        var inputSchema = function.JsonSchema.GetRawText();

        // Assert — host-tool schemas are documentation inside the description only; they
        // must never widen execute_code's own input contract.
        Assert.Contains("\"code\"", inputSchema);
        Assert.DoesNotContain("query", inputSchema);
    }
}
