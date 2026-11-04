// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Nodes;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Tests JSON deserialization of <c>skills/list</c> and <c>skills/get</c> results.
/// </summary>
public sealed class AgentMcpSkillsSerializationTests
{
    [Theory]
    [InlineData(null, null)]
    [InlineData("null", null)]
    [InlineData("\"public\"", CacheScope.Public)]
    [InlineData("\"PUBLIC\"", CacheScope.Public)]
    [InlineData("\"private\"", CacheScope.Private)]
    [InlineData("\"PRIVATE\"", CacheScope.Private)]
    public void Deserialize_CacheScope_MatchesResourceSdkAndRoundTripsKnownScopes(string? json, CacheScope? expected)
    {
        // Arrange
        JsonObject listing = new()
        {
            ["resultType"] = "complete",
            ["skills"] = new JsonArray(),
        };
        JsonObject get = new()
        {
            ["resultType"] = "complete",
            ["skill"] = CreateEntry(),
        };
        if (json is not null)
        {
            listing["cacheScope"] = JsonNode.Parse(json);
            get["cacheScope"] = JsonNode.Parse(json);
        }

        // Act
        var listResult = listing.Deserialize(McpSkillsJsonContext.Default.McpSkillsListResult);
        var getResult = get.Deserialize(McpSkillsJsonContext.Default.McpSkillsGetResult);
        var resourceResult = listing.Deserialize<ReadResourceResult>();

        // Assert
        Assert.NotNull(listResult);
        Assert.NotNull(getResult);
        Assert.NotNull(resourceResult);
        Assert.Equal(expected, listResult.CacheScope);
        Assert.Equal(expected, getResult.CacheScope);
        Assert.Equal(expected, resourceResult.CacheScope);
        Assert.Equal(expected, JsonSerializer.SerializeToNode(listResult, McpSkillsJsonContext.Default.McpSkillsListResult)!
            .Deserialize(McpSkillsJsonContext.Default.McpSkillsListResult)!.CacheScope);
        Assert.Equal(expected, JsonSerializer.SerializeToNode(getResult, McpSkillsJsonContext.Default.McpSkillsGetResult)!
            .Deserialize(McpSkillsJsonContext.Default.McpSkillsGetResult)!.CacheScope);
    }

    [Theory]
    [InlineData("\"future\"")]
    [InlineData("\"\"")]
    [InlineData("42")]
    [InlineData("true")]
    [InlineData("{\"nested\":[1,2]}")]
    [InlineData("[{\"nested\":true}]")]
    public void Deserialize_InvalidCacheScope_Throws(string json)
    {
        // Arrange
        JsonObject listing = new()
        {
            ["resultType"] = "complete",
            ["skills"] = new JsonArray(),
            ["cacheScope"] = JsonNode.Parse(json),
        };
        JsonObject get = new()
        {
            ["resultType"] = "complete",
            ["skill"] = CreateEntry(),
            ["cacheScope"] = JsonNode.Parse(json),
        };

        // Act & Assert
        Assert.Throws<JsonException>(() => listing.Deserialize(McpSkillsJsonContext.Default.McpSkillsListResult));
        Assert.Throws<JsonException>(() => get.Deserialize(McpSkillsJsonContext.Default.McpSkillsGetResult));
    }

