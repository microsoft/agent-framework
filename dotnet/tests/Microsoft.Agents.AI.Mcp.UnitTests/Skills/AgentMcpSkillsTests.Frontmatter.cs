// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class AgentMcpSkillsTests
{
    [Fact]
    public async Task GetSkillsAsync_Metadata_ProjectsOnlyAdvertisedDictionaryValuesAsync()
    {
        // Arrange
        JsonObject entry = Entry();
        entry["frontmatter"]!["metadata"] = JsonNode.Parse("""
            {
              "Owner": "Example",
              "owner": "Other",
              "count": 42,
              "enabled": true,
              "empty": null,
              "nested": { "items": [1, "two"] },
              "originaljson": "Server-provided value"
            }
            """);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        var catalog = new McpSkillsCatalog(client);

        // Act
        var skill = Assert.Single(await catalog.GetSkillsAsync(CancellationToken.None));

        // Assert
        Assert.NotNull(skill.Frontmatter.Metadata);
        Assert.Equal(6, skill.Frontmatter.Metadata.Count);
        Assert.Equal("Other", Assert.IsType<JsonElement>(skill.Frontmatter.Metadata["owner"]).GetString());
        Assert.Contains("Owner", skill.Frontmatter.Metadata.Keys);
        Assert.DoesNotContain("owner", skill.Frontmatter.Metadata.Keys);
        Assert.Equal(42, Assert.IsType<JsonElement>(skill.Frontmatter.Metadata["count"]).GetInt32());
        Assert.True(Assert.IsType<JsonElement>(skill.Frontmatter.Metadata["enabled"]).GetBoolean());
        Assert.Null(skill.Frontmatter.Metadata["empty"]);
        Assert.Equal("two", Assert.IsType<JsonElement>(skill.Frontmatter.Metadata["nested"]).GetProperty("items")[1].GetString());
        Assert.Equal("Server-provided value", Assert.IsType<JsonElement>(skill.Frontmatter.Metadata["originaljson"]).GetString());
    }

    [Theory]
    [InlineData("42")]
    [InlineData("true")]
    [InlineData("\"text\"")]
    [InlineData("[]")]
    public async Task GetSkillsAsync_NonObjectMetadata_ThrowsAsync(string metadata)
    {
        // Arrange
        JsonObject entry = Entry();
        entry["frontmatter"]!["metadata"] = JsonNode.Parse(metadata);
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act & Assert
        await Assert.ThrowsAsync<JsonException>(async () =>
            await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
    }

    [Theory]
    [InlineData(null)]
    [InlineData(0)]
    [InlineData(500)]
    public async Task GetSkillsAsync_ValidCompatibility_VerifiesAdvertisedValueAsync(int? length)
    {
        // Arrange
        string? compatibility = length is { } count ? new string('a', count) : null;
        string content = $"---\nname: unit-converter\ndescription: Convert units.\ncompatibility: {JsonSerializer.Serialize(compatibility)}\n---\nInstructions.";
        JsonObject entry = Entry(content: content);
        entry["frontmatter"]!["compatibility"] = compatibility;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)),
            (uri, _) => ValueTask.FromResult(Text(uri, content)));
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        string loaded = await skill.GetContentAsync();

        // Assert
        Assert.Equal(content, loaded);
        Assert.Null(skill.Frontmatter.Metadata);
        Assert.Null(skill.Frontmatter.Compatibility);
    }

    [Theory]
    [InlineData("""{"license":"MIT"}""", "license: Apache-2.0", "/license")]
    [InlineData("""{"compatibility":"Any runtime"}""", "compatibility: Other runtime", "/compatibility")]
    [InlineData("""{"allowed-tools":"read"}""", "allowed-tools: write", "/allowed-tools")]
    [InlineData("""{"metadata":{"owner":"Example"}}""", "metadata: {owner: Other}", "/metadata/owner")]
    [InlineData("""{"future":{"nested":[true,42]}}""", "future: {nested: [true, 43]}", "/future/nested/1")]
    [InlineData("""{"future":{"nested":[true,42]}}""", "future: {nested: [42, true]}", "/future/nested/0")]
    [InlineData("""{"future":{"nested":[true,42]}}""", "future: {nested: [true]}", "/future/nested/1")]
    [InlineData("""{"future":{"a/b~c":"first"}}""", "future: {a/b~c: second}", "/future/a~1b~0c")]
    [InlineData("""{"metadata":{"Owner":"Example"}}""", "metadata: {owner: Example}", "/metadata/owner")]
    [InlineData("""{"future":42}""", "future: '42'", "/future")]
    [InlineData("""{"future":true}""", "future: 'true'", "/future")]
    [InlineData("""{"future":" text "}""", "future: text", "/future")]
    [InlineData("""{"future":null}""", "", "/future")]
    [InlineData("{}", "future: null", "/future")]
    [InlineData("""{"future":9007199254740992}""", "future: 9007199254740993", "/future")]
    [InlineData("""{"future":0.123456789012345678901234567890}""", "future: 0.123456789012345678901234567891", "/future")]
    public async Task GetContentAsync_AnyFrontmatterDifference_ThrowsWithoutCachingOrRefreshingAsync(string advertised, string yaml, string expectedPath)
    {
        // Arrange
        string content = $"---\nname: unit-converter\ndescription: Convert units.\n{yaml}\n---\nInstructions.";
        JsonObject entry = Entry(content: content);
        foreach (var property in JsonNode.Parse(advertised)!.AsObject())
        {
            entry["frontmatter"]![property.Key] = property.Value?.DeepClone();
        }

        int reads = 0;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, content));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.IsType<AgentMcpSkill>(Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create())));

        // Act & Assert
        for (int i = 0; i < 2; i++)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
            Assert.Contains(SkillUri, exception.Message);
            Assert.Contains($"JSON pointer '{expectedPath}'", exception.Message);
        }

        Assert.Equal(2, reads);
        Assert.False(skill.NeedsRefresh);
    }

    [Fact]
    public async Task GetContentAsync_CompleteEquivalentFrontmatter_ReturnsAndCachesContentAsync()
    {
        // Arrange
        const string Content = """
            ---
            future:
              nested: [true, 1.0e2, null, {}, []]
              precise: 0.123456789012345678901234567890
              huge: 10e9998
              integer: 9007199254740993
            metadata: {Owner: Example, owner: Other}
            allowed-tools: read write
            compatibility: Any runtime
            license: 'MIT'
            description: >-
              Convert
              units.
            name: "unit\u002dconverter"
            ---
            # Instructions
            Not YAML: [
            """;
        JsonObject entry = Entry(content: Content);
        entry["frontmatter"] = JsonNode.Parse("""
            {
              "name": "unit-converter",
              "description": "Convert units.",
              "license": "MIT",
              "compatibility": "Any runtime",
              "allowed-tools": "read write",
              "metadata": { "owner": "Other", "Owner": "Example" },
              "future": {
                "integer": 9007199254740993,
                "huge": 1e9999,
                "precise": 0.1234567890123456789012345678900,
                "nested": [true, 100, null, {}, []]
              }
            }
            """);
        int reads = 0;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(entry)), (uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, Content));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        string loaded = await skill.GetContentAsync();
        string cached = await skill.GetContentAsync();

        // Assert
        Assert.Equal(Content, loaded);
        Assert.Equal(loaded, cached);
        Assert.Equal(1, reads);
        Assert.Equal("MIT", skill.Frontmatter.License);
        Assert.Null(skill.Frontmatter.Compatibility);
        Assert.Null(skill.Frontmatter.AllowedTools);
        Assert.NotNull(skill.Frontmatter.Metadata);
        Assert.Equal("Example", Assert.IsType<JsonElement>(skill.Frontmatter.Metadata["Owner"]).GetString());
        Assert.False(skill.Frontmatter.Metadata.ContainsKey("OriginalJson"));
    }

    [Theory]
    [InlineData("future: {value: first, value: second}")]
    [InlineData("future: &anchor value")]
    [InlineData("future: *missing")]
    [InlineData("future: !custom value")]
    [InlineData("future: [invalid")]
    [InlineData("future: {42: value}")]
    public async Task GetContentAsync_UnsupportedFrontmatter_ThrowsWithoutCachingAsync(string yaml)
    {
        // Arrange
        string content = $"---\nname: unit-converter\ndescription: Convert units.\n{yaml}\n---\nInstructions.";
        int reads = 0;
        await using var server = CreateServer((_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry(content: content))), (uri, _) =>
        {
            reads++;
            return ValueTask.FromResult(Text(uri, content));
        });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act & Assert
        for (int i = 0; i < 2; i++)
        {
            var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await skill.GetContentAsync());
            Assert.Contains("contains invalid frontmatter", exception.Message);
            Assert.Contains(SkillUri, exception.Message);
            Assert.NotNull(exception.InnerException);
        }

        Assert.Equal(2, reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetContentAsync_RefreshedFrontmatter_UsesSkillsGetSnapshotAsync(bool matches)
    {
        // Arrange
        const string Content = "---\nname: unit-converter\ndescription: Convert units.\nlicense: MIT\n---\nInstructions.";
        JsonObject refreshedEntry = Entry(content: Content);
        refreshedEntry["frontmatter"]!["license"] = matches ? "MIT" : "Apache-2.0";
        int reads = 0;
        var client = CreateTtlClient((request, _) => Task.FromResult(request.Method switch
        {
            "skills/list" => TtlListResult(60000, Entry()),
            "resources/read" => ResourceReadResult(SkillUri, 60000, ++reads == 1 ? SkillContent + "\nChanged." : Content),
            "skills/get" => GetSkillResult(refreshedEntry, 60000),
            _ => throw new InvalidOperationException(request.Method),
        }));
        var catalog = new McpSkillsCatalog(client.Object);
        var original = Assert.Single(await catalog.GetSkillsAsync(CancellationToken.None));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        var refreshed = Assert.Single(await catalog.GetSkillsAsync(CancellationToken.None));

        // Act & Assert
        Assert.NotSame(original, refreshed);
        if (matches)
        {
            Assert.Equal(Content, await refreshed.GetContentAsync());
            Assert.Equal(Content, await refreshed.GetContentAsync());
            Assert.Equal(2, reads);
        }
        else
        {
            for (int i = 0; i < 2; i++)
            {
                var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () => await refreshed.GetContentAsync());
                Assert.Contains("JSON pointer '/license'", exception.Message);
            }

            Assert.Equal(3, reads);
        }
    }
}
