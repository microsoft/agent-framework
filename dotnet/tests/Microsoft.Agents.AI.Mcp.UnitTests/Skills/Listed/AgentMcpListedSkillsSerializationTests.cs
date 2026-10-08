// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests JSON deserialization of <c>skills/list</c> results.
/// </summary>
public sealed class AgentMcpListedSkillsSerializationTests
{
    [Theory]
    [InlineData("[]")]
    [InlineData("true")]
    [InlineData("42")]
    [InlineData("\"result\"")]
    [InlineData("{}")]
    [InlineData("""{"resultType":"complete"}""")]
    [InlineData("""{"skills":[]}""")]
    [InlineData("""{"resultType":"complete","skills":null}""")]
    [InlineData("""{"resultType":"complete","skills":{}}""")]
    [InlineData("""{"resultType":"complete","skills":"[]"}""")]
    [InlineData("""{"resultType":"complete","skills":[42]}""")]
    [InlineData("""{"resultType":"complete","skills":[[]]}""")]
    [InlineData("""{"resultType":null,"skills":[]}""")]
    [InlineData("""{"resultType":42,"skills":[]}""")]
    [InlineData("""{"resultType":true,"skills":[]}""")]
    [InlineData("""{"resultType":[],"skills":[]}""")]
    [InlineData("""{"ResultType":"complete","skills":[]}""")]
    [InlineData("""{"resultType":"complete","Skills":[]}""")]
    public void Deserialize_InvalidResult_Throws(string json)
    {
        // Arrange
        var context = McpListedSkillsJsonContext.Default;

        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(json, context.McpSkillsListResult));
    }

    [Theory]
    [InlineData("uri", "null")]
    [InlineData("uri", "42")]
    [InlineData("uri", "true")]
    [InlineData("frontmatter", "null")]
    [InlineData("frontmatter", "[]")]
    [InlineData("frontmatter", "\"metadata\"")]
    [InlineData("resources", "null")]
    [InlineData("resources", "{}")]
    [InlineData("resources", "false")]
    [InlineData("resources", "\"dynamic\"")]
    [InlineData("resources", "[42]")]
    [InlineData("resources", "[[]]")]
    [InlineData("resources", "[{}]")]
    public void Deserialize_InvalidSkillField_Throws(string field, string value)
    {
        // Arrange
        JsonObject entry = CreateEntry();
        entry[field] = JsonNode.Parse(value);

        // Act & Assert
        Assert.Throws<JsonException>(() => entry.Deserialize(McpListedSkillsJsonContext.Default.McpListedSkillEntry));
    }

    [Theory]
    [InlineData("uri")]
    [InlineData("frontmatter")]
    [InlineData("resources")]
    public void Deserialize_MissingSkillField_Throws(string field)
    {
        // Arrange
        JsonObject entry = CreateEntry();
        entry.Remove(field);

        // Act & Assert
        JsonException exception = Assert.Throws<JsonException>(() => entry.Deserialize(McpListedSkillsJsonContext.Default.McpListedSkillEntry));
        Assert.Contains(field, exception.Message);
    }

    [Theory]
    [InlineData("[]")]
    [InlineData("\"metadata\"")]
    [InlineData("42")]
    [InlineData("{}")]
    [InlineData("""{"name":"unit-converter"}""")]
    [InlineData("""{"description":"Convert units."}""")]
    [InlineData("""{"name":null,"description":"Convert units."}""")]
    [InlineData("""{"name":42,"description":"Convert units."}""")]
    [InlineData("""{"name":"unit-converter","description":null}""")]
    [InlineData("""{"name":"unit-converter","description":false}""")]
    public void Deserialize_InvalidFrontmatter_Throws(string json)
    {
        // Arrange
        var context = McpListedSkillsJsonContext.Default;

        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(json, context.McpListedSkillFrontmatter));
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("""{"uri":null}""")]
    [InlineData("""{"uri":42}""")]
    [InlineData("""{"uri":true}""")]
    [InlineData("""{"uri":[]}""")]
    [InlineData("""{"uri":{}}""")]
    public void Deserialize_InvalidResource_Throws(string json)
    {
        // Arrange
        var context = McpListedSkillsJsonContext.Default;

        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(json, context.McpListedSkillResourceEntry));
    }

    [Fact]
    public void Deserialize_Resource_ReturnsResource()
    {
        // Arrange
        const string Json = """{"uri":"skill://unit-converter/file.txt"}""";
        var context = McpListedSkillsJsonContext.Default;

        // Act
        McpListedSkillResourceEntry? resource = JsonSerializer.Deserialize(Json, context.McpListedSkillResourceEntry);

        // Assert
        Assert.NotNull(resource);
        Assert.Equal("skill://unit-converter/file.txt", resource.Uri);
    }

    [Theory]
    [InlineData("[]")]
    [InlineData("""[{"uri":"skill://unit-converter/SKILL.md"}]""")]
    public void Deserialize_Skill_UsesTypedFrontmatterAndResources(string resources)
    {
        // Arrange
        JsonObject entry = CreateEntry();
        entry["resources"] = JsonNode.Parse(resources);

        // Act
        McpListedSkillEntry? deserialized = entry.Deserialize(McpListedSkillsJsonContext.Default.McpListedSkillEntry);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("unit-converter", deserialized.Frontmatter.Name);
        Assert.Equal("Convert units.", deserialized.Frontmatter.Description);
        JsonArray expected = Assert.IsType<JsonArray>(entry["resources"]);
        Assert.Equal(expected.Count, deserialized.Resources.Count);
        if (expected.Count > 0)
        {
            McpListedSkillResourceEntry resource = Assert.IsType<McpListedSkillResourceEntry>(Assert.Single(deserialized.Resources));
            Assert.Equal("skill://unit-converter/SKILL.md", resource.Uri);
        }
    }

    [Fact]
    public void Deserialize_CaseVariants_IgnoresUnknownCaseVariants()
    {
        // Arrange
        const string Json = """{"resultType":"complete","ResultType":"unknown","skills":[],"Skills":null}""";

        // Act
        McpSkillsListResult? result = JsonSerializer.Deserialize(Json, McpListedSkillsJsonContext.Default.McpSkillsListResult);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("complete", result.ResultType);
        Assert.Empty(result.Skills);
    }

    private static JsonObject CreateEntry() => new()
    {
        ["uri"] = "skill://unit-converter/SKILL.md",
        ["frontmatter"] = new JsonObject
        {
            ["name"] = "unit-converter",
            ["description"] = "Convert units.",
            ["future-field"] = new JsonObject { ["nested"] = 42 },
        },
        ["resources"] = new JsonArray(),
    };
}
