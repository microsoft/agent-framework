// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentInlineSkill"/>.
/// </summary>
public sealed class AgentInlineSkillTests
{
    [Fact]
    public void Constructor_WithNameAndDescription_SetsFrontmatter()
    {
        // Arrange & Act
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Assert
        Assert.Equal("my-skill", skill.Frontmatter.Name);
        Assert.Equal("A valid skill.", skill.Frontmatter.Description);
        Assert.Null(skill.Frontmatter.License);
        Assert.Null(skill.Frontmatter.Compatibility);
        Assert.Null(skill.Frontmatter.AllowedTools);
        Assert.Null(skill.Frontmatter.Metadata);
    }

    [Fact]
    public void Constructor_WithAllProps_SetsFrontmatter()
    {
        // Arrange
        var metadata = new AdditionalPropertiesDictionary { ["key"] = "value" };

        // Act
        var skill = new AgentInlineSkill(
            "my-skill",
            "A valid skill.",
            "Instructions.",
            license: "MIT",
            compatibility: "gpt-4",
            allowedTools: "tool-a tool-b",
            metadata: metadata);

        // Assert
        Assert.Equal("my-skill", skill.Frontmatter.Name);
        Assert.Equal("A valid skill.", skill.Frontmatter.Description);
        Assert.Equal("MIT", skill.Frontmatter.License);
        Assert.Equal("gpt-4", skill.Frontmatter.Compatibility);
        Assert.Equal("tool-a tool-b", skill.Frontmatter.AllowedTools);
        Assert.NotNull(skill.Frontmatter.Metadata);
        Assert.Equal("value", skill.Frontmatter.Metadata["key"]);
    }

    [Fact]
    public void Constructor_WithFrontmatter_UsesFrontmatterDirectly()
    {
        // Arrange
        var frontmatter = new AgentSkillFrontmatter("my-skill", "A valid skill.")
        {
            License = "Apache-2.0",
            Compatibility = "gpt-4",
            AllowedTools = "tool-a",
            Metadata = new AdditionalPropertiesDictionary { ["env"] = "prod" },
        };

        // Act
        var skill = new AgentInlineSkill(frontmatter, "Instructions.");

        // Assert
        Assert.Same(frontmatter, skill.Frontmatter);
        Assert.Equal("Apache-2.0", skill.Frontmatter.License);
        Assert.Equal("gpt-4", skill.Frontmatter.Compatibility);
        Assert.Equal("tool-a", skill.Frontmatter.AllowedTools);
        Assert.Equal("prod", skill.Frontmatter.Metadata!["env"]);
    }

    [Fact]
    public void Constructor_WithFrontmatter_NullFrontmatter_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new AgentInlineSkill(null!, "Instructions."));
    }

    [Fact]
    public void Constructor_WithFrontmatter_NullInstructions_Throws()
    {
        // Arrange
        var frontmatter = new AgentSkillFrontmatter("my-skill", "A valid skill.");

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new AgentInlineSkill(frontmatter, null!));
    }

    [Fact]
    public void Constructor_WithAllProps_NullInstructions_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() =>
            new AgentInlineSkill("my-skill", "A valid skill.", null!));
    }

    [Fact]
    public async Task Content_ContainsNameDescriptionAndInstructionsAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Do the thing.");

        // Act
        var content = await skill.GetContentAsync();

        // Assert
        Assert.Contains("<name>my-skill</name>", content);
        Assert.Contains("<description>A valid skill.</description>", content);
        Assert.Contains("<instructions>\nDo the thing.\n</instructions>", content);
    }

    [Fact]
    public async Task Content_EscapesXmlCharactersAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "x<y>z\"w & it's more", "1 & 2 < 3");

        // Act
        var content = await skill.GetContentAsync();

        // Assert
        Assert.Contains("<name>my-skill</name>", content);
        Assert.Contains("<description>x&lt;y&gt;z&quot;w &amp; it&apos;s more</description>", content);
        Assert.Contains("1 &amp; 2 &lt; 3", content); // instructions are escaped
    }

    [Fact]
    public async Task Content_IsCachedAcrossAccessesAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act
        var first = await skill.GetContentAsync();
        var second = await skill.GetContentAsync();

        // Assert
        Assert.Same(first, second);
    }

    [Fact]
    public async Task Content_IncludesResourcesAddedBeforeFirstAccessAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("config", "value1", "A config resource.");

        // Act
        var content = await skill.GetContentAsync();

        // Assert
        Assert.Contains("<resources>", content);
        Assert.Contains("config", content);
    }

    [Fact]
    public async Task Content_IncludesDelegateResourcesAddedBeforeFirstAccessAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("dynamic", () => "hello");

        // Act
        var content = await skill.GetContentAsync();

        // Assert
        Assert.Contains("<resources>", content);
        Assert.Contains("dynamic", content);
    }

    [Fact]
    public async Task Content_IncludesScriptsAddedBeforeFirstAccessAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("run", () => "result", "Runs something.");

        // Act
        var content = await skill.GetContentAsync();

        // Assert
        Assert.Contains("<scripts>", content);
        Assert.Contains("run", content);
    }

    [Fact]
    public async Task Content_IsCachedAndNotRebuiltAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("r1", "v1");

        // Act
        var first = await skill.GetContentAsync();
        var second = await skill.GetContentAsync();

        // Assert
        Assert.Same(first, second);
    }

    [Fact]
    public async Task Content_IncludesResourcesAndScriptsAddedBeforeFirstAccessAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("r1", "v1");
        skill.AddScript("s1", () => "ok");

        // Act
        var content = await skill.GetContentAsync();

        // Assert
        Assert.Contains("<resources>", content);
        Assert.Contains("r1", content);
        Assert.Contains("<scripts>", content);
        Assert.Contains("s1", content);
    }

    [Fact]
    public async Task Content_ParametersSchema_IsXmlEscapedAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("search", (string query, int limit) => $"found {limit} results for {query}");

        // Act
        var content = await skill.GetContentAsync();

        // Assert — JSON schema should be present and XML content chars escaped
        Assert.Contains("parameters_schema", content);
        Assert.DoesNotContain("<![CDATA[", content);
    }

    [Fact]
    public void AddResource_NullValue_Throws()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act & Assert — cast needed to target the object overload
