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

    [Fact]
    public async Task InvokeAsync_ReturnsErrorJsonOnExceptionAsync()
    {
        // Arrange
        static int Boom() => throw new InvalidOperationException("nope");
        var tool = AIFunctionFactory.Create(Boom, name: "boom");

        // Act
        var result = await ToolBridge.InvokeAsync(tool, "{}");

        // Assert
        using var doc = JsonDocument.Parse(result);
        Assert.True(doc.RootElement.TryGetProperty("error", out var err));
        Assert.Contains("nope", err.GetString()!);
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
        Assert.True(doc.RootElement.TryGetProperty("error", out _));
    }

    [Fact]
    public void Unwrap_ReturnsInnerWhenWrappedInApprovalRequired()
    {
        // Arrange
        var inner = AIFunctionFactory.Create(() => "ok", name: "inner");
        var wrapped = new ApprovalRequiredAIFunction(inner);

        // Act
        var actual = ToolBridge.Unwrap(wrapped);

        // Assert
        Assert.Same(inner, actual);
    }

    [Fact]
    public void Unwrap_ReturnsSameInstanceWhenNotWrapped()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "ok", name: "t");

        // Act
        var actual = ToolBridge.Unwrap(tool);

        // Assert
        Assert.Same(tool, actual);
    }
}
