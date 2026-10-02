// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

public sealed class JevToolCallCompilerTests
{
    private static readonly Dictionary<string, List<Dictionary<string, JsonElement>>> s_noCalls = [];

    [Fact]
    public void Compile_ReferencesAndAnyOfNull_ResolveAndDecode()
    {
        // Arrange: a $defs reference, and an optional anyOf of an enum and null, as Pydantic writes them.
        AIFunctionDeclaration tool = Declaration("set_mode", """
            {
              "type": "object",
              "properties": {
                "mode": { "$ref": "#/$defs/Mode", "description": "The mode" },
                "level": { "anyOf": [{ "enum": ["low", "high"] }, { "type": "null" }], "default": null },
                "kind": { "const": "fixed" }
              },
              "required": ["mode", "kind"],
              "$defs": { "Mode": { "type": "string", "enum": ["fast", "safe"] } }
            }
            """);

        // Act
        JevToolCallPlan plan = Compile([tool])!;
        JevToolCall? call = plan.Decode(Result(
            JevChatTestData.RouteTo("t0", "t0", "none"),
            JevChatTestData.Choice("__af_tool__.t0.a0.value", "v1", "v0", "v1"),
            JevChatTestData.Noul("__af_tool__.t0.a1.present", 0.9),
            JevChatTestData.Choice("__af_tool__.t0.a1.value", "v0", "v0", "v1")));

        // Assert
        Assert.Contains("The mode", plan.Questions["__af_tool__.t0.a0.value"].Instructions!.Value.Text, StringComparison.Ordinal);
        Assert.Equal(["route", "t0.a0.value", "t0.a1.present", "t0.a1.value"], plan.Questions.Keys.Select(key => key["__af_tool__.".Length..]));
        Assert.Equal("safe", ((JsonElement)call!.Value.Arguments["mode"]!).GetString());
        Assert.Equal("low", ((JsonElement)call.Value.Arguments["level"]!).GetString());
        Assert.Equal("fixed", ((JsonElement)call.Value.Arguments["kind"]!).GetString());
    }

    [Fact]
    public void Compile_ChainedReferences_ResolveAndDecode()
    {
        // Arrange: Speed aliases Mode, and the nullable Level aliases a nullable enum, so each reference leads to another.
        AIFunctionDeclaration tool = Declaration("set_speed", """
            {
              "type": "object",
              "properties": {
                "speed": { "$ref": "#/$defs/Speed", "description": "How fast to go" },
                "level": { "$ref": "#/$defs/Level" }
              },
              "required": ["speed"],
              "$defs": {
                "Speed": { "$ref": "#/$defs/Mode" },
                "Mode": { "type": "string", "enum": ["fast", "safe"] },
                "Level": { "$ref": "#/$defs/NullableLevel" },
                "NullableLevel": { "anyOf": [{ "type": "string", "enum": ["low", "high"] }, { "type": "null" }] }
              }
            }
            """);

        // Act
        JevToolCallPlan plan = Compile([tool])!;
        JevToolCall? call = plan.Decode(Result(
            JevChatTestData.RouteTo("t0", "t0", "none"),
            JevChatTestData.Choice("__af_tool__.t0.a0.value", "v1", "v0", "v1"),
            JevChatTestData.Noul("__af_tool__.t0.a1.present", 0.9),
            JevChatTestData.Choice("__af_tool__.t0.a1.value", "v1", "v0", "v1")));

        // Assert: the description next to the first reference wins, and the nullable alias still gets a presence question.
        Assert.Contains("How fast to go", plan.Questions["__af_tool__.t0.a0.value"].Instructions!.Value.Text, StringComparison.Ordinal);
        Assert.Equal("safe", ((JsonElement)call!.Value.Arguments["speed"]!).GetString());
        Assert.Equal("high", ((JsonElement)call.Value.Arguments["level"]!).GetString());
    }

