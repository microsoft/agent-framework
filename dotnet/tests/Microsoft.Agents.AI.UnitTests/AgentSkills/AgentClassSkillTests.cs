// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentClassSkill"/> and <see cref="AgentInMemorySkillsSource"/>.
/// </summary>
public sealed class AgentClassSkillTests
{
    [Fact]
    public void Resources_DefaultsToNull_WhenNotOverridden()
    {
        // Arrange
        var skill = new MinimalClassSkill();

        // Act & Assert
        Assert.Null(skill.Resources);
    }

    [Fact]
    public void Scripts_DefaultsToNull_WhenNotOverridden()
    {
        // Arrange
        var skill = new MinimalClassSkill();

        // Act & Assert
        Assert.Null(skill.Scripts);
    }

    [Fact]
    public void Resources_ReturnsOverriddenList_WhenOverridden()
    {
        // Arrange
        var skill = new FullClassSkill();

        // Act
        var resources = skill.Resources;

        // Assert
        Assert.Single(resources!);
        Assert.Equal("test-resource", resources![0].Name);
    }

    [Fact]
    public void Scripts_ReturnsOverriddenList_WhenOverridden()
    {
        // Arrange
        var skill = new FullClassSkill();

        // Act
        var scripts = skill.Scripts;

        // Assert
        Assert.Single(scripts!);
        Assert.Equal("TestScript", scripts![0].Name);
    }

    [Fact]
    public void ResourcesAndScripts_CanBeLazyLoaded_AndCached()
    {
        // Arrange
        var skill = new LazyLoadedSkill();

        // Act & Assert
        Assert.Equal(0, skill.ResourceCreationCount);
        Assert.Equal(0, skill.ScriptCreationCount);

        var firstResources = skill.Resources;
        var firstScripts = skill.Scripts;
        var secondResources = skill.Resources;
        var secondScripts = skill.Scripts;

        Assert.Single(firstResources!);
        Assert.Single(firstScripts!);
        Assert.Same(firstResources, secondResources);
        Assert.Same(firstScripts, secondScripts);
        Assert.Equal(1, skill.ResourceCreationCount);
        Assert.Equal(1, skill.ScriptCreationCount);
    }

    [Fact]
    public void Name_Content_ReturnClassDefinedValues()
    {
        // Arrange
        var skill = new MinimalClassSkill();

        // Act & Assert
        Assert.Equal("minimal", skill.Frontmatter.Name);
        Assert.Contains("<instructions>", skill.Content);
        Assert.Contains("Minimal skill body.", skill.Content);
        Assert.Contains("</instructions>", skill.Content);
    }

    [Fact]
    public void Content_ReturnsSynthesizedXmlDocument()
    {
        // Arrange
        var skill = new MinimalClassSkill();

        // Act & Assert
        Assert.Contains("<name>minimal</name>", skill.Content);
        Assert.Contains("<description>A minimal skill.</description>", skill.Content);
        Assert.Contains("<instructions>", skill.Content);
        Assert.Contains("Minimal skill body.", skill.Content);
    }

    [Fact]
    public async Task AgentInMemorySkillsSource_ReturnsAllSkillsAsync()
    {
        // Arrange
        var skills = new AgentClassSkill[] { new MinimalClassSkill(), new FullClassSkill() };
        var source = new AgentInMemorySkillsSource(skills);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("minimal", result[0].Frontmatter.Name);
        Assert.Equal("full", result[1].Frontmatter.Name);
    }

