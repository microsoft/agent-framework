// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for argument marshaling integration via <c>Func&lt;JsonElement?, AIFunctionArguments&gt;</c>.
/// </summary>
public sealed class SkillScriptArgumentMarshalerTests
{
    /// <summary>
    /// Creates a JsonElement with ValueKind.String containing the given string value.
    /// This simulates how vLLM backends send arguments as a string-wrapped JSON object.
    /// </summary>
    private static JsonElement CreateStringElement(string value)
    {
        // JSON encoding of a string value: surround with quotes and escape inner quotes
        string json = "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.Clone();
    }

    [Fact]
    public async Task DefaultMarshaler_NullArguments_ReturnsEmptyAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript("test", () => "ok");
        var skill = new AgentInlineSkill("s", "d", "i");

        // Act
        var result = await script.RunAsync(skill, null, null, CancellationToken.None);

        // Assert
        Assert.Equal("ok", result?.ToString());
    }

    [Fact]
    public async Task DefaultMarshaler_JsonNull_ReturnsEmptyAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript("test", () => "ok");
        var skill = new AgentInlineSkill("s", "d", "i");
        using var doc = JsonDocument.Parse("null");
        var element = doc.RootElement.Clone();

        // Act
        var result = await script.RunAsync(skill, element, null, CancellationToken.None);

        // Assert
        Assert.Equal("ok", result?.ToString());
    }

    [Fact]
    public async Task DefaultMarshaler_UndefinedArguments_ReturnsEmptyAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript("test", () => "ok");
        var skill = new AgentInlineSkill("s", "d", "i");
        JsonElement? element = default(JsonElement); // ValueKind == Undefined

        // Act
        var result = await script.RunAsync(skill, element, null, CancellationToken.None);

        // Assert
        Assert.Equal("ok", result?.ToString());
    }

    [Fact]
    public async Task DefaultMarshaler_ObjectArguments_PassesPropertiesAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript("test", (string query, int maxResults) => $"{query}:{maxResults}");
        var skill = new AgentInlineSkill("s", "d", "i");
        using var doc = JsonDocument.Parse("""{"query":"hello","maxResults":5}""");
        var element = doc.RootElement.Clone();

        // Act
        var result = await script.RunAsync(skill, element, null, CancellationToken.None);

        // Assert
        Assert.Equal("hello:5", result?.ToString());
    }

    [Fact]
    public async Task DefaultMarshaler_StringArguments_ThrowsAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript("test", (string query) => query);
        var skill = new AgentInlineSkill("s", "d", "i");
        var element = CreateStringElement("{\"query\": \"hello\"}");

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => script.RunAsync(skill, element, null, CancellationToken.None));
        Assert.Contains("String", ex.Message);
    }

    [Fact]
    public async Task DefaultMarshaler_NumberArguments_ThrowsAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript("test", (string query) => query);
        var skill = new AgentInlineSkill("s", "d", "i");
        using var doc = JsonDocument.Parse("42");
        var element = doc.RootElement.Clone();

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => script.RunAsync(skill, element, null, CancellationToken.None));
        Assert.Contains("Number", ex.Message);
    }

    [Fact]
    public async Task InlineSkillScript_UsesCustomMarshaler_WhenProvidedAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript(
            "test-script",
            (string query) => $"result: {query}",
            argumentMarshaler: StringParsingMarshaler);
        var skill = new AgentInlineSkill("test-skill", "desc", "instructions");

        // Create string-wrapped JSON arguments (simulating vLLM behavior)
        var stringArgs = CreateStringElement("{\"query\":\"hello\"}");

        // Act
        var result = await script.RunAsync(skill, stringArgs, null, CancellationToken.None);

        // Assert
        Assert.Equal("result: hello", result?.ToString());
    }

    [Fact]
    public async Task InlineSkill_SkillLevelMarshaler_InheritedByScriptsAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("test-skill", "desc", "instructions", argumentMarshaler: StringParsingMarshaler)
            .AddScript("search", (string query) => $"found: {query}");

        var script = await skill.GetScriptAsync("search", CancellationToken.None);
        Assert.NotNull(script);

        // Create string-wrapped JSON arguments
        var stringArgs = CreateStringElement("{\"query\":\"world\"}");

        // Act
        var result = await script.RunAsync(skill, stringArgs, null, CancellationToken.None);

        // Assert
        Assert.Equal("found: world", result?.ToString());
    }

    [Fact]
    public async Task InlineSkillScript_ScriptLevelMarshaler_OverridesSkillLevelAsync()
    {
        // Arrange — skill has a throwing marshaler, but script has its own
        Func<JsonElement?, AIFunctionArguments> throwingMarshaler = ThrowingMarshaler;

        var skill = new AgentInlineSkill("test-skill", "desc", "instructions", argumentMarshaler: throwingMarshaler);
        // Create a script directly with a per-script marshaler
        var script = new AgentInlineSkillScript("search", (string query) => $"found: {query}", argumentMarshaler: StringParsingMarshaler);

        // Create string-wrapped JSON arguments
        var stringArgs = CreateStringElement("{\"query\":\"test\"}");

        // Act — should use scriptMarshaler (not the throwing skill marshaler)
        var result = await script.RunAsync(skill, stringArgs, null, CancellationToken.None);

        // Assert
        Assert.Equal("found: test", result?.ToString());
    }

    [Fact]
    public async Task ClassSkill_ArgumentMarshaler_UsedByDiscoveredScriptsAsync()
    {
        // Arrange
        var skill = new TestClassSkillWithMarshaler();
        var script = await skill.GetScriptAsync("greet", CancellationToken.None);
        Assert.NotNull(script);

        // Create string-wrapped JSON arguments
        var stringArgs = CreateStringElement("{\"name\":\"Alice\"}");

        // Act
        var result = await script.RunAsync(skill, stringArgs, null, CancellationToken.None);

        // Assert
        Assert.Equal("Hello, Alice!", result?.ToString());
    }

    [Fact]
    public async Task ClassSkill_CreateScript_UsesArgumentMarshalerAsync()
    {
        // Arrange — a class skill that defines its scripts programmatically via CreateScript
        var skill = new TestClassSkillWithCreateScript();
        var script = await skill.GetScriptAsync("echo", CancellationToken.None);
        Assert.NotNull(script);

        // Create string-wrapped JSON arguments (simulating vLLM behavior)
        var stringArgs = CreateStringElement("{\"value\":\"hi\"}");

        // Act
        var result = await script.RunAsync(skill, stringArgs, null, CancellationToken.None);

        // Assert
        Assert.Equal("echo: hi", result?.ToString());
    }

    [Fact]
    public async Task ClassSkill_NoMarshaler_UsesDefaultObjectMarshalingAsync()
    {
        // Arrange — a class skill without a custom marshaler falls back to default behavior
        var skill = new TestClassSkillWithoutMarshaler();
        var script = await skill.GetScriptAsync("greet", CancellationToken.None);
        Assert.NotNull(script);

        using var doc = JsonDocument.Parse("""{"name":"Bob"}""");
        var objectArgs = doc.RootElement.Clone();

        // Act — plain JSON object is marshaled by the default marshaler
        var result = await script.RunAsync(skill, objectArgs, null, CancellationToken.None);

        // Assert
        Assert.Equal("Hello, Bob!", result?.ToString());
    }

    [Fact]
    public async Task ClassSkill_NoMarshaler_StringArguments_ThrowsAsync()
    {
        // Arrange — default marshaler rejects string-wrapped arguments
        var skill = new TestClassSkillWithoutMarshaler();
        var script = await skill.GetScriptAsync("greet", CancellationToken.None);
        Assert.NotNull(script);

        var stringArgs = CreateStringElement("{\"name\":\"Bob\"}");

        // Act & Assert
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(
            () => script.RunAsync(skill, stringArgs, null, CancellationToken.None));
        Assert.Contains("String", ex.Message);
    }

    /// <summary>
    /// A custom marshaler function that handles string-wrapped JSON (simulating the vLLM fix).
    /// </summary>
    private static AIFunctionArguments StringParsingMarshaler(JsonElement? arguments)
    {
        if (arguments is null ||
            arguments.Value.ValueKind == JsonValueKind.Null ||
            arguments.Value.ValueKind == JsonValueKind.Undefined)
        {
            return [];
        }

        JsonElement element = arguments.Value;

        if (element.ValueKind == JsonValueKind.String)
        {
            string? raw = element.GetString();
            if (raw is not null)
            {
                using var innerDoc = JsonDocument.Parse(raw);
                element = innerDoc.RootElement.Clone();
            }
        }

        if (element.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidOperationException($"Cannot marshal arguments of kind '{element.ValueKind}'.");
        }

        var dict = new Dictionary<string, object?>();
        foreach (var property in element.EnumerateObject())
        {
            dict[property.Name] = property.Value;
        }

        return new AIFunctionArguments(dict);
    }

    /// <summary>
    /// A marshaler function that always throws — used to verify override behavior.
    /// </summary>
    private static AIFunctionArguments ThrowingMarshaler(JsonElement? arguments)
    {
        throw new InvalidOperationException("ThrowingMarshaler should not be called.");
    }

    /// <summary>
    /// A class-based skill with a custom argument marshaler.
    /// </summary>
    private sealed class TestClassSkillWithMarshaler : AgentClassSkill<TestClassSkillWithMarshaler>
    {
        public TestClassSkillWithMarshaler()
            : base(argumentMarshaler: StringParsingMarshaler)
        {
        }

        public override AgentSkillFrontmatter Frontmatter { get; } = new("test-class-skill", "A test class skill.");

        protected override string Instructions => "Test instructions.";

        [AgentSkillScript("greet")]
        public static string Greet(string name) => $"Hello, {name}!";
    }

    /// <summary>
    /// A class-based skill that defines its scripts programmatically via <c>CreateScript</c>,
    /// passing the constructor-supplied argument marshaler through to each script.
    /// </summary>
    private sealed class TestClassSkillWithCreateScript : AgentClassSkill<TestClassSkillWithCreateScript>
    {
        public TestClassSkillWithCreateScript()
            : base(argumentMarshaler: StringParsingMarshaler)
        {
        }

        public override AgentSkillFrontmatter Frontmatter { get; } = new("create-script-skill", "A test class skill using CreateScript.");

        protected override string Instructions => "Test instructions.";

        public override IReadOnlyList<AgentSkillScript>? Scripts =>
            [this.CreateScript("echo", (string value) => $"echo: {value}")];
    }

    /// <summary>
    /// A class-based skill without a custom argument marshaler (uses default object marshaling).
    /// </summary>
    private sealed class TestClassSkillWithoutMarshaler : AgentClassSkill<TestClassSkillWithoutMarshaler>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("default-marshaler-skill", "A test class skill without a marshaler.");

        protected override string Instructions => "Test instructions.";

        [AgentSkillScript("greet")]
        public static string Greet(string name) => $"Hello, {name}!";
    }
}