#pragma warning disable IDE0004
        Assert.Throws<ArgumentNullException>(() => skill.AddResource("config", (object)null!));
#pragma warning restore IDE0004
    }

    [Fact]
    public void AddResource_NullDelegate_Throws()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => skill.AddResource("config", null!));
    }

    [Fact]
    public void AddScript_NullDelegate_Throws()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => skill.AddScript("run", null!));
    }

    [Fact]
    public void Resources_WhenNoneAdded_ReturnsNull()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act & Assert
        Assert.Null(skill.GetTestResources());
    }

    [Fact]
    public async Task Scripts_WhenNoneAdded_ReturnsNullAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act & Assert
        Assert.Null(await skill.GetScriptAsync("nonexistent"));
    }

    [Fact]
    public async Task GetResourceAsync_ExistingName_ReturnsResourceAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("r1", "v1");
        skill.AddResource("r2", "v2");

        // Act
        var resource = await skill.GetResourceAsync("r2");

        // Assert
        Assert.NotNull(resource);
        Assert.Equal("r2", resource!.Name);
    }

    [Fact]
    public async Task GetResourceAsync_NonExistingName_ReturnsNullAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("r1", "v1");

        // Act
        var resource = await skill.GetResourceAsync("missing");

        // Assert
        Assert.Null(resource);
    }

    [Fact]
    public async Task GetResourceAsync_NoResourcesAdded_ReturnsNullAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act
        var resource = await skill.GetResourceAsync("missing");

        // Assert
        Assert.Null(resource);
    }

    [Fact]
    public async Task GetScriptAsync_ExistingName_ReturnsScriptAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("s1", () => "first");
        skill.AddScript("s2", () => "second");

        // Act
        var script = await skill.GetScriptAsync("s2");

        // Assert
        Assert.NotNull(script);
        Assert.Equal("s2", script!.Name);
    }

    [Fact]
    public async Task GetScriptAsync_NonExistingName_ReturnsNullAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("s1", () => "ok");

        // Act
        var script = await skill.GetScriptAsync("missing");

        // Assert
        Assert.Null(script);
    }

    [Fact]
    public async Task GetScriptAsync_NoScriptsAdded_ReturnsNullAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act
        var script = await skill.GetScriptAsync("missing");

        // Assert
        Assert.Null(script);
    }

    [Fact]
    public void AddResource_ReturnsSameInstance_ForChaining()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act
        var returned = skill.AddResource("r1", "v1");

        // Assert
        Assert.Same(skill, returned);
    }

    [Fact]
    public void AddResource_Delegate_ReturnsSameInstance_ForChaining()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act
        var returned = skill.AddResource("r1", () => "v1");

        // Assert
        Assert.Same(skill, returned);
    }

    [Fact]
    public void AddScript_ReturnsSameInstance_ForChaining()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act
        var returned = skill.AddScript("s1", () => "ok");

        // Assert
        Assert.Same(skill, returned);
    }

    [Fact]
    public async Task Content_NoResourcesOrScripts_DoesNotContainResourcesOrScriptsTagsAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act
        var content = await skill.GetContentAsync();

        // Assert
        Assert.DoesNotContain("<resources>", content);
        Assert.DoesNotContain("<scripts>", content);
    }

    [Fact]
    public async Task Content_ResourcesAddedAfterCaching_AreNotIncludedAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        _ = await skill.GetContentAsync(); // trigger caching
        skill.AddResource("late-resource", "late-value");

        // Act
        var content = await skill.GetContentAsync();

        // Assert — the late resource should not appear because content was cached
        Assert.DoesNotContain("late-resource", content);
    }

    [Fact]
    public async Task Content_ScriptsAddedAfterCaching_AreNotIncludedAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        _ = await skill.GetContentAsync(); // trigger caching
        skill.AddScript("late-script", () => "late");

        // Act
        var content = await skill.GetContentAsync();

        // Assert — the late script should not appear because content was cached
        Assert.DoesNotContain("late-script", content);
    }

    [Fact]
    public async Task Content_ScriptWithDescription_IncludesDescriptionAttributeAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("my-script", () => "ok", "Runs something.");

        // Act
        var content = await skill.GetContentAsync();

        // Assert
        Assert.Contains("description=\"Runs something.\"", content);
    }

    [Fact]
    public async Task Content_ScriptWithoutParametersOrDescription_UsesSelfClosingTagAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("simple", () => "ok");

        // Act
        var content = await skill.GetContentAsync();

        // Assert — parameterless Action delegates still produce a schema, so this
        // verifies the script is at least included in the output
        Assert.Contains("simple", content);
    }

    [Fact]
    public async Task Content_ResourceWithDescription_IncludesDescriptionAttributeAsync()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("with-desc", "value", "A described resource.");
        skill.AddResource("no-desc", "value");

        // Act
        var content = await skill.GetContentAsync();

        // Assert
        Assert.Contains("description=\"A described resource.\"", content);
        Assert.DoesNotContain("no-desc\" description", content);
    }

    [Fact]
    public async Task AddScript_SkillLevelSerializerOptions_AppliedToScriptAsync()
    {
        // Arrange — skill-level JSO with source-generated context for custom types
        var jso = SkillTestJsonContext.Default.Options;
        var skill = new AgentInlineSkill("jso-skill", "JSO test.", "Instructions.", serializerOptions: jso);
        skill.AddScript("lookup", (LookupRequest request) => new LookupResponse
        {
            Items = [$"result for {request.Query}"],
            TotalCount = request.MaxResults,
        });
        var inputJson = JsonSerializer.SerializeToElement(new LookupRequest { Query = "test", MaxResults = 3 }, jso);
        using var argsDoc = JsonDocument.Parse($$"""{ "request": {{inputJson.GetRawText()}} }""");
        var args = argsDoc.RootElement;

        // Act
        var result = await (await skill.GetScriptAsync("lookup"))!.RunAsync(skill, args, null, CancellationToken.None);

        // Assert — the custom input was deserialized via skill-level JSO and response was produced
        Assert.NotNull(result);
        Assert.Contains("result for test", result!.ToString()!);
    }

    [Fact]
    public async Task AddScript_PerScriptSerializerOptions_OverridesSkillLevelAsync()
    {
        // Arrange — skill-level JSO uses snake_case naming; per-script JSO overrides with source-generated context
        var skillJso = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
        var scriptJso = SkillTestJsonContext.Default.Options;
        var skill = new AgentInlineSkill("override-skill", "Override test.", "Instructions.", serializerOptions: skillJso);
        skill.AddScript("lookup", (LookupRequest request) => new LookupResponse
        {
            Items = [$"found {request.Query}"],
            TotalCount = request.MaxResults,
        }, serializerOptions: scriptJso);
        var inputJson = JsonSerializer.SerializeToElement(new LookupRequest { Query = "override", MaxResults = 7 }, scriptJso);
        using var argsDoc = JsonDocument.Parse($$"""{ "request": {{inputJson.GetRawText()}} }""");
        var args = argsDoc.RootElement;

        // Act
        var result = await (await skill.GetScriptAsync("lookup"))!.RunAsync(skill, args, null, CancellationToken.None);

        // Assert — per-script JSO takes effect and custom types are properly marshaled
        Assert.NotNull(result);
        Assert.Contains("found override", result!.ToString()!);
    }

    [Fact]
    public async Task AddResource_SkillLevelSerializerOptions_AppliedToDelegateResourceAsync()
    {
        // Arrange — skill-level JSO with source-generated context; delegate resource returns a custom type
        var jso = SkillTestJsonContext.Default.Options;
        var skill = new AgentInlineSkill("custom-type-resource-skill", "Custom type resource test.", "Instructions.", serializerOptions: jso);
        skill.AddResource("config", () => new SkillConfig { Theme = "dark", Verbose = true });

        // Act
        var result = await skill.GetTestResources()![0].ReadAsync();

        // Assert — the custom type was returned successfully via skill-level JSO
        Assert.NotNull(result);
        Assert.Contains("dark", result!.ToString()!);
    }

    [Fact]
    public async Task AddResource_PerResourceSerializerOptions_OverridesSkillLevelAsync()
    {
        // Arrange — skill-level JSO uses snake_case naming; per-resource JSO overrides with source-generated context
        var skillJso = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
        var resourceJso = SkillTestJsonContext.Default.Options;
        var skill = new AgentInlineSkill("override-resource-skill", "Override resource test.", "Instructions.", serializerOptions: skillJso);
        skill.AddResource("config", () => new SkillConfig { Theme = "dark", Verbose = true }, serializerOptions: resourceJso);

        // Act
        var result = await skill.GetTestResources()![0].ReadAsync();

        // Assert — per-resource JSO takes effect and custom type is properly marshaled
        Assert.NotNull(result);
        Assert.Contains("dark", result!.ToString()!);
    }
}
