// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Hyperlight.IntegrationTests;

/// <summary>
/// Integration tests that exercise a real Hyperlight sandbox. Gated by the
/// <c>HYPERLIGHT_PYTHON_GUEST_PATH</c> environment variable: when not set these
/// tests are skipped.
/// </summary>
public sealed class CodeActEndToEndTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

    private static string? GuestPath => Environment.GetEnvironmentVariable("HYPERLIGHT_PYTHON_GUEST_PATH");

    private static string SkipReason => "HYPERLIGHT_PYTHON_GUEST_PATH is not set; skipping hyperlight integration test.";

    [Fact]
    public async Task ExecuteCode_PythonPrint_ReturnsStdoutAsync()
    {
        // Skip if no guest available.
        if (string.IsNullOrWhiteSpace(GuestPath))
        {
            Assert.Skip(SkipReason);
            return;
        }

        // Arrange
        using var provider = new HyperlightCodeActProvider(
            HyperlightCodeActProviderOptions.CreateForWasm(GuestPath!));

        var context = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(s_mockAgent, session: null, new AIContext())).ConfigureAwait(false);

        var executeCode = Assert.IsAssignableFrom<AIFunction>(context.Tools![0]);

        // Act
        var rawResult = await executeCode.InvokeAsync(
            new AIFunctionArguments(new System.Collections.Generic.Dictionary<string, object?>
            {
                ["code"] = "print(\"hi\")",
            })).ConfigureAwait(false);

        // Assert
        var json = rawResult?.ToString();
        Assert.False(string.IsNullOrWhiteSpace(json));
        using var doc = JsonDocument.Parse(json!);
        Assert.True(doc.RootElement.GetProperty("success").GetBoolean());
        Assert.Contains("hi", doc.RootElement.GetProperty("stdout").GetString()!);
        Assert.Equal(0, doc.RootElement.GetProperty("exit_code").GetInt32());
    }
}
