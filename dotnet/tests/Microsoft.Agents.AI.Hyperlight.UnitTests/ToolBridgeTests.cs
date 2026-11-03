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
        const string InnerDetail = "synthetic inner diagnostic";
        static int Boom() => throw new InvalidOperationException(Detail, new ArgumentException(InnerDetail));
        static async Task<int> BoomAsync()
        {
            await Task.Yield();
            throw new InvalidOperationException(Detail, new ArgumentException(InnerDetail));
        }

        var tool = isAsync
            ? AIFunctionFactory.Create(BoomAsync, name: "boom")
            : AIFunctionFactory.Create(Boom, name: "boom");

        // Act
        var result = await ToolBridge.InvokeAsync(tool, "{}", includeDetailedErrors);

        // Assert
        using var doc = JsonDocument.Parse(result);
        Assert.True(doc.RootElement.TryGetProperty("error", out var err));
        var message = err.GetString()!;
        Assert.Equal(includeDetailedErrors, message.Contains(Detail, StringComparison.Ordinal));
        Assert.Equal(includeDetailedErrors, message.Contains(InnerDetail, StringComparison.Ordinal));
        Assert.Equal(includeDetailedErrors, message.Contains("   at ", StringComparison.Ordinal));
        if (includeDetailedErrors)
        {
            Assert.StartsWith($"System.InvalidOperationException: {Detail}", message, StringComparison.Ordinal);
            Assert.Contains($"System.ArgumentException: {InnerDetail}", message, StringComparison.Ordinal);
            Assert.Contains(isAsync ? nameof(BoomAsync) : nameof(Boom), message, StringComparison.Ordinal);
        }
        else
        {
            Assert.Equal("Host tool execution failed.", message);
        }
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

    [Theory]
    [InlineData(false, "[1, 2, 3]")]
    [InlineData(true, "[1, 2, 3]")]
    [InlineData(false, "{")]
    [InlineData(true, "{")]
    public async Task InvokeAsync_InvalidArgumentsFollowDetailedPolicyAsync(bool includeDetailedErrors, string argsJson)
    {
        // Arrange
        static string Hi() => "hi";
        var tool = AIFunctionFactory.Create(Hi, name: "hi");

        // Act
        var result = await ToolBridge.InvokeAsync(tool, argsJson, includeDetailedErrors);

        // Assert
        using var doc = JsonDocument.Parse(result);
        Assert.True(doc.RootElement.TryGetProperty("error", out var error));
        var message = error.GetString()!;
        Assert.NotEmpty(message);
        Assert.Equal(includeDetailedErrors, message.Contains("   at ", StringComparison.Ordinal));
        Assert.Equal(includeDetailedErrors, message.Contains(nameof(ToolBridge.ParseArguments), StringComparison.Ordinal));
        if (argsJson.StartsWith("[", StringComparison.Ordinal))
        {
            Assert.Contains("Tool arguments must be a JSON object.", message, StringComparison.Ordinal);
        }
    }
}