    [Fact]
    public void Compile_IntegersOutsideTheInt64Range_Compile()
    {
        // Arrange: an unsigned 64-bit contract, whose largest values do not fit in a long.
        AIFunctionDeclaration tool = Declaration("set_mask", """
            {
              "type": "object",
              "properties": {
                "mask": { "type": "integer", "enum": [0, 18446744073709551615] },
                "all": { "type": "integer", "const": 18446744073709551615 },
                "bits": { "type": "array", "items": { "type": "integer", "enum": [1, 9223372036854775808] } }
              },
              "required": ["mask", "all", "bits"]
            }
            """);

        // Act
        JevToolCallPlan plan = Compile([tool])!;
        JevToolCall? call = plan.Decode(Result(
            JevChatTestData.RouteTo("t0", "t0", "none"),
            JevChatTestData.Choice("__af_tool__.t0.a0.value", "v1", "v0", "v1"),
            JevChatTestData.Noul("__af_tool__.t0.a2.m0", 0.1),
            JevChatTestData.Noul("__af_tool__.t0.a2.m1", 0.9)));

        // Assert: the values reach the function unchanged.
        Assert.Equal(ulong.MaxValue, ((JsonElement)call!.Value.Arguments["mask"]!).GetUInt64());
        Assert.Equal(ulong.MaxValue, ((JsonElement)call.Value.Arguments["all"]!).GetUInt64());
        Assert.Equal([9223372036854775808UL], ((JsonElement)call.Value.Arguments["bits"]!).EnumerateArray().Select(item => item.GetUInt64()));
    }

    [Fact]
    public void Compile_EnumAndConstValuesMatchingTheirType_Compile()
    {
        // Arrange: numbers, mixed types, and a nullable enum whose null was removed before the check.
        AIFunctionDeclaration tool = Declaration("tune", """
            {
              "type": "object",
              "properties": {
                "ratio": { "type": "number", "enum": [1, 2.5] },
                "mode": { "type": ["string", "integer"], "enum": ["auto", 3] },
                "unit": { "type": ["string", "null"], "enum": ["c", "f", null] },
                "version": { "type": "integer", "const": 2 }
              },
              "required": ["ratio", "mode", "version"]
            }
            """);

        // Act
        JevToolCallPlan? plan = Compile([tool]);

        // Assert
        Assert.NotNull(plan);
        Assert.Single(plan.Tools);
    }

