// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hyperlight.Internal;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Hyperlight.UnitTests;

public sealed class InstructionBuilderTests
{
    private static readonly AIAgent s_mockAgent = new Mock<AIAgent>().Object;

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
    public async Task BuildExecuteCodeDescription_WithParameterizedTools_IncludesHostToolJsonSchemaAsync()
    {
        // Arrange — zero-parameter tools already have coverage above; this locks the
        // host-tool JsonSchema gap tracked by microsoft/agent-framework#8446.
        // Stick to reflection-friendly primitives so AOT/source-gen test hosts can build the schema.
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

        // Assert — model-facing description must carry the host tool parameter schema.
        Assert.Contains("lookup", text);
        Assert.Contains("Look up an item.", text);
        Assert.Contains("Parameters (JSON Schema)", text);
        Assert.Contains(tool.JsonSchema.GetRawText(), text);
        Assert.Contains("query", text);
        Assert.Contains("Search text", text);
        Assert.Contains("limit", text);
        Assert.Contains("Maximum results", text);

        // Host schemas are documentation only; they must not replace execute_code's code-only input.
        using var executeCode = new HyperlightExecuteCodeFunction(new HyperlightCodeActProviderOptions
        {
            Tools = [tool],
        });
        Assert.Contains("\"code\"", executeCode.JsonSchema.GetRawText());
        Assert.DoesNotContain("\"query\"", executeCode.JsonSchema.GetRawText());
        Assert.DoesNotContain("\"limit\"", executeCode.JsonSchema.GetRawText());

        using var provider = new HyperlightCodeActProvider(new HyperlightCodeActProviderOptions
        {
            Tools = [tool],
        });
        var context = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(s_mockAgent, session: null, new AIContext()));
        var providerFn = Assert.IsAssignableFrom<AIFunction>(context!.Tools!.First());
        Assert.Contains("\"code\"", providerFn.JsonSchema.GetRawText());
        Assert.DoesNotContain("\"query\"", providerFn.JsonSchema.GetRawText());
        Assert.DoesNotContain("\"limit\"", providerFn.JsonSchema.GetRawText());
    }

    [Theory]
    [InlineData("true")]
    [InlineData("false")]
    public void BuildExecuteCodeDescription_WithBooleanJsonSchema_IncludesBooleanRoot(string schemaJson)
    {
        // Arrange — boolean JSON Schema roots are valid and must surface to the model.
        var tool = new BooleanSchemaTool("gate", "Always-on gate.", schemaJson);

        // Act
        var text = InstructionBuilder.BuildExecuteCodeDescription(
            tools: [tool],
            fileMounts: [],
            allowedDomains: [],
            hasHostInputDirectory: false);

        // Assert
        Assert.Contains("gate", text);
        Assert.Contains("Parameters (JSON Schema)", text);
        Assert.Contains(schemaJson, text);
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

    private sealed class BooleanSchemaTool : AIFunction
    {
        private readonly JsonDocument _schemaDocument;

        public BooleanSchemaTool(string name, string description, string schemaJson)
        {
            this.Name = name;
            this.Description = description;
            this._schemaDocument = JsonDocument.Parse(schemaJson);
        }

        public override string Name { get; }

        public override string Description { get; }

        public override JsonElement JsonSchema => this._schemaDocument.RootElement;

        protected override ValueTask<object?> InvokeCoreAsync(
            AIFunctionArguments arguments,
            System.Threading.CancellationToken cancellationToken) =>
            new((object?)null);
    }
}
