// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentMcpSkillsSource"/>.
/// </summary>
public sealed class AgentMcpSkillsSourceTests
{
    private const string SampleSkillMd = """
        ---
        name: unit-converter
        description: Convert between common units.
        ---
        # Unit Converter

        Body content here.
        """;

    private const string SampleSkillIndex = """
        {
          "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
          "skills": [
            {
              "name": "unit-converter",
              "type": "skill-md",
              "description": "Convert between common units.",
              "url": "skill://unit-converter/SKILL.md"
            }
          ]
        }
        """;

    [Fact]
    public async Task GetSkillsAsync_IndexBasedDiscovery_ReturnsSkillAsync()
    {
        // Arrange - server exposes both skill://index.json and the skill itself.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexAndSkill>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert - frontmatter comes from index; Content is the actual SKILL.md body from the server.
        var skill = Assert.Single(skills);
        Assert.Equal("unit-converter", skill.Frontmatter.Name);
        Assert.Equal("Convert between common units.", skill.Frontmatter.Description);

        string content = await skill.GetContentAsync();
        Assert.Contains("name: unit-converter", content);
        Assert.Contains("description: Convert between common units.", content);
        Assert.Contains("Body content here.", content);
    }

    [Fact]
    public async Task GetSkillsAsync_NoIndex_ReturnsEmptyAsync()
    {
        // Arrange - server only exposes SKILL.md, no skill://index.json.
        // Per SEP-2640, discovery requires the index document; without it, no skills are surfaced.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<SkillOnly>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetResourceAsync_SiblingText_ReturnsContentAsync()
    {
        // Arrange - server exposes index, SKILL.md, and a sibling reference file.
        // The skill reads the sibling on demand via GetResourceAsync.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexAndSkillWithSibling>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var resource = await skill.GetResourceAsync("references/checklist.md");

        // Assert
        Assert.NotNull(resource);
        var content = await resource!.ReadAsync();
        Assert.Equal("- check thing 1\n- check thing 2", content);
    }

    [Fact]
    public async Task GetResourceAsync_SiblingBinary_ReturnsDataContentAsync()
    {
        // Arrange - server exposes index, SKILL.md, and a binary sibling.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexAndSkillWithBinarySibling>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var resource = await skill.GetResourceAsync("assets/icon.bin");

        // Assert
        Assert.NotNull(resource);
        var content = await resource!.ReadAsync();
        var dataContent = Assert.IsType<DataContent>(content);
        Assert.Equal("application/octet-stream", dataContent.MediaType);
        Assert.Equal([0x01, 0x02, 0x03, 0x04], dataContent.Data.ToArray());
    }

    [Fact]
    public async Task GetResourceAsync_UnknownName_ReturnsNullAsync()
    {
        // Arrange - index advertises a skill, but no sibling resource exists.
        // GetResourceAsync eagerly fetches from the MCP server; a non-existent
        // resource causes the server to return an error, so null is returned.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexAndSkill>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var resource = await skill.GetResourceAsync("references/does-not-exist.md");

        // Assert - resource does not exist on the server, so null is returned
        Assert.Null(resource);
    }

    [Theory]
    [InlineData("../escape.md")]
    [InlineData("references/../../escape.md")]
    [InlineData("..")]
    [InlineData("..\\escape.md")]
    [InlineData("/etc/passwd")]
    [InlineData("http://example.com/other")]
    [InlineData("%2e%2e/escape.md")]
    [InlineData("%2E./escape.md")]
    [InlineData(".%2e/escape.md")]
    [InlineData("references/%2e%2e/escape.md")]
    [InlineData("references%2f..%2f..%2fescape.md")]
    [InlineData("%2e%2e%5cescape.md")]
    [InlineData("%252e%252e%252fescape.md")]
    [InlineData("%25252e%25252e/escape.md")]
    [InlineData("%2fescape.md")]
    [InlineData("%5cescape.md")]
    [InlineData("%68ttp%3a%2f%2fexample.com/other")]
    [InlineData("..?download=1")]
    [InlineData("..#fragment")]
    [InlineData("%2e%2e%3fdownload=1")]
    [InlineData("references%3f/../../escape.md")]
    [InlineData("references%3f/%2e%2e/%2e%2e/escape.md")]
    [InlineData("references%23/%2e%2e/%2e%2e/escape.md")]
    [InlineData("references%3f%2f%2e%2e%2f%2e%2e%2fescape.md")]
    [InlineData("references%23%5c%2e%2e%5c%2e%2e%5cescape.md")]
    [InlineData("references%253f%252f%252e%252e%252f%252e%252e%252fescape.md")]
    [InlineData("references%2523%252f%252e%252e%252f%252e%252e%252fescape.md")]
    [InlineData("references%3f/%252e%252e/%252e%252e/escape.md")]
    [InlineData("references%3f/%2e%2e/%2e%2e/escape.md?version=1")]
    [InlineData("references%23/%2e%2e/%2e%2e/escape.md#section")]
    [InlineData("references%3f%2f%2e%2e%20")]
    [InlineData(".\t./escape.md")]
    [InlineData(".%09./escape.md")]
    [InlineData("references/\0/guide.md")]
    [InlineData(".. ")]
    [InlineData(".%2e ")]
    [InlineData("%2e%2e ")]
    [InlineData("..%20")]
    [InlineData("%252e%252e%2520")]
    [InlineData("references/.. ")]
    [InlineData("references/.. ?version=1")]
    [InlineData("references/guide.md?value=%00")]
    [InlineData("references/guide.md#value=%2509")]
    [InlineData("references/guide.md?value=%C2%85")]
    [InlineData("references/%2500guide.md?version=1")]
    [InlineData("references/guide.md?version=1#value=%2509")]
    [InlineData("references/guide.md#section?value=%2509")]
    public async Task GetResourceAsync_PathTraversalName_ReturnsNullAsync(string name)
    {
        foreach (string root in new[]
        {
            "skill://unit-converter/",
            "skill://unit-converter/private/",
            "https://example.com/skills/private/",
            "file:///skills/private/",
            "custom:skills/private/"
        })
        {
            // Arrange - accept every URI so rejection must happen before the MCP request.
            List<string> reads = [];
            await using var server = CreatePermissiveSkillServer(root + "SKILL.md", reads);
            await using var client = await server.CreateClientAsync();
            var source = new AgentMcpSkillsSource(client);
            var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
            reads.Clear();

            // Act
            var resource = await skill.GetResourceAsync(name);

            // Assert
            Assert.Null(resource);
            Assert.Empty(reads);
        }
    }

    [Theory]
    [InlineData("skill://unit-converter/")]
    [InlineData("skill://unit-converter/private/")]
    [InlineData("https://example.com/skills/private/")]
    [InlineData("file:///skills/private/")]
    [InlineData("custom:skills/private/")]
    public async Task GetResourceAsync_SafeNamesAndSchemes_ArePreservedAsync(string root)
    {
        // Arrange
        List<string> reads = [];
        await using var server = CreatePermissiveSkillServer(root + "SKILL.md", reads);
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Act
        Assert.Equal(SampleSkillMd, await skill.GetContentAsync());

        // Assert
        Assert.Equal(root + "SKILL.md", reads[1]);
        foreach (string name in new[]
        {
            "references/guide.md",
            "references\\guide.md",
            "references/guide%20one.md",
            "references/v1.2/guide.md",
            "references/%2520.md",
            "references/100%.md",
            "references/guide.md?version=1#section",
            "references/guide%3fname.md",
            "references/guide%23name.md",
            "references/guide%253fname.md",
            "references/guide.md?example=/../../other.md",
            "references/guide.md#example=/../../other.md",
            "references/guide.md?example=%2e%2e%2f%2e%2e%2fother.md",
            "references/guide.md?src=https://example.com/other",
            "references/guide%2520one.md?value=%2520#section%2520",
            "references/guide%253fname.md#section?value=%2520",
            "references/guide.md?",
            "references/guide.md#",
            "references/guide.md "
        })
        {
            reads.Clear();
            var resource = await skill.GetResourceAsync(name);
            Assert.NotNull(resource);
            Assert.Equal(name, resource.Name);
            Assert.Equal("safe content", await resource.ReadAsync());
            Assert.Equal(root + name.Replace('\\', '/'), Assert.Single(reads));
        }
    }

    [Theory]
    [InlineData(1)]
    [InlineData(31)]
    [InlineData(32)]
    [InlineData(33)]
    [InlineData(4096)]
    public async Task GetResourceAsync_DecodingDepthIsBoundedAsync(int depth)
    {
        // Arrange
        const string Root = "skill://unit-converter/private/";
        List<string> reads = [];
        await using var server = CreatePermissiveSkillServer(Root + "SKILL.md", reads);
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        string encoded = "%" + string.Concat(Enumerable.Repeat("25", depth - 1)) + "41";

        foreach (string name in new[]
        {
            $"references/{encoded}.md",
            $"references/guide.md?value={encoded}",
            $"references/guide.md#value={encoded}",
            $"../{encoded}.md"
        })
        {
            reads.Clear();

            // Act
            var resource = await skill.GetResourceAsync(name);

            // Assert
            if (depth <= 32 && !name.StartsWith("../", System.StringComparison.Ordinal))
            {
                Assert.NotNull(resource);
                Assert.Equal(name, resource.Name);
                Assert.Equal(Root + name, Assert.Single(reads));
            }
            else
            {
                Assert.Null(resource);
                Assert.Empty(reads);
            }
        }
    }

    [Fact]
    public async Task GetSkillsAsync_DoesNotReadSkillMdAsync()
    {
        // Arrange - index points to a non-existent SKILL.md URI. Because the source builds
        // skills from index info only, discovery still succeeds.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithoutSkillMdResource>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert - discovery succeeds from index alone.
        var skill = Assert.Single(skills);
        Assert.Equal("unit-converter", skill.Frontmatter.Name);
    }

    [Fact]
    public async Task GetSkillsAsync_IndexEntryWithInvalidName_IsSkippedAsync()
    {
        // Arrange - index entry has an invalid (uppercase) name, which AgentSkillFrontmatter rejects.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithInvalidName>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_IndexEntryWithMissingRequiredFields_IsSkippedAsync()
    {
        // Arrange - index entry is missing the required description and url fields.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithIncompleteEntry>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_ArchiveEntryWithUnreadableResource_IsSkippedAsync()
    {
        // Arrange - index has an "archive" entry, but the referenced archive resource does not
        // exist on the server, so reading it fails and the entry is skipped gracefully.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithArchiveOnly>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_IndexEntryWithTemplateType_IsSkippedAsync()
    {
        // Arrange - index has an "mcp-resource-template" entry (parameterized skill namespace).
        // The current source skips template entries; they require user input to materialize.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithTemplateOnly>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    private static InMemoryMcpServer CreatePermissiveSkillServer(string skillMdUri, List<string> reads)
    {
        string index = JsonSerializer.Serialize(new
        {
            skills = new[]
            {
                new { name = "unit-converter", type = "skill-md", description = "Convert between common units.", url = skillMdUri }
            }
        });
        return new InMemoryMcpServer(builder => builder.WithReadResourceHandler((request, cancellationToken) =>
        {
            string uri = request.Params!.Uri;
            reads.Add(uri);
            return ValueTask.FromResult(new ReadResourceResult
            {
                Contents = [new TextResourceContents
                {
                    Uri = uri,
                    Text = uri == "skill://index.json" ? index : uri == skillMdUri ? SampleSkillMd : "safe content",
                    MimeType = "text/plain"
                }]
            });
        }));
    }

    #region Resource classes (registered with the MCP server via WithResources<T>)

    // CA1812 flags these classes as "never instantiated", which is technically correct -
    // they are never constructed because they only contain static methods (e.g. `public static string Index()`).
    // The MCP framework discovers and invokes these static methods via the [McpServerResourceType] and
    // [McpServerResource] attributes registered through WithResources<T>(), without ever creating an instance.
#pragma warning disable CA1812

    /// <summary>
    /// Server type that exposes both <c>skill://index.json</c> and a single <c>skill-md</c> resource.
    /// </summary>
    [McpServerResourceType]
    private sealed class IndexAndSkill
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => SampleSkillIndex;

        [McpServerResource(UriTemplate = "skill://unit-converter/SKILL.md", Name = "unit-converter", MimeType = "text/markdown")]
        public static string Skill() => SampleSkillMd;
    }

    /// <summary>Server type that exposes only <c>SKILL.md</c> (no index, no siblings).</summary>
    [McpServerResourceType]
    private sealed class SkillOnly
    {
        [McpServerResource(UriTemplate = "skill://unit-converter/SKILL.md", Name = "unit-converter", MimeType = "text/markdown")]
        public static string Skill() => SampleSkillMd;
    }

    /// <summary>Server type that exposes <c>skill://index.json</c>, <c>SKILL.md</c>, and one text sibling.</summary>
    [McpServerResourceType]
    private sealed class IndexAndSkillWithSibling
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => SampleSkillIndex;

        [McpServerResource(UriTemplate = "skill://unit-converter/SKILL.md", Name = "unit-converter", MimeType = "text/markdown")]
        public static string Skill() => SampleSkillMd;

        [McpServerResource(UriTemplate = "skill://unit-converter/references/checklist.md", Name = "checklist", MimeType = "text/markdown")]
        public static string Checklist() => "- check thing 1\n- check thing 2";
    }

    /// <summary>Server type that exposes <c>skill://index.json</c>, <c>SKILL.md</c>, and one binary sibling.</summary>
    [McpServerResourceType]
    private sealed class IndexAndSkillWithBinarySibling
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => SampleSkillIndex;

        [McpServerResource(UriTemplate = "skill://unit-converter/SKILL.md", Name = "unit-converter", MimeType = "text/markdown")]
        public static string Skill() => SampleSkillMd;

        [McpServerResource(UriTemplate = "skill://unit-converter/assets/icon.bin", Name = "icon", MimeType = "application/octet-stream")]
        public static BlobResourceContents Icon() => BlobResourceContents.FromBytes(
            new byte[] { 0x01, 0x02, 0x03, 0x04 },
            "skill://unit-converter/assets/icon.bin",
            "application/octet-stream");
    }

    /// <summary>Server type that exposes only the index (no concrete SKILL.md resource).</summary>
    [McpServerResourceType]
    private sealed class IndexWithoutSkillMdResource
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => SampleSkillIndex;
    }

    /// <summary>Server type whose index entry has an invalid (uppercase) name.</summary>
    [McpServerResourceType]
    private sealed class IndexWithInvalidName
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => """
            {
              "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
              "skills": [
                {
                  "name": "UnitConverter",
                  "type": "skill-md",
                  "description": "Convert between common units.",
                  "url": "skill://UnitConverter/SKILL.md"
                }
              ]
            }
            """;
    }

    /// <summary>Server type whose index entry is missing required fields (description, url).</summary>
    [McpServerResourceType]
    private sealed class IndexWithIncompleteEntry
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => """
            {
              "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
              "skills": [
                {
                  "name": "unit-converter",
                  "type": "skill-md"
                }
              ]
            }
            """;
    }

    /// <summary>Server type whose index references only an <c>archive</c> entry.</summary>
    [McpServerResourceType]
    private sealed class IndexWithArchiveOnly
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => """
            {
              "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
              "skills": [
                {
                  "name": "some-skill",
                  "type": "archive",
                  "description": "Packaged skill.",
                  "url": "skill://some-skill.tar.gz"
                }
              ]
            }
            """;
    }

    /// <summary>Server type whose index references only an <c>mcp-resource-template</c> entry.</summary>
    [McpServerResourceType]
    private sealed class IndexWithTemplateOnly
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => """
            {
              "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
              "skills": [
                {
                  "type": "mcp-resource-template",
                  "description": "Per-product documentation skill",
                  "url": "skill://docs/{product}/SKILL.md"
                }
              ]
            }
            """;
    }

#pragma warning restore CA1812

    #endregion
}
