// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hyperlight.Internal;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.UnitTests;

public sealed class ToolBridgeTests
{
    [Fact]
    public async Task InvokeAsync_PassesArgumentsAndReturnsSerializedResultAsync()
    {
        // Arrange
        static string Echo(string value) => $"echo:{value}";
        var tool = AIFunctionFactory.Create(Echo, name: "echo");

        // Act
        var result = await ToolBridge.InvokeAsync(tool, """{"value":"hello"}""");

        // Assert — AIFunction.InvokeAsync returns the string; ToolBridge JSON-encodes it.
        Assert.Equal("\"echo:hello\"", result);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task InvokeAsync_ReturnsErrorJsonOnExceptionAsync(bool includeDetailedErrors, bool isAsync)
    {
        // Arrange
        const string Detail = "synthetic backend diagnostic";
        static int Boom() => throw new InvalidOperationException(Detail);
        static async Task<int> BoomAsync()
        {
            await Task.Yield();
            throw new InvalidOperationException(Detail);
        }

        var tool = isAsync
            ? AIFunctionFactory.Create(BoomAsync, name: "boom")
            : AIFunctionFactory.Create(Boom, name: "boom");

        // Act
        var result = await ToolBridge.InvokeAsync(tool, "{}", includeDetailedErrors);

        // Assert
        using var doc = JsonDocument.Parse(result);
        Assert.True(doc.RootElement.TryGetProperty("error", out var err));
        Assert.Equal(includeDetailedErrors ? Detail : "Host tool execution failed.", err.GetString());
        Assert.Equal(includeDetailedErrors, result.Contains(Detail, StringComparison.Ordinal));
    }

    [Fact]
    public async Task InvokeAsync_EmptyArguments_InvokesToolWithNoArgsAsync()
    {
        // Arrange
        static string Hi() => "hi";
        var tool = AIFunctionFactory.Create(Hi, name: "hi");

        // Act
        var result = await ToolBridge.InvokeAsync(tool, string.Empty);

        // Assert
        Assert.Equal("\"hi\"", result);
    }

    [Fact]
    public async Task InvokeAsync_NonObjectJson_ReturnsErrorAsync()
    {
        // Arrange
        static string Hi() => "hi";
        var tool = AIFunctionFactory.Create(Hi, name: "hi");

        // Act
        var result = await ToolBridge.InvokeAsync(tool, "[1, 2, 3]");

        // Assert
        using var doc = JsonDocument.Parse(result);
        Assert.True(doc.RootElement.TryGetProperty("error", out var error));
        Assert.Contains("Tool arguments must be a JSON object.", error.GetString()!, StringComparison.Ordinal);
    }
}
