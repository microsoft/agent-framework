// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests JSON deserialization of <c>skills/list</c> results.
/// </summary>
public sealed class AgentMcpSkillsSerializationTests
{
    [Theory]
    [InlineData("null", null)]
    [InlineData("0", 0L)]
    [InlineData("300000", 300000L)]
    [InlineData("-1", -1L)]
    public void Deserialize_TimeToLive_PreservesMilliseconds(string ttl, long? expectedMilliseconds)
    {
        // Arrange
        JsonObject node = new()
        {
            ["resultType"] = "complete",
            ["skills"] = new JsonArray(),
            ["ttlMs"] = JsonNode.Parse(ttl),
        };

        // Act
        var result = node.Deserialize(McpSkillsJsonContext.Default.McpSkillsListResult);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(expectedMilliseconds is { } ms ? TimeSpan.FromMilliseconds(ms) : null, result.TimeToLive);
    }

    [Fact]
    public void Deserialize_MissingTimeToLive_PreservesAbsence()
    {
        // Arrange
        const string Json = """{"resultType":"complete","skills":[]}""";

        // Act
        var result = JsonSerializer.Deserialize(Json, McpSkillsJsonContext.Default.McpSkillsListResult);

        // Assert
        Assert.NotNull(result);
        Assert.Null(result.TimeToLive);
    }

    [Theory]
    [InlineData("\"1000\"")]
    [InlineData("true")]
    [InlineData("{}")]
    [InlineData("[]")]
    public void Deserialize_InvalidTimeToLive_Throws(string ttl)
    {
        // Arrange
        JsonObject node = new()
        {
            ["resultType"] = "complete",
            ["skills"] = new JsonArray(),
            ["ttlMs"] = JsonNode.Parse(ttl),
        };

        // Act & Assert
        Assert.Throws<JsonException>(() => node.Deserialize(McpSkillsJsonContext.Default.McpSkillsListResult));
    }

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
    [InlineData("""{"resultType":"complete","skills":[],"nextCursor":42}""")]
    [InlineData("""{"resultType":"complete","skills":[],"nextCursor":true}""")]
    [InlineData("""{"resultType":"complete","skills":[],"nextCursor":[]}""")]
    [InlineData("""{"resultType":"complete","skills":[],"nextCursor":{}}""")]
    public void Deserialize_InvalidResult_Throws(string json)
    {
        // Arrange
        var context = McpSkillsJsonContext.Default;

        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(json, context.McpSkillsListResult));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("opaque cursor:+/=\u00e9")]
    public void Deserialize_NextCursor_PreservesValue(string? cursor)
    {
        // Arrange
        JsonObject node = new()
        {
            ["resultType"] = "complete",
            ["skills"] = new JsonArray(),
            ["nextCursor"] = cursor,
        };

        // Act
        var result = node.Deserialize(McpSkillsJsonContext.Default.McpSkillsListResult);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(cursor, result.NextCursor);
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
        Assert.Throws<JsonException>(() => entry.Deserialize(McpSkillsJsonContext.Default.McpSkillEntry));
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
        JsonException exception = Assert.Throws<JsonException>(() => entry.Deserialize(McpSkillsJsonContext.Default.McpSkillEntry));
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
        var context = McpSkillsJsonContext.Default;

        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(json, context.McpSkillFrontmatter));
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
        var context = McpSkillsJsonContext.Default;

        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(json, context.McpSkillResourceEntry));
    }

    [Fact]
    public void Deserialize_Resource_ReturnsResource()
    {
        // Arrange
        const string Json = """{"uri":"skill://unit-converter/file.txt","digest":"sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","size":0}""";
        var context = McpSkillsJsonContext.Default;

        // Act
        McpSkillResourceEntry? resource = JsonSerializer.Deserialize(Json, context.McpSkillResourceEntry);

        // Assert
        Assert.NotNull(resource);
        Assert.Equal("skill://unit-converter/file.txt", resource.Uri);
        Assert.Equal("sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", resource.Digest);
        Assert.Equal(0, resource.Size);
    }

    [Theory]
    [InlineData("[]")]
    [InlineData("""[{"uri":"skill://unit-converter/SKILL.md","digest":"sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","size":0}]""")]
    public void Deserialize_Skill_UsesTypedFrontmatterAndResources(string resources)
    {
        // Arrange
        JsonObject entry = CreateEntry();
        entry["resources"] = JsonNode.Parse(resources);

        // Act
        McpSkillEntry? deserialized = entry.Deserialize(McpSkillsJsonContext.Default.McpSkillEntry);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("unit-converter", deserialized.Frontmatter.Name);
        Assert.Equal("Convert units.", deserialized.Frontmatter.Description);
        JsonArray expected = Assert.IsType<JsonArray>(entry["resources"]);
        Assert.Equal(expected.Count, deserialized.Resources.Count);
        if (expected.Count > 0)
        {
            McpSkillResourceEntry resource = Assert.IsType<McpSkillResourceEntry>(Assert.Single(deserialized.Resources));
            Assert.Equal("skill://unit-converter/SKILL.md", resource.Uri);
        }
    }

    [Fact]
    public void Deserialize_CaseVariants_IgnoresUnknownCaseVariants()
    {
        // Arrange
        const string Json = """{"resultType":"complete","ResultType":"unknown","skills":[],"Skills":null}""";

        // Act
        McpSkillsListResult? result = JsonSerializer.Deserialize(Json, McpSkillsJsonContext.Default.McpSkillsListResult);

        // Assert
        Assert.NotNull(result);
        Assert.Equal("complete", result.ResultType);
        Assert.Empty(result.Skills);
        Assert.Null(result.NextCursor);
    }

    [Theory]
    [InlineData("digest", "null")]
    [InlineData("digest", "42")]
    [InlineData("digest", "true")]
    [InlineData("digest", "[]")]
    [InlineData("size", "null")]
    [InlineData("size", "\"12\"")]
    [InlineData("size", "false")]
    [InlineData("size", "[]")]
    [InlineData("size", "1.5")]
    [InlineData("size", "9223372036854775808")]
    public void Deserialize_InvalidIntegrityField_Throws(string field, string value)
    {
        // Arrange
        JsonObject resource = CreateResource();
        resource[field] = JsonNode.Parse(value);

        // Act & Assert
        Assert.Throws<JsonException>(() => resource.Deserialize(McpSkillsJsonContext.Default.McpSkillResourceEntry));
    }

    [Theory]
    [InlineData("uri")]
    [InlineData("digest")]
    [InlineData("size")]
    public void Deserialize_MissingResourceField_Throws(string field)
    {
        // Arrange
        JsonObject resource = CreateResource();
        resource.Remove(field);

        // Act & Assert
        JsonException exception = Assert.Throws<JsonException>(() => resource.Deserialize(McpSkillsJsonContext.Default.McpSkillResourceEntry));
        Assert.Contains(field, exception.Message);
    }

    [Fact]
    public void Deserialize_LargeSize_PreservesInt64()
    {
        // Arrange
        JsonObject resource = CreateResource();
        resource["size"] = long.MaxValue;

        // Act
        var deserialized = resource.Deserialize(McpSkillsJsonContext.Default.McpSkillResourceEntry);

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(long.MaxValue, deserialized.Size);
    }

    private static JsonObject CreateResource() => new()
    {
        ["uri"] = "skill://unit-converter/SKILL.md",
        ["digest"] = "sha256:" + new string('a', 64),
        ["size"] = 0,
    };

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
