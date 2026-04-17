// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Hyperlight.Internal;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.UnitTests;

public sealed class InstructionBuilderTests
{
    [Fact]
    public void BuildContextInstructions_HiddenTools_MentionsCallTool()
    {
        // Act
        var text = InstructionBuilder.BuildContextInstructions(toolsVisibleToModel: false);

        // Assert
        Assert.Contains("execute_code", text);
        Assert.Contains("call_tool", text);
    }

    [Fact]
    public void BuildContextInstructions_VisibleTools_OmitsCallTool()
    {
        // Act
        var text = InstructionBuilder.BuildContextInstructions(toolsVisibleToModel: true);

        // Assert
        Assert.Contains("execute_code", text);
        Assert.DoesNotContain("call_tool", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithNoExtras_ReturnsBaseBlurbOnly()
    {
        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [],
            fileMounts: [],
            allowedDomains: [],
            workspaceRoot: null);

        // Assert
        Assert.Contains("Executes code", text);
        Assert.DoesNotContain("call_tool", text);
        Assert.DoesNotContain("Filesystem access", text);
        Assert.DoesNotContain("Outbound network access", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithTools_IncludesToolNames()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "ok", name: "fetch_docs", description: "fetch docs");

        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [tool],
            fileMounts: [],
            allowedDomains: [],
            workspaceRoot: null);

        // Assert
        Assert.Contains("call_tool", text);
        Assert.Contains("fetch_docs", text);
        Assert.Contains("fetch docs", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithFilesystem_IncludesFilesystemSection()
    {
        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [],
            fileMounts: [new FileMount("/host/data.csv", "/input/data.csv")],
            allowedDomains: [],
            workspaceRoot: "/host/workspace");

        // Assert
        Assert.Contains("Filesystem access", text);
        Assert.Contains("/input", text);
        Assert.Contains("/host/workspace", text);
        Assert.Contains("/input/data.csv", text);
        Assert.Contains("/host/data.csv", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithAllowedDomains_IncludesNetworkSection()
    {
        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [],
            fileMounts: [],
            allowedDomains: [new AllowedDomain("https://api.github.com", new List<string> { "GET", "POST" })],
            workspaceRoot: null);

        // Assert
        Assert.Contains("Outbound network access", text);
        Assert.Contains("api.github.com", text);
        Assert.Contains("GET", text);
        Assert.Contains("POST", text);
    }
}