    [Theory]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "boolean" } }, "minProperties": 1 }""", "unsupported root-level schema constraints: minProperties")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "string", "enum": ["x", "y"], "minLength": 1 } }, "required": ["a"] }""", "required argument 'a': unsupported argument schema constraints: minLength")]
    [InlineData("""{ "type": "object", "properties": { "a": { "$ref": "#/$defs/A", "enum": ["x"] } }, "$defs": { "A": { "type": "boolean" } } }""", "optional argument 'a': $ref sibling constraints are not supported: enum")]
    [InlineData("""{ "type": "object", "properties": { "a": { "anyOf": [{ "type": "boolean" }, { "type": "string", "enum": ["x"] }] } } }""", "only a single schema combined with null is supported")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": ["boolean", "null"] } }, "required": ["a"] }""", "required nullable arguments are not supported")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "array", "items": { "type": "string", "enum": ["x"], "maxLength": 3 } } } }""", "unsupported array item schema constraints: maxLength")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "array", "items": { "type": "integer", "enum": [1, 2.5] } } } }""", "array enum member 2.5 does not match declared item type \"integer\"")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "array", "items": { "type": ["string", "null"], "enum": ["x", null] } } } }""", "nullable array members are not supported")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "integer" } } }""", "only const, enum, boolean, and arrays of enum values are supported")]
    [InlineData("""{ "type": "object", "properties": { "a": { "$ref": "#/$defs/A" } }, "$defs": { "A": { "$ref": "#/$defs/B" }, "B": { "$ref": "#/$defs/A" } } }""", "schema references are nested too deeply")]
    [InlineData("""{ "type": "object", "properties": { "a": { "$ref": "#/$defs/A" } }, "$defs": { "A": { "$ref": "#/$defs/Missing" } } }""", "unresolved schema reference '#/$defs/Missing'")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "integer", "enum": ["fast", "safe"] } } }""", "enum value \"fast\" does not match declared type \"integer\"")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "integer", "enum": ["fast"] } } }""", "enum value \"fast\" does not match declared type \"integer\"")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": ["integer", "boolean"], "enum": [1, "x"] } } }""", "enum value \"x\" does not match declared type [\"integer\", \"boolean\"]")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "string", "const": 5 } }, "required": ["a"] }""", "required argument 'a': const value 5 does not match declared type \"string\"")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "integer", "enum": [1, 2.0] } } }""", "enum value 2.0 does not match declared type \"integer\"")]
    [InlineData("""{ "type": "object", "properties": { "a": { "type": "integer", "const": 1e2 } }, "required": ["a"] }""", "const value 1e2 does not match declared type \"integer\"")]
    [InlineData("""{ "type": "object", "properties": {}, "required": ["missing"] }""", "required arguments are missing from properties: missing")]
    [InlineData("""{ "type": "array" }""", "the top-level input schema must be an object")]
    public void Compile_UnsupportedSchema_ExcludesTheToolWithTheReason(string schema, string reason)
    {
        // Arrange
        var logger = new ListLoggerFactory();

        // Act
        JevToolCallPlan? plan = Compile([Declaration("tool", schema)], logger: logger.CreateLogger("test"));

        // Assert
        Assert.Null(plan);
        Assert.Contains(reason, Assert.Single(logger.Entries).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Compile_SingleValueEnumAndNoArguments_NeedNoArgumentQuestions()
    {
        // Arrange
        AIFunctionDeclaration refresh = Declaration("refresh", """{ "type": "object", "properties": {} }""");
        AIFunctionDeclaration single = Declaration("single", """{ "type": "object", "properties": { "scope": { "enum": ["all"] } }, "required": ["scope"] }""");

        // Act
        JevToolCallPlan plan = Compile([refresh, single])!;
        JevToolCall? call = plan.Decode(Result(JevChatTestData.RouteTo("t1", "t0", "t1", "none")));

        // Assert
        Assert.Equal([JevChatTestData.Route], plan.Questions.Keys);
        Assert.Equal("single", call!.Value.Function.Name);
        Assert.Equal("all", ((JsonElement)call.Value.Arguments["scope"]!).GetString());
    }

    [Fact]
    public void Compile_TooManyTools_Throws()
    {
        // Arrange
        List<AIFunctionDeclaration> tools = [.. Enumerable.Range(0, JevToolCallCompiler.MaxRoutableTools + 1).Select(index => Declaration($"tool{index}", """{ "type": "object", "properties": {} }"""))];

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => Compile(tools));
    }

    [Fact]
    public void Compile_RequiredToolFilter_AppliesBeforeTheToolLimit()
    {
        // Arrange
        List<AIFunctionDeclaration> tools = [.. Enumerable.Range(0, JevToolCallCompiler.MaxRoutableTools + 1).Select(index => Declaration($"tool{index}", """{ "type": "object", "properties": {} }"""))];

        // Act
        JevToolCallPlan plan = Compile(tools, ChatToolMode.RequireSpecific("tool3"))!;

        // Assert
        Assert.Equal("tool3", plan.RequiredTool!.Function.Name);
        Assert.Null(plan.RouteQuestionId);
    }

    [Fact]
    public void Compile_TooManyInternalQuestions_Throws()
    {
        // Arrange: each tool needs 40 member questions, so the fourth exceeds 128.
        string members = string.Join(",", Enumerable.Range(0, 40).Select(index => $"\"m{index}\""));
        List<AIFunctionDeclaration> tools = [.. Enumerable.Range(0, 4).Select(index => Declaration($"tool{index}", $$"""{ "type": "object", "properties": { "tags": { "type": "array", "items": { "enum": [{{members}}] } } }, "required": ["tags"] }"""))];

        // Act & Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() => Compile(tools));
        Assert.Contains("128", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Compile_UnsupportedTool_ReturnsItsQuestionBudget()
    {
        // Arrange: the first tool fails only after its array reserved 64 questions; they must be released.
        string members = string.Join(",", Enumerable.Range(0, 64).Select(index => $"\"m{index}\""));
        AIFunctionDeclaration failing = Declaration("failing", $$"""{ "type": "object", "properties": { "tags": { "type": "array", "items": { "enum": [{{members}}] } }, "text": { "type": "string" } }, "required": ["tags"] }""");
        AIFunctionDeclaration large = Declaration("large", $$"""{ "type": "object", "properties": { "a": { "type": "array", "items": { "enum": [{{members}}] } }, "b": { "type": "array", "items": { "enum": [{{string.Join(",", Enumerable.Range(0, 60).Select(index => $"\"n{index}\""))}}] } } }, "required": ["a", "b"] }""");

        // Act
        JevToolCallPlan plan = Compile([failing, large])!;

        // Assert
        Assert.Equal(125, plan.Questions.Count);
    }

    [Fact]
    public void Compile_TooManyEnumValuesOrProperties_ExcludeTheTool()
    {
        // Arrange
        string values = string.Join(",", Enumerable.Range(0, JevToolCallCompiler.MaxEnumValues + 1).Select(index => $"\"v{index}\""));
        string properties = string.Join(",", Enumerable.Range(0, JevToolCallCompiler.MaxToolProperties + 1).Select(index => $"\"p{index}\": {{ \"type\": \"boolean\" }}"));

        // Act
        JevToolCallPlan? plan = Compile(
        [
            Declaration("enum", $$"""{ "type": "object", "properties": { "a": { "enum": [{{values}}] } } }"""),
            Declaration("wide", $$"""{ "type": "object", "properties": { {{properties}} } }"""),
        ]);

        // Assert
        Assert.Null(plan);
    }

    [Fact]
    public void Decode_UnknownRouteOrMissingAnswer_Throws()
    {
        // Arrange
        JevToolCallPlan plan = Compile([Declaration("flag", """{ "type": "object", "properties": { "on": { "type": "boolean" } }, "required": ["on"] }""")])!;

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => plan.Decode(Result(JevChatTestData.RouteTo("t9", "t9"))));
        Assert.Throws<InvalidOperationException>(() => plan.Decode(Result(JevChatTestData.RouteTo("t0", "t0"))));
    }

    [Fact]
    public void Compile_DuplicateDescriptions_KeepToolNamesInTheRoute()
    {
        // Arrange
        AIFunctionDeclaration first = Declaration("first", """{ "type": "object", "properties": {} }""", "Does it.");
        AIFunctionDeclaration second = Declaration("second", """{ "type": "object", "properties": {} }""", "Does it.");

        // Act
        JevChoiceQuestion route = Assert.IsType<JevChoiceQuestion>(Compile([first, second])!.Questions[JevChatTestData.Route]);

        // Assert
        Assert.Equal("Tool 'first': Does it.", route.Criteria["t0"].Text);
        Assert.Equal("Tool 'second': Does it.", route.Criteria["t1"].Text);
    }

    [Fact]
    public void Describe_MatchesPythonJsonDumps()
    {
        // Arrange: json.dumps(value, ensure_ascii=False, sort_keys=True) in the Python connector.
        JsonElement value = JsonDocument.Parse("""{"city":"São Paulo","b":[1,2.5,true,null],"q":"say \"hi\"\n"}""").RootElement;

        // Act
        string described = JevToolSchema.Describe(value);

        // Assert
        Assert.Equal("""{"b": [1, 2.5, true, null], "city": "São Paulo", "q": "say \"hi\"\n"}""", described);
    }

    private static AIFunctionDeclaration Declaration(string name, string schema, string? description = null) =>
        AIFunctionFactory.CreateDeclaration(name, description, JsonDocument.Parse(schema).RootElement.Clone());

    private static JevToolCallPlan? Compile(IReadOnlyList<AIFunctionDeclaration> tools, ChatToolMode? mode = null, ILogger? logger = null) =>
        JevToolCallCompiler.Compile(tools, mode, s_noCalls, logger ?? new ListLoggerFactory().CreateLogger("test"));

    private static JevResult Result(params string[] answers) =>
        JsonSerializer.Deserialize(JevChatTestData.Result(answers), JevJsonContext.Default.JevResult)!;
}