    [Fact]
    public void AgentClassSkill_InvalidFrontmatter_ThrowsArgumentException()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentSkillFrontmatter("INVALID-NAME", "An invalid skill."));
    }

    [Fact]
    public void SkillWithOnlyResources_HasNullScripts()
    {
        // Arrange
        var skill = new ResourceOnlySkill();

        // Act & Assert
        Assert.Single(skill.Resources!);
        Assert.Null(skill.Scripts);
    }

    [Fact]
    public void SkillWithOnlyScripts_HasNullResources()
    {
        // Arrange
        var skill = new ScriptOnlySkill();

        // Act & Assert
        Assert.Null(skill.Resources);
        Assert.Single(skill.Scripts!);
    }

    [Fact]
    public void Content_ReturnsCachedInstance_OnRepeatedAccess()
    {
        // Arrange
        var skill = new FullClassSkill();

        // Act
        var first = skill.Content;
        var second = skill.Content;

        // Assert
        Assert.Same(first, second);
    }

    [Fact]
    public void Content_IncludesParametersSchema_WhenScriptsHaveParameters()
    {
        // Arrange
        var skill = new FullClassSkill();

        // Act
        var content = skill.Content;

        // Assert — scripts with typed parameters should have their schema included
        Assert.Contains("parameters_schema", content);
        Assert.Contains("value", content);
    }

    [Fact]
    public void Content_IncludesDerivedResources_WhenResourcesUseBaseTypeOverrides()
    {
        // Arrange
        var skill = new DerivedResourceSkill();

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("<resources>", content);
        Assert.Contains("custom-resource", content);
        Assert.Contains("Custom resource description.", content);
    }

    [Fact]
    public void Content_IncludesDerivedScripts_WhenScriptsUseBaseTypeOverrides()
    {
        // Arrange
        var skill = new DerivedScriptSkill();

        // Act
        var content = skill.Content;

        // Assert
        Assert.Contains("<scripts>", content);
        Assert.Contains("custom-script", content);
        Assert.Contains("Custom script description.", content);
    }

    [Fact]
    public void Content_OmitsParametersSchema_WhenDerivedScriptDoesNotProvideOne()
    {
        // Arrange
        var skill = new DerivedScriptSkill();

        // Act
        var content = skill.Content;

        // Assert
        Assert.DoesNotContain("parameters_schema", content);
    }

    #region Test skill classes

    private sealed class MinimalClassSkill : AgentClassSkill
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("minimal", "A minimal skill.");

        protected override string Instructions => "Minimal skill body.";

        public override IReadOnlyList<AgentSkillResource>? Resources => null;

        public override IReadOnlyList<AgentSkillScript>? Scripts => null;
    }

    private sealed class FullClassSkill : AgentClassSkill
    {
        private IReadOnlyList<AgentSkillResource>? _resources;
        private IReadOnlyList<AgentSkillScript>? _scripts;

        public override AgentSkillFrontmatter Frontmatter { get; } = new("full", "A full skill with resources and scripts.");

        protected override string Instructions => "Full skill body.";

        public override IReadOnlyList<AgentSkillResource>? Resources => this._resources ??=
        [
            CreateResource("test-resource", "resource content"),
        ];

        public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts ??=
        [
            CreateScript("TestScript", TestScript),
        ];

        private static string TestScript(double value) =>
            JsonSerializer.Serialize(new { result = value * 2 });
    }

    private sealed class ResourceOnlySkill : AgentClassSkill
    {
        private IReadOnlyList<AgentSkillResource>? _resources;

        public override AgentSkillFrontmatter Frontmatter { get; } = new("resource-only", "Skill with resources only.");

        protected override string Instructions => "Body.";

        public override IReadOnlyList<AgentSkillResource>? Resources => this._resources ??=
        [
            CreateResource("data", "some data"),
        ];

        public override IReadOnlyList<AgentSkillScript>? Scripts => null;
    }

    private sealed class ScriptOnlySkill : AgentClassSkill
    {
        private IReadOnlyList<AgentSkillScript>? _scripts;

        public override AgentSkillFrontmatter Frontmatter { get; } = new("script-only", "Skill with scripts only.");

        protected override string Instructions => "Body.";

        public override IReadOnlyList<AgentSkillResource>? Resources => null;

        public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts ??=
        [
            CreateScript("ToUpper", (string input) => input.ToUpperInvariant()),
        ];
    }

    private sealed class DerivedResourceSkill : AgentClassSkill
    {
        private IReadOnlyList<AgentSkillResource>? _resources;

        public override AgentSkillFrontmatter Frontmatter { get; } = new("derived-resource", "Skill with a derived resource type.");

        protected override string Instructions => "Body.";

        public override IReadOnlyList<AgentSkillResource>? Resources => this._resources ??=
        [
            new CustomResource("custom-resource", "Custom resource description."),
        ];

        public override IReadOnlyList<AgentSkillScript>? Scripts => null;
    }

    private sealed class DerivedScriptSkill : AgentClassSkill
    {
        private IReadOnlyList<AgentSkillScript>? _scripts;

        public override AgentSkillFrontmatter Frontmatter { get; } = new("derived-script", "Skill with a derived script type.");

        protected override string Instructions => "Body.";

        public override IReadOnlyList<AgentSkillResource>? Resources => null;

        public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts ??=
        [
            new CustomScript("custom-script", "Custom script description."),
        ];
    }

    private sealed class LazyLoadedSkill : AgentClassSkill
    {
        private IReadOnlyList<AgentSkillResource>? _resources;
        private IReadOnlyList<AgentSkillScript>? _scripts;

        public override AgentSkillFrontmatter Frontmatter { get; } = new("lazy-loaded", "Skill with lazily created resources and scripts.");

        protected override string Instructions => "Body.";

        public int ResourceCreationCount { get; private set; }

        public int ScriptCreationCount { get; private set; }

        public override IReadOnlyList<AgentSkillResource>? Resources => this._resources ??= this.CreateResources();

        public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts ??= this.CreateScripts();

        private IReadOnlyList<AgentSkillResource> CreateResources()
        {
            this.ResourceCreationCount++;
            return [CreateResource("lazy-resource", "resource content")];
        }

        private IReadOnlyList<AgentSkillScript> CreateScripts()
        {
            this.ScriptCreationCount++;
            return [CreateScript("LazyScript", () => "done")];
        }
    }

    private sealed class CustomResource : AgentSkillResource
    {
        public CustomResource(string name, string? description = null)
            : base(name, description)
        {
        }

        public override Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
            => Task.FromResult<object?>("resource-value");
    }

    private sealed class CustomScript : AgentSkillScript
    {
        public CustomScript(string name, string? description = null)
            : base(name, description)
        {
        }

        public override Task<object?> RunAsync(AgentSkill skill, Extensions.AI.AIFunctionArguments arguments, CancellationToken cancellationToken = default)
            => Task.FromResult<object?>("script-result");
    }

    #endregion
}
