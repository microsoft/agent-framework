// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentInlineSkillScript"/>.
/// </summary>
public sealed class AgentInlineSkillScriptTests
{
    [Fact]
    public async Task RunAsync_InvokesDelegate_ReturnsResultAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript("greet", () => "hello");
        var skill = new AgentInlineSkill("test-skill", "Test.", "Instructions.");

        // Act
        var result = await script.RunAsync(skill, new AIFunctionArguments(), CancellationToken.None);

        // Assert
        Assert.Equal("hello", result?.ToString());
    }

    [Fact]
    public async Task RunAsync_WithParameters_PassesArgumentsAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript("add", (int a, int b) => a + b);
        var skill = new AgentInlineSkill("calc-skill", "Calc.", "Instructions.");
        var args = new AIFunctionArguments { ["a"] = 3, ["b"] = 7 };

        // Act
        var result = await script.RunAsync(skill, args, CancellationToken.None);

        // Assert
        Assert.Equal(10, int.Parse(result?.ToString()!));
    }

    [Fact]
    public void ParametersSchema_NoParameters_ReturnsSchema()
    {
        // Arrange
        var script = new AgentInlineSkillScript("noop", () => "ok");

        // Act
        var schema = script.ParametersSchema;

        // Assert — parameterless delegates still produce a schema
        Assert.NotNull(schema);
    }

    [Fact]
    public void ParametersSchema_WithParameters_ContainsPropertyNames()
    {
        // Arrange
        var script = new AgentInlineSkillScript("search", (string query, int limit) => $"{query}:{limit}");

        // Act
        var schema = script.ParametersSchema;

        // Assert
        Assert.NotNull(schema);
        var schemaText = schema!.Value.GetRawText();
        Assert.Contains("query", schemaText);
        Assert.Contains("limit", schemaText);
    }

    [Fact]
    public void Constructor_SetsNameAndDescription()
    {
        // Arrange & Act
        var script = new AgentInlineSkillScript("my-script", () => "ok", "Does something.");

        // Assert
        Assert.Equal("my-script", script.Name);
        Assert.Equal("Does something.", script.Description);
    }

    [Fact]
    public void Constructor_NullDescription_DescriptionIsNull()
    {
        // Arrange & Act
        var script = new AgentInlineSkillScript("my-script", () => "ok");

        // Assert
        Assert.Null(script.Description);
    }

    [Fact]
    public void Constructor_NullName_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new AgentInlineSkillScript(null!, () => "ok"));
    }

    [Fact]
    public void Constructor_WhitespaceName_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() =>
            new AgentInlineSkillScript("  ", () => "ok"));
    }

    [Fact]
    public void Constructor_NullMethod_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new AgentInlineSkillScript("my-script", null!));
    }

    [Fact]
    public async Task RunAsync_WithSerializerOptions_MarshalsCustomTypesAsync()
    {
        // Arrange — script accepts a custom type; the JSO includes a source-generated context for it
        var jso = SkillTestJsonContext.Default.Options;
        var script = new AgentInlineSkillScript("lookup", (LookupRequest request) => new LookupResponse
        {
            Items = ["result-1", "result-2"],
            TotalCount = request.MaxResults,
        }, serializerOptions: jso);
        var skill = new AgentInlineSkill("test-skill", "Test.", "Instructions.");
        var inputJson = JsonSerializer.SerializeToElement(new LookupRequest { Query = "test", MaxResults = 5 }, jso);
        var args = new AIFunctionArguments { ["request"] = inputJson };

        // Act
        var result = await script.RunAsync(skill, args, CancellationToken.None);

        // Assert — the custom input type was deserialized and the response was produced
        Assert.NotNull(result);
        Assert.Contains("5", result!.ToString()!);
    }

    [Fact]
    public async Task RunAsync_StringParameter_WorksAsync()
    {
        // Arrange
        var script = new AgentInlineSkillScript("echo", (string message) => message);
        var skill = new AgentInlineSkill("test-skill", "Test.", "Instructions.");
        var args = new AIFunctionArguments { ["message"] = "hello world" };

        // Act
        var result = await script.RunAsync(skill, args, CancellationToken.None);

        // Assert
        Assert.Equal("hello world", result?.ToString());
    }

    [Fact]
    public void Constructor_MethodInfo_SetsNameAndDescription()
    {
        // Arrange
        var method = typeof(AgentInlineSkillScriptTests).GetMethod(nameof(StaticScriptHelper), BindingFlags.NonPublic | BindingFlags.Static)!;

        // Act
        var script = new AgentInlineSkillScript("method-script", method, target: null, description: "A method script.");

        // Assert
        Assert.Equal("method-script", script.Name);
        Assert.Equal("A method script.", script.Description);
    }

    [Fact]
    public async Task RunAsync_MethodInfo_StaticMethod_InvokesAndReturnsAsync()
    {
        // Arrange
        var method = typeof(AgentInlineSkillScriptTests).GetMethod(nameof(StaticScriptHelper), BindingFlags.NonPublic | BindingFlags.Static)!;
        var script = new AgentInlineSkillScript("static-method-script", method, target: null);
        var skill = new AgentInlineSkill("test-skill", "Test.", "Instructions.");
        var args = new AIFunctionArguments { ["input"] = "hello" };

        // Act
        var result = await script.RunAsync(skill, args, CancellationToken.None);

        // Assert
        Assert.Equal("HELLO", result?.ToString());
    }

    [Fact]
    public async Task RunAsync_MethodInfo_InstanceMethod_InvokesAndReturnsAsync()
    {
        // Arrange
        var method = typeof(AgentInlineSkillScriptTests).GetMethod(nameof(InstanceScriptHelper), BindingFlags.NonPublic | BindingFlags.Instance)!;
        var script = new AgentInlineSkillScript("instance-method-script", method, target: this);
        var skill = new AgentInlineSkill("test-skill", "Test.", "Instructions.");
        var args = new AIFunctionArguments { ["input"] = "test" };

        // Act
        var result = await script.RunAsync(skill, args, CancellationToken.None);

        // Assert
        Assert.Equal("test-suffix", result?.ToString());
    }

    [Fact]
    public void Constructor_MethodInfo_NullMethod_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new AgentInlineSkillScript("my-script", null!, target: null));
    }

    [Fact]
    public void ParametersSchema_MethodInfo_ContainsParameterNames()
    {
        // Arrange
        var method = typeof(AgentInlineSkillScriptTests).GetMethod(nameof(StaticScriptHelper), BindingFlags.NonPublic | BindingFlags.Static)!;
        var script = new AgentInlineSkillScript("param-script", method, target: null);

        // Act
        var schema = script.ParametersSchema;

        // Assert
        Assert.NotNull(schema);
        Assert.Contains("input", schema!.Value.GetRawText());
    }

    private static string StaticScriptHelper(string input) => input.ToUpperInvariant();

    private string InstanceScriptHelper(string input) => input + "-suffix";
}
