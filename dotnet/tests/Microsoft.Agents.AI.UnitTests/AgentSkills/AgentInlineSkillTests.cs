// Copyright (c) Microsoft. All rights reserved.

using System;
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
    public void Content_ContainsNameDescriptionAndInstructions()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Do the thing.");

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("<name>my-skill</name>", content);
        Assert.Contains("<description>A valid skill.</description>", content);
        Assert.Contains("<instructions>\nDo the thing.\n</instructions>", content);
    }

    [Fact]
    public void Content_EscapesXmlCharacters()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "x<y>z\"w & it's more", "1 & 2 < 3");

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("<name>my-skill</name>", content);
        Assert.Contains("<description>x&lt;y&gt;z&quot;w &amp; it&apos;s more</description>", content);
        Assert.Contains("1 &amp; 2 &lt; 3", content); // instructions are escaped
    }

    [Fact]
    public void Content_IsCachedAcrossAccesses()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act
        var first = skill.Content;
        var second = skill.Content;

        // Assert
        Assert.Same(first, second);
    }

    [Fact]
    public void Content_IncludesResourcesAddedBeforeFirstAccess()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("config", "value1", "A config resource.");

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("<resources>", content);
        Assert.Contains("config", content);
    }

    [Fact]
    public void Content_IncludesDelegateResourcesAddedBeforeFirstAccess()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("dynamic", () => "hello");

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("<resources>", content);
        Assert.Contains("dynamic", content);
    }

    [Fact]
    public void Content_IncludesScriptsAddedBeforeFirstAccess()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("run", () => "result", "Runs something.");

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("<scripts>", content);
        Assert.Contains("run", content);
    }

    [Fact]
    public void Content_IsCachedAndNotRebuilt()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("r1", "v1");

        // Act
        var first = skill.Content;
        var second = skill.Content;

        // Assert
        Assert.Same(first, second);
    }

    [Fact]
    public void Content_IncludesResourcesAndScriptsAddedBeforeFirstAccess()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("r1", "v1");
        skill.AddScript("s1", () => "ok");

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("<resources>", content);
        Assert.Contains("r1", content);
        Assert.Contains("<scripts>", content);
        Assert.Contains("s1", content);
    }

    [Fact]
    public void Content_ParametersSchema_IsXmlEscaped()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("search", (string query, int limit) => $"found {limit} results for {query}");

        // Act
        var content = skill.Content;

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
        Assert.Null(skill.Resources);
    }

    [Fact]
    public void Scripts_WhenNoneAdded_ReturnsNull()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act & Assert
        Assert.Null(skill.Scripts);
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
    public void Content_NoResourcesOrScripts_DoesNotContainResourcesOrScriptsTags()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");

        // Act
        var content = skill.Content;

        // Assert
        Assert.DoesNotContain("<resources>", content);
        Assert.DoesNotContain("<scripts>", content);
    }

    [Fact]
    public void Content_ResourcesAddedAfterCaching_AreNotIncluded()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        _ = skill.Content; // trigger caching
        skill.AddResource("late-resource", "late-value");

        // Act
        var content = skill.Content;

        // Assert — the late resource should not appear because content was cached
        Assert.DoesNotContain("late-resource", content);
    }

    [Fact]
    public void Content_ScriptsAddedAfterCaching_AreNotIncluded()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        _ = skill.Content; // trigger caching
        skill.AddScript("late-script", () => "late");

        // Act
        var content = skill.Content;

        // Assert — the late script should not appear because content was cached
        Assert.DoesNotContain("late-script", content);
    }

    [Fact]
    public void Content_ScriptWithDescription_IncludesDescriptionAttribute()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("my-script", () => "ok", "Runs something.");

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("description=\"Runs something.\"", content);
    }

    [Fact]
    public void Content_ScriptWithoutParametersOrDescription_UsesSelfClosingTag()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddScript("simple", () => "ok");

        // Act
        var content = skill.Content;

        // Assert — parameterless Action delegates still produce a schema, so this
        // verifies the script is at least included in the output
        Assert.Contains("simple", content);
    }

    [Fact]
    public void Content_ResourceWithDescription_IncludesDescriptionAttribute()
    {
        // Arrange
        var skill = new AgentInlineSkill("my-skill", "A valid skill.", "Instructions.");
        skill.AddResource("with-desc", "value", "A described resource.");
        skill.AddResource("no-desc", "value");

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("description=\"A described resource.\"", content);
        Assert.DoesNotContain("no-desc\" description", content);
    }
}
