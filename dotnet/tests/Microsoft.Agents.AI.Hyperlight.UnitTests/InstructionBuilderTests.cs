// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
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
        // Backend-agnostic: don't mention a specific language.
        Assert.DoesNotContain("Python", text);
    }

    [Fact]
    public void BuildContextInstructions_VisibleTools_OmitsCallTool()
    {
        // Act
        var text = InstructionBuilder.BuildContextInstructions(toolsVisibleToModel: true);

        // Assert
        Assert.Contains("execute_code", text);
        Assert.DoesNotContain("call_tool", text);
        Assert.DoesNotContain("Python", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithNoExtras_ReturnsBaseBlurbOnly()
    {
        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [],
            fileMounts: [],
            allowedDomains: [],
            hasHostInputDirectory: false);

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
            hasHostInputDirectory: false);

        // Assert
        Assert.Contains("call_tool", text);
        Assert.Contains("fetch_docs", text);
        Assert.Contains("fetch docs", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithToolParameters_IncludesParameterMetadata()
    {
        // Arrange
        static string Lookup(
            [Description("Search text")] string query,
            [Description("Maximum results")] int limit = 10) => $"{query}:{limit}";

        var tool = AIFunctionFactory.Create(
            Lookup,
            name: "lookup",
            description: "Look up an item.");

        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [tool],
            fileMounts: [],
            allowedDomains: [],
            hasHostInputDirectory: false);

        // Assert
        Assert.Contains("lookup", text);
        Assert.Contains("query", text);
        Assert.Contains("Search text", text);
        Assert.Contains("Maximum results", text);

        // Requiredness and defaults separate the two parameters.
        Assert.Contains("\"required\":[\"query\"]", text);
        Assert.Contains("\"default\":10", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithZeroParameterTool_ReportsNoParameters()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "ok", name: "ping", description: "Pings.");

        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [tool],
            fileMounts: [],
            allowedDomains: [],
            hasHostInputDirectory: false);

        // Assert
        Assert.Contains("Parameters: none.", text);
        Assert.DoesNotContain("Parameters (JSON Schema)", text);
        Assert.DoesNotContain("\"properties\":{}", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithUnconstrainedSchema_OmitsParameterBlock()
    {
        // Arrange
        var tool = new StubTool("legacy_tool", "A tool that does not describe its input.");

        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [tool],
            fileMounts: [],
            allowedDomains: [],
            hasHostInputDirectory: false);

        // Assert
        Assert.Contains("legacy_tool", text);
        Assert.DoesNotContain("Parameters", text);
        Assert.DoesNotContain("{}", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithBooleanSchemaRoot_OmitsParameterBlock()
    {
        // Arrange — `true` is a valid JSON Schema root, and carries exactly as much
        // parameter information as `{}`: none.
        using var document = JsonDocument.Parse("true");
        var tool = new StubTool("gate", "Always-on gate.", document.RootElement);

        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [tool],
            fileMounts: [],
            allowedDomains: [],
            hasHostInputDirectory: false);

        // Assert
        Assert.Contains("gate", text);
        Assert.DoesNotContain("Parameters", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithFilesystem_IncludesSandboxPathsOnly()
    {
        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [],
            fileMounts: [new FileMount("/host/data.csv", "/input/data.csv")],
            allowedDomains: [],
            hasHostInputDirectory: true);

        // Assert
        Assert.Contains("Filesystem access", text);
        Assert.Contains("/input", text);
        Assert.Contains("/input/data.csv", text);

        // Host paths must not leak to the model.
        Assert.DoesNotContain("/host/workspace", text);
        Assert.DoesNotContain("/host/data.csv", text);
    }

    [Fact]
    public void BuildExecuteCodeDescription_WithAllowedDomains_IncludesNetworkSection()
    {
        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [],
            fileMounts: [],
            allowedDomains: [new AllowedDomain("https://api.github.com", new List<string> { "GET", "POST" })],
            hasHostInputDirectory: false);

        // Assert
        Assert.Contains("Outbound network access", text);
        Assert.Contains("api.github.com", text);
        Assert.Contains("GET", text);
        Assert.Contains("POST", text);
    }

    /// <summary>An <see cref="AIFunction"/> with a caller-supplied schema, or none at all.</summary>
    private sealed class StubTool : AIFunction
    {
        private readonly JsonElement? _schema;

        public StubTool(string name, string description, JsonElement? schema = null)
        {
            this.Name = name;
            this.Description = description;
            this._schema = schema;
        }

        public override string Name { get; }

        public override string Description { get; }

        public override JsonElement JsonSchema => this._schema ?? base.JsonSchema;

        protected override ValueTask<object?> InvokeCoreAsync(
            AIFunctionArguments arguments,
            CancellationToken cancellationToken) => new((object?)null);
    }
}
