// Copyright (c) Microsoft. All rights reserved.

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
        // Arrange — server exposes both skill://index.json and the skill itself.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexAndSkill>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — frontmatter comes from index; Content is the actual SKILL.md body from the server.
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
        // Arrange — server only exposes SKILL.md, no skill://index.json.
        // Per SEP-2640, discovery requires the index document; without it, no skills are surfaced.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<SkillOnly>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetResourceAsync_SiblingText_ReturnsContentAsync()
    {
        // Arrange — server exposes index, SKILL.md, and a sibling reference file.
        // The skill reads the sibling on demand via GetResourceAsync.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexAndSkillWithSibling>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync());
        var resource = await skill.GetResourceAsync("references/checklist.md");

        // Assert
        Assert.NotNull(resource);
        var content = await resource!.ReadAsync();
        Assert.Equal("- check thing 1\n- check thing 2", content);
    }

    [Fact]
    public async Task GetResourceAsync_SiblingBinary_ReturnsDataContentAsync()
    {
        // Arrange — server exposes index, SKILL.md, and a binary sibling.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexAndSkillWithBinarySibling>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync());
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
        // Arrange — index advertises a skill, but no sibling resource exists.
        // GetResourceAsync eagerly fetches from the MCP server; a non-existent
        // resource causes the server to return an error, so null is returned.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexAndSkill>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync());
        var resource = await skill.GetResourceAsync("references/does-not-exist.md");

        // Assert — resource does not exist on the server, so null is returned
        Assert.Null(resource);
    }

    [Theory]
    [InlineData("../escape.md")]
    [InlineData("references/../../escape.md")]
    [InlineData("..")]
    public async Task GetResourceAsync_PathTraversalName_ReturnsNullAsync(string name)
    {
        // Arrange — '..' segments result in URIs that don't match any server resource.
        // The MCP server returns an error for unknown URIs, so GetResourceAsync returns null.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexAndSkill>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync());
        var resource = await skill.GetResourceAsync(name);

        // Assert — resource does not exist on the server, so null is returned
        Assert.Null(resource);
    }

    [Fact]
    public async Task GetSkillsAsync_DoesNotReadSkillMdAsync()
    {
        // Arrange — index points to a non-existent SKILL.md URI. Because the source builds
        // skills from index info only, discovery still succeeds.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithoutSkillMdResource>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — discovery succeeds from index alone.
        var skill = Assert.Single(skills);
        Assert.Equal("unit-converter", skill.Frontmatter.Name);
    }

    [Fact]
    public async Task GetSkillsAsync_IndexEntryWithInvalidName_IsSkippedAsync()
    {
        // Arrange — index entry has an invalid (uppercase) name, which AgentSkillFrontmatter rejects.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithInvalidName>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_IndexEntryWithMissingRequiredFields_IsSkippedAsync()
    {
        // Arrange — index entry is missing the required description and url fields.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithIncompleteEntry>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_IndexEntryWithUnsupportedType_IsSkippedAsync()
    {
        // Arrange — index has an "archive" entry, which this source does not support.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithArchiveOnly>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_IndexEntryWithTemplateType_IsSkippedAsync()
    {
        // Arrange — index has an "mcp-resource-template" entry (parameterized skill namespace).
        // The current source skips template entries; they require user input to materialize.
        await using var server = new InMemoryMcpServer(builder =>
            builder.WithResources<IndexWithTemplateOnly>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    #region Resource classes (registered with the MCP server via WithResources<T>)

    // CA1812 flags these classes as "never instantiated", which is technically correct —
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