    [Theory]
    [InlineData("license", "\"MIT\"")]
    [InlineData("compatibility", "\"Any runtime\"")]
    [InlineData("allowed-tools", "\"read write\"")]
    [InlineData("metadata", """{"Owner":"Example","owner":"Other"}""")]
    [InlineData("future-field", """{"nested":[true,42,1.25,"123",null,{},[]]}""")]
    [InlineData("Name", "\"Unrecognized case variant\"")]
    [InlineData("originalJson", """{"server-field":true}""")]
    [InlineData("explicit-null", "null")]
    public void Deserialize_Frontmatter_PreservesOriginalJsonAfterDocumentDisposal(string field, string value)
    {
        // Arrange
        JsonObject entry = CreateEntry();
        entry["frontmatter"]![field] = JsonNode.Parse(value);
        using JsonDocument document = JsonDocument.Parse(entry.ToJsonString());

        // Act
        McpSkillEntry? deserialized = document.RootElement.Deserialize(McpSkillsJsonContext.Default.McpSkillEntry);
        document.Dispose();

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal("unit-converter", deserialized.Frontmatter.Name);
        Assert.Equal("Convert units.", deserialized.Frontmatter.Description);
        JsonElement snapshot = deserialized.Frontmatter.OriginalJson;
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(value), JsonNode.Parse(snapshot.GetProperty(field).GetRawText())));
        Assert.True(JsonNode.DeepEquals(entry["frontmatter"], JsonNode.Parse(snapshot.GetRawText())));

        JsonElement serialized = JsonSerializer.SerializeToElement(deserialized, McpSkillsJsonContext.Default.McpSkillEntry);
        Assert.True(JsonNode.DeepEquals(entry["frontmatter"], JsonNode.Parse(serialized.GetProperty("frontmatter").GetRawText())));
    }

    [Fact]
    public void Deserialize_Frontmatter_RetainsOriginalRepresentation()
    {
        // Arrange
        const string Json = """
            {
              "uri": "skill://unit-converter/SKILL.md",
              "frontmatter": {
                "future-field": 1.2300e+2,
                "description": "Convert \u0075nits.",
                "name": "unit-converter",
                "metadata": { "owner": "First", "owner": "Second" }
              },
              "resources": []
            }
            """;
        using JsonDocument document = JsonDocument.Parse(Json);
        string expected = document.RootElement.GetProperty("frontmatter").GetRawText();

        // Act
        McpSkillEntry? entry = JsonSerializer.Deserialize(Json, McpSkillsJsonContext.Default.McpSkillEntry);

        // Assert
        Assert.NotNull(entry);
        Assert.Equal("unit-converter", entry.Frontmatter.Name);
        Assert.Equal("Convert units.", entry.Frontmatter.Description);
        Assert.Equal(expected, entry.Frontmatter.OriginalJson.GetRawText());
    }

    [Theory]
    [InlineData(null, null)]
    [InlineData("null", "null")]
    [InlineData("\"MIT\"", """{"Owner":"Example","owner":"Other","count":42,"nested":[true,null,{}]}""")]
    public void Deserialize_Frontmatter_ReadsLicenseAndMetadata(string? license, string? metadata)
    {
        // Arrange
        JsonObject entry = CreateEntry();
        if (license is not null)
        {
            entry["frontmatter"]!["license"] = JsonNode.Parse(license);
        }

        if (metadata is not null)
        {
            entry["frontmatter"]!["metadata"] = JsonNode.Parse(metadata);
        }

        using JsonDocument document = JsonDocument.Parse(entry.ToJsonString());

        // Act
        McpSkillEntry? deserialized = document.RootElement.Deserialize(McpSkillsJsonContext.Default.McpSkillEntry);
        document.Dispose();

        // Assert
        Assert.NotNull(deserialized);
        Assert.Equal(license is null ? null : JsonSerializer.Deserialize<string>(license), deserialized.Frontmatter.License);
        if (metadata is null or "null")
        {
            Assert.Null(deserialized.Frontmatter.Metadata);
        }
        else
        {
            Assert.NotNull(deserialized.Frontmatter.Metadata);
            Assert.Equal(3, deserialized.Frontmatter.Metadata.Count);
            Assert.Equal("Other", Assert.IsType<JsonElement>(deserialized.Frontmatter.Metadata["Owner"]).GetString());
            Assert.Equal(42, Assert.IsType<JsonElement>(deserialized.Frontmatter.Metadata["count"]).GetInt32());
            Assert.True(Assert.IsType<JsonElement>(deserialized.Frontmatter.Metadata["nested"])[0].GetBoolean());
        }

        JsonElement serialized = JsonSerializer.SerializeToElement(deserialized, McpSkillsJsonContext.Default.McpSkillEntry);
        Assert.True(JsonNode.DeepEquals(entry["frontmatter"], JsonNode.Parse(serialized.GetProperty("frontmatter").GetRawText())));
    }

    [Theory]
    [InlineData("42")]
    [InlineData("true")]
    [InlineData("{}")]
    [InlineData("[]")]
    public void Deserialize_Frontmatter_InvalidLicenseType_Throws(string license)
    {
        // Arrange
        JsonObject entry = CreateEntry();
        entry["frontmatter"]!["license"] = JsonNode.Parse(license);

        // Act & Assert
        Assert.Throws<JsonException>(() => entry.Deserialize(McpSkillsJsonContext.Default.McpSkillEntry));
    }

    [Fact]
    public void Serialize_FrontmatterWithoutSnapshot_Throws()
    {
        // Arrange
        McpSkillEntry entry = new()
        {
            Uri = "skill://unit-converter/SKILL.md",
            Frontmatter = new McpSkillFrontmatter { Name = "unit-converter", Description = "Convert units." },
            Resources = [],
        };

        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(entry, McpSkillsJsonContext.Default.McpSkillEntry));
    }

    [Theory]
    [InlineData("null", null)]
    [InlineData("0", 0L)]
    [InlineData("300000", 300000L)]
    [InlineData("-1", -1L)]
    public void Deserialize_GetTimeToLive_PreservesMilliseconds(string ttl, long? expectedMilliseconds)
    {
        // Arrange
        JsonObject node = new()
        {
            ["resultType"] = "complete",
            ["skill"] = CreateEntry(),
            ["ttlMs"] = JsonNode.Parse(ttl),
        };

        // Act
        var result = node.Deserialize(McpSkillsJsonContext.Default.McpSkillsGetResult);

        // Assert
        Assert.NotNull(result);
        Assert.Equal(expectedMilliseconds is { } ms ? TimeSpan.FromMilliseconds(ms) : null, result.TimeToLive);
    }

    [Fact]
    public void Deserialize_GetMissingTimeToLive_PreservesAbsence()
    {
        // Arrange
        JsonObject node = new()
        {
            ["resultType"] = "complete",
            ["skill"] = CreateEntry(),
        };

        // Act
        var result = node.Deserialize(McpSkillsJsonContext.Default.McpSkillsGetResult);

        // Assert
        Assert.NotNull(result);
        Assert.Null(result.TimeToLive);
    }

    [Theory]
    [InlineData("\"1000\"")]
    [InlineData("true")]
    [InlineData("{}")]
    [InlineData("[]")]
    public void Deserialize_GetInvalidTimeToLive_Throws(string ttl)
    {
        // Arrange
        JsonObject node = new()
        {
            ["resultType"] = "complete",
            ["skill"] = CreateEntry(),
            ["ttlMs"] = JsonNode.Parse(ttl),
        };

        // Act & Assert
        Assert.Throws<JsonException>(() => node.Deserialize(McpSkillsJsonContext.Default.McpSkillsGetResult));
    }

    [Theory]
    [InlineData(long.MinValue)]
    [InlineData(long.MaxValue)]
    public void Deserialize_GetExtremeTimeToLive_MatchesListConversion(long ttl)
    {
        // Arrange
        JsonObject getNode = new()
        {
            ["resultType"] = "complete",
            ["skill"] = CreateEntry(),
            ["ttlMs"] = ttl,
        };
        JsonObject listNode = new()
        {
            ["resultType"] = "complete",
            ["skills"] = new JsonArray(),
            ["ttlMs"] = ttl,
        };

        // Act
        var getResult = getNode.Deserialize(McpSkillsJsonContext.Default.McpSkillsGetResult);
        var listResult = listNode.Deserialize(McpSkillsJsonContext.Default.McpSkillsListResult);

        // Assert
        Assert.NotNull(getResult);
        Assert.NotNull(listResult);
        Assert.NotNull(getResult.TimeToLive);
        Assert.Equal(listResult.TimeToLive, getResult.TimeToLive);
    }

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
        JsonObject entry = CreateEntry();
        entry["frontmatter"] = JsonNode.Parse(json);

        // Act & Assert
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize(json, context.McpSkillFrontmatter));
        Assert.Throws<JsonException>(() => entry.Deserialize(context.McpSkillEntry));
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
