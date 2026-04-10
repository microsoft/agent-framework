// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentClassSkill{TSelf}"/> and <see cref="AgentInMemorySkillsSource"/>.
/// </summary>
public sealed class AgentClassSkillTests
{
    [Fact]
    public void MinimalClassSkill_HasNullOverrides_AndSynthesizesContent()
    {
        // Arrange
        var skill = new MinimalClassSkill();

        // Act & Assert — null overrides
        Assert.Equal("minimal", skill.Frontmatter.Name);
        Assert.Null(skill.Resources);
        Assert.Null(skill.Scripts);

        // Act & Assert — synthesized XML content
        Assert.Contains("<name>minimal</name>", skill.Content);
        Assert.Contains("<description>A minimal skill.</description>", skill.Content);
        Assert.Contains("<instructions>", skill.Content);
        Assert.Contains("Minimal skill body.", skill.Content);
        Assert.Contains("</instructions>", skill.Content);
    }

    [Fact]
    public void FullClassSkill_ReturnsOverriddenLists_AndCachesContent()
    {
        // Arrange
        var skill = new FullClassSkill();

        // Act & Assert — overridden resources and scripts
        Assert.Single(skill.Resources!);
        Assert.Equal("test-resource", skill.Resources![0].Name);

        Assert.Single(skill.Scripts!);
        Assert.Equal("TestScript", skill.Scripts![0].Name);

        // Act & Assert — Content is cached
        Assert.Same(skill.Content, skill.Content);

        // Act & Assert — Content includes parameter schema from typed script
        Assert.Contains("parameters_schema", skill.Content);
        Assert.Contains("value", skill.Content);
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
    public async Task AgentInMemorySkillsSource_ReturnsAllSkillsAsync()
    {
        // Arrange
        var skills = new AgentSkill[] { new MinimalClassSkill(), new FullClassSkill() };
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
    public void PartialOverrides_OneCollectionNull_OtherHasValues()
    {
        // Arrange
        var resourceOnly = new ResourceOnlySkill();
        var scriptOnly = new ScriptOnlySkill();

        // Act & Assert
        Assert.Single(resourceOnly.Resources!);
        Assert.Null(resourceOnly.Scripts);
        Assert.Null(scriptOnly.Resources);
        Assert.Single(scriptOnly.Scripts!);
    }

    [Fact]
    public async Task CreateScriptAndResource_WithSerializerOptions_HandleCustomTypesAsync()
    {
        // Arrange
        var skill = new CustomTypeSkill();
        var jso = SkillTestJsonContext.Default.Options;

        // Act — script with custom type deserialization
        var script = skill.Scripts![0];
        var inputJson = JsonSerializer.SerializeToElement(new LookupRequest { Query = "test", MaxResults = 5 }, jso);
        var args = new AIFunctionArguments { ["request"] = inputJson };
        var scriptResult = await script.RunAsync(skill, args, CancellationToken.None);

        // Assert
        Assert.NotNull(scriptResult);
        var resultText = scriptResult!.ToString()!;
        Assert.Contains("result for test", resultText);
        Assert.Contains("5", resultText);

        // Act — resource with custom type serialization
        var resourceResult = await skill.Resources![0].ReadAsync();

        // Assert
        Assert.NotNull(resourceResult);
        Assert.Contains("dark", resourceResult!.ToString()!);
    }

    [Fact]
    public void Scripts_DiscoveredViaAttribute_WithCorrectNamesAndDescriptions()
    {
        // Arrange
        var skill = new AttributedScriptsSkill();

        // Act
        var scripts = skill.Scripts;

        // Assert — all scripts discovered with correct metadata
        Assert.NotNull(scripts);
        Assert.Equal(4, scripts!.Count);
        Assert.Contains(scripts, s => s.Name == "do-work");
        Assert.Contains(scripts, s => s.Name == "DefaultNamed");
        Assert.Contains(scripts, s => s.Name == "append");

        var processScript = scripts.First(s => s.Name == "process");
        Assert.Equal("Processes the input.", processScript.Description);
    }

    [Fact]
    public async Task Scripts_DiscoveredViaAttribute_StaticAndInstance_CanBeInvokedAsync()
    {
        // Arrange
        var skill = new AttributedScriptsSkill();

        // Act & Assert — static method
        var doWorkScript = skill.Scripts!.First(s => s.Name == "do-work");
        var doWorkResult = await doWorkScript.RunAsync(skill, new AIFunctionArguments { ["input"] = "hello" }, CancellationToken.None);
        Assert.Equal("HELLO", doWorkResult?.ToString());

        // Act & Assert — instance method
        var appendScript = skill.Scripts!.First(s => s.Name == "append");
        var appendResult = await appendScript.RunAsync(skill, new AIFunctionArguments { ["input"] = "test" }, CancellationToken.None);
        Assert.Equal("test-suffix", appendResult?.ToString());
    }

    [Fact]
    public void Resources_DiscoveredViaAttribute_OnProperties_WithCorrectMetadata()
    {
        // Arrange
        var skill = new AttributedResourcePropertiesSkill();

        // Act
        var resources = skill.Resources;

        // Assert — all resources discovered with correct metadata
        Assert.NotNull(resources);
        Assert.Equal(4, resources!.Count);
        Assert.Contains(resources, r => r.Name == "ref-data");
        Assert.Contains(resources, r => r.Name == "DefaultNamed");
        Assert.Contains(resources, r => r.Name == "static-data");

        var describedResource = resources.First(r => r.Name == "data");
        Assert.Equal("Some important data.", describedResource.Description);
    }

    [Fact]
    public async Task Resources_DiscoveredViaAttribute_OnProperties_CanBeReadAsync()
    {
        // Arrange
        var skill = new AttributedResourcePropertiesSkill();

        // Act & Assert — instance property
        var refData = skill.Resources!.First(r => r.Name == "ref-data");
        Assert.Equal("Reference content.", (await refData.ReadAsync())?.ToString());

        // Act & Assert — static property
        var staticData = skill.Resources!.First(r => r.Name == "static-data");
        Assert.Equal("Static content.", (await staticData.ReadAsync())?.ToString());
    }

    [Fact]
    public async Task Resources_DiscoveredViaAttribute_OnProperty_InvokedEachTimeAsync()
    {
        // Arrange
        var skill = new AttributedResourceDynamicPropertySkill();
        var resource = skill.Resources![0];

        // Act
        var first = await resource.ReadAsync();
        var second = await resource.ReadAsync();

        // Assert — property getter is called on each ReadAsync, producing different values
        Assert.Equal("call-1", first?.ToString());
        Assert.Equal("call-2", second?.ToString());
        Assert.Equal(2, skill.CallCount);
    }

    [Fact]
    public void Resources_DiscoveredViaAttribute_OnMethods_WithCorrectMetadata()
    {
        // Arrange
        var skill = new AttributedResourceMethodsSkill();

        // Act
        var resources = skill.Resources;

        // Assert
        Assert.NotNull(resources);
        Assert.Equal(4, resources!.Count);
        Assert.Contains(resources, r => r.Name == "dynamic");
        Assert.Contains(resources, r => r.Name == "GetData");
        Assert.Contains(resources, r => r.Name == "instance-dynamic");

        var describedResource = resources.First(r => r.Name == "info");
        Assert.Equal("Returns runtime info.", describedResource.Description);
    }

    [Fact]
    public async Task Resources_DiscoveredViaAttribute_OnMethods_CanBeReadAsync()
    {
        // Arrange
        var skill = new AttributedResourceMethodsSkill();

        // Act & Assert — static method
        var dynamicResource = skill.Resources!.First(r => r.Name == "dynamic");
        Assert.Equal("dynamic-value", (await dynamicResource.ReadAsync())?.ToString());

        // Act & Assert — instance method
        var instanceResource = skill.Resources!.First(r => r.Name == "instance-dynamic");
        Assert.Equal("instance-method-value", (await instanceResource.ReadAsync())?.ToString());
    }

    [Fact]
    public void AttributedFullSkill_IncludesContentWithSchema_AndCachesMembers()
    {
        // Arrange
        var skill = new AttributedFullSkill();

        // Act & Assert — Content includes reflected resources and scripts
        Assert.Contains("<resources>", skill.Content);
        Assert.Contains("conversion-table", skill.Content);
        Assert.Contains("<scripts>", skill.Content);
        Assert.Contains("convert", skill.Content);

        // Act & Assert — discovered members are cached
        Assert.Same(skill.Resources, skill.Resources);
        Assert.Same(skill.Scripts, skill.Scripts);

        // Act & Assert — script has parameters schema
        var script = skill.Scripts![0];
        Assert.NotNull(script.ParametersSchema);
        Assert.Contains("value", script.ParametersSchema!.Value.GetRawText());
    }

    [Fact]
    public void NoAttributedMembers_NoOverrides_ReturnsNull()
    {
        // Arrange — skill with no attributes and no overrides; base discovery returns null (not empty list)
        var skill = new NoAttributesNoOverridesSkill();
        var baseType = typeof(AgentClassSkill<NoAttributesNoOverridesSkill>);
        var resourcesDiscoveredField = baseType.GetField("_resourcesDiscovered", BindingFlags.Instance | BindingFlags.NonPublic);
        var scriptsDiscoveredField = baseType.GetField("_scriptsDiscovered", BindingFlags.Instance | BindingFlags.NonPublic);
        var reflectedResourcesField = baseType.GetField("_reflectedResources", BindingFlags.Instance | BindingFlags.NonPublic);
        var reflectedScriptsField = baseType.GetField("_reflectedScripts", BindingFlags.Instance | BindingFlags.NonPublic);

        Assert.NotNull(resourcesDiscoveredField);
        Assert.NotNull(scriptsDiscoveredField);
        Assert.NotNull(reflectedResourcesField);
        Assert.NotNull(reflectedScriptsField);
        Assert.False((bool)resourcesDiscoveredField!.GetValue(skill)!);
        Assert.False((bool)scriptsDiscoveredField!.GetValue(skill)!);

        // Act & Assert
        Assert.Null(skill.Resources);
        Assert.Null(skill.Scripts);
        Assert.True((bool)resourcesDiscoveredField.GetValue(skill)!);
        Assert.True((bool)scriptsDiscoveredField.GetValue(skill)!);
        Assert.Null(reflectedResourcesField!.GetValue(skill));
        Assert.Null(reflectedScriptsField!.GetValue(skill));

        // Repeated access should not re-trigger discovery even when discovered value is null.
        Assert.Null(skill.Resources);
        Assert.Null(skill.Scripts);
        Assert.True((bool)resourcesDiscoveredField.GetValue(skill)!);
        Assert.True((bool)scriptsDiscoveredField.GetValue(skill)!);
        Assert.Null(reflectedResourcesField.GetValue(skill));
        Assert.Null(reflectedScriptsField.GetValue(skill));
    }

    [Fact]
    public void SubclassOverride_TakesPrecedence_OverAttributes()
    {
        // Arrange — skill has attributes AND overrides Resources/Scripts
        var skill = new AttributedWithOverrideSkill();

        // Act
        var resources = skill.Resources;
        var scripts = skill.Scripts;

        // Assert — overrides win, not reflected members
        Assert.NotNull(resources);
        Assert.Single(resources!);
        Assert.Equal("manual-resource", resources![0].Name);
        Assert.NotNull(scripts);
        Assert.Single(scripts!);
        Assert.Equal("ManualScript", scripts![0].Name);
    }

    [Fact]
    public async Task MixedStaticAndInstance_AllDiscoveredAndInvocableAsync()
    {
        // Arrange
        var skill = new MixedStaticInstanceSkill();

        // Act & Assert — correct counts
        Assert.NotNull(skill.Resources);
        Assert.Equal(2, skill.Resources!.Count);
        Assert.NotNull(skill.Scripts);
        Assert.Equal(2, skill.Scripts!.Count);

        // Act & Assert — all resources produce values
        foreach (var resource in skill.Resources!)
        {
            var value = await resource.ReadAsync();
            Assert.NotNull(value);
        }

        // Act & Assert — all scripts produce values
        foreach (var script in skill.Scripts!)
        {
            var result = await script.RunAsync(skill, new AIFunctionArguments(), CancellationToken.None);
            Assert.NotNull(result);
        }
    }

    [Fact]
    public async Task SerializerOptions_UsedForReflectedMembersAsync()
    {
        // Arrange
        var skill = new AttributedSkillWithCustomSerializer();
        var jso = SkillTestJsonContext.Default.Options;

        // Act & Assert — script with custom JSO
        var script = skill.Scripts![0];
        var inputJson = JsonSerializer.SerializeToElement(new LookupRequest { Query = "test", MaxResults = 3 }, jso);
        var args = new AIFunctionArguments { ["request"] = inputJson };
        var scriptResult = await script.RunAsync(skill, args, CancellationToken.None);
        Assert.NotNull(scriptResult);
        Assert.Contains("test", scriptResult!.ToString()!);
        Assert.Contains("3", scriptResult!.ToString()!);

        // Act & Assert — resource with custom JSO
        var resourceResult = await skill.Resources![0].ReadAsync();
        Assert.NotNull(resourceResult);
        Assert.Contains("light", resourceResult!.ToString()!);
    }

    [Fact]
    public void Content_IncludesDescription_ForReflectedResources()
    {
        // Arrange
        var skill = new AttributedResourcePropertiesSkill();

        // Act
        var content = skill.Content;

        // Assert — descriptions from [Description] attribute appear in synthesized content
        Assert.Contains("Some important data.", content);
    }

    [Fact]
    public void IndexerPropertyWithResourceAttribute_ThrowsInvalidOperationException()
    {
        // Arrange
        var skill = new IndexerResourceSkill();

        // Act & Assert — accessing Resources triggers discovery which should throw
        var ex = Assert.Throws<InvalidOperationException>(() => skill.Resources);
        Assert.Contains("indexer", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("IndexerResourceSkill", ex.Message);
    }

    [Fact]
    public void ResourceMethodWithUnsupportedParameters_ThrowsInvalidOperationException()
    {
        // Arrange
        var skill = new UnsupportedParamResourceMethodSkill();

        // Act & Assert — accessing Resources triggers discovery which should throw
        var ex = Assert.Throws<InvalidOperationException>(() => skill.Resources);
        Assert.Contains("content", ex.Message);
        Assert.Contains("String", ex.Message);
    }

    [Fact]
    public async Task ResourceMethodWithServiceProviderParam_IsDiscoveredSuccessfullyAsync()
    {
        // Arrange
        var skill = new ServiceProviderResourceMethodSkill();
        var sp = new ServiceCollection().BuildServiceProvider();

        // Act
        var resources = skill.Resources;

        // Assert
        Assert.NotNull(resources);
        Assert.Single(resources!);
        Assert.Equal("sp-resource", resources![0].Name);

        var value = await resources[0].ReadAsync(sp);
        Assert.Equal("from-sp-method", value?.ToString());
    }

    [Fact]
    public async Task ResourceMethodWithCancellationTokenParam_IsDiscoveredSuccessfullyAsync()
    {
        // Arrange
        var skill = new CancellationTokenResourceMethodSkill();

        // Act
        var resources = skill.Resources;

        // Assert
        Assert.NotNull(resources);
        Assert.Single(resources!);
        Assert.Equal("ct-resource", resources![0].Name);

        var value = await resources[0].ReadAsync();
        Assert.Equal("from-ct-method", value?.ToString());
    }

    [Fact]
    public async Task ResourceMethodWithBothServiceProviderAndCancellationToken_IsDiscoveredSuccessfullyAsync()
    {
        // Arrange
        var skill = new BothParamsResourceMethodSkill();
        var sp = new ServiceCollection().BuildServiceProvider();

        // Act
        var resources = skill.Resources;

        // Assert
        Assert.NotNull(resources);
        Assert.Single(resources!);
        Assert.Equal("both-resource", resources![0].Name);

        var value = await resources[0].ReadAsync(sp);
        Assert.Equal("from-both-method", value?.ToString());
    }

    [Fact]
    public async Task CreateScript_FallsBackToSerializerOptions_WhenNoExplicitJsoAsync()
    {
        // Arrange
        var skill = new CreateMethodsFallbackSkill();

        // Act — invoke script that uses custom types, relying on SerializerOptions fallback
        var script = skill.Scripts!.First(s => s.Name == "Lookup");
        var jso = SkillTestJsonContext.Default.Options;
        var inputJson = JsonSerializer.SerializeToElement(new LookupRequest { Query = "fallback", MaxResults = 7 }, jso);
        var args = new AIFunctionArguments { ["request"] = inputJson };
        var result = await script.RunAsync(skill, args, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Contains("fallback", result!.ToString()!);
        Assert.Contains("7", result!.ToString()!);
    }

    [Fact]
    public async Task CreateResource_FallsBackToSerializerOptions_WhenNoExplicitJsoAsync()
    {
        // Arrange
        var skill = new CreateMethodsFallbackSkill();

        // Act — read resource that uses custom types, relying on SerializerOptions fallback
        var resource = skill.Resources!.First(r => r.Name == "config");
        var result = await resource.ReadAsync();

        // Assert
        Assert.NotNull(result);
        Assert.Contains("dark", result!.ToString()!);
    }

    [Fact]
    public async Task CreateScript_UsesExplicitJso_OverSerializerOptionsAsync()
    {
        // Arrange
        var skill = new CreateMethodsExplicitJsoSkill();

        // Act — invoke script that passes explicit JSO (should take precedence over SerializerOptions)
        var script = skill.Scripts!.First(s => s.Name == "Lookup");
        var jso = SkillTestJsonContext.Default.Options;
        var inputJson = JsonSerializer.SerializeToElement(new LookupRequest { Query = "explicit", MaxResults = 2 }, jso);
        var args = new AIFunctionArguments { ["request"] = inputJson };
        var result = await script.RunAsync(skill, args, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        Assert.Contains("explicit", result!.ToString()!);
        Assert.Contains("2", result!.ToString()!);
    }

    [Fact]
    public async Task CreateResource_UsesExplicitJso_OverSerializerOptionsAsync()
    {
        // Arrange
        var skill = new CreateMethodsExplicitJsoSkill();

        // Act — read resource that passes explicit JSO (should take precedence over SerializerOptions)
        var resource = skill.Resources!.First(r => r.Name == "config");
        var result = await resource.ReadAsync();

        // Assert
        Assert.NotNull(result);
        Assert.Contains("explicit-theme", result!.ToString()!);
    }

    [Fact]
    public void DuplicateResourceNames_FromProperties_ThrowsInvalidOperationException()
    {
        // Arrange
        var skill = new DuplicateResourcePropertiesSkill();

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => _ = skill.Resources);
        Assert.Contains("data", ex.Message);
        Assert.Contains("already has a resource", ex.Message);
    }

    [Fact]
    public void DuplicateResourceNames_FromPropertyAndMethod_ThrowsInvalidOperationException()
    {
        // Arrange
        var skill = new DuplicateResourcePropertyAndMethodSkill();

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => _ = skill.Resources);
        Assert.Contains("data", ex.Message);
        Assert.Contains("already has a resource", ex.Message);
    }

    [Fact]
    public void DuplicateResourceNames_FromMethods_ThrowsInvalidOperationException()
    {
        // Arrange
        var skill = new DuplicateResourceMethodsSkill();

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => _ = skill.Resources);
        Assert.Contains("data", ex.Message);
        Assert.Contains("already has a resource", ex.Message);
    }

    [Fact]
    public void DuplicateScriptNames_ThrowsInvalidOperationException()
    {
        // Arrange
        var skill = new DuplicateScriptsSkill();

        // Act & Assert
        var ex = Assert.Throws<InvalidOperationException>(() => _ = skill.Scripts);
        Assert.Contains("do-work", ex.Message);
        Assert.Contains("already has a script", ex.Message);
    }

    #region Test skill classes

    private sealed class MinimalClassSkill : AgentClassSkill<MinimalClassSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("minimal", "A minimal skill.");

        protected override string Instructions => "Minimal skill body.";
    }

    private sealed class FullClassSkill : AgentClassSkill<FullClassSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("full", "A full skill with resources and scripts.");

        protected override string Instructions => "Full skill body.";

        public override IReadOnlyList<AgentSkillResource>? Resources =>
        [
            this.CreateResource("test-resource", "resource content"),
        ];

        public override IReadOnlyList<AgentSkillScript>? Scripts =>
        [
            this.CreateScript("TestScript", TestScript),
        ];

        private static string TestScript(double value) =>
            JsonSerializer.Serialize(new { result = value * 2 });
    }

    private sealed class ResourceOnlySkill : AgentClassSkill<ResourceOnlySkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("resource-only", "Skill with resources only.");

        protected override string Instructions => "Body.";

        public override IReadOnlyList<AgentSkillResource>? Resources =>
        [
            this.CreateResource("data", "some data"),
        ];
    }

    private sealed class ScriptOnlySkill : AgentClassSkill<ScriptOnlySkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("script-only", "Skill with scripts only.");

        protected override string Instructions => "Body.";

        public override IReadOnlyList<AgentSkillScript>? Scripts =>
        [
            this.CreateScript("ToUpper", (string input) => input.ToUpperInvariant()),
        ];
    }

    private sealed class LazyLoadedSkill : AgentClassSkill<LazyLoadedSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("lazy-loaded", "Skill with lazily created resources and scripts.");

        protected override string Instructions => "Body.";

        public int ResourceCreationCount { get; private set; }

        public int ScriptCreationCount { get; private set; }

        private IReadOnlyList<AgentSkillResource>? _resources;
        private IReadOnlyList<AgentSkillScript>? _scripts;

        public override IReadOnlyList<AgentSkillResource>? Resources => this._resources ??= this.CreateResources();

        public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts ??= this.CreateScripts();

        private IReadOnlyList<AgentSkillResource> CreateResources()
        {
            this.ResourceCreationCount++;
            return [this.CreateResource("lazy-resource", "resource content")];
        }

        private IReadOnlyList<AgentSkillScript> CreateScripts()
        {
            this.ScriptCreationCount++;
            return [this.CreateScript("LazyScript", () => "done")];
        }
    }

    private sealed class CustomTypeSkill : AgentClassSkill<CustomTypeSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("custom-type-skill", "Skill with custom-typed scripts and resources.");

        protected override string Instructions => "Body.";

        public override IReadOnlyList<AgentSkillResource>? Resources =>
        [
            this.CreateResource("config", () => new SkillConfig
            {
                Theme = "dark",
                Verbose = true
            }, serializerOptions: SkillTestJsonContext.Default.Options),
        ];

        public override IReadOnlyList<AgentSkillScript>? Scripts =>
        [
            this.CreateScript("Lookup", (LookupRequest request) => new LookupResponse
            {
                Items = [$"result for {request.Query}"],
                TotalCount = request.MaxResults,
            }, serializerOptions: SkillTestJsonContext.Default.Options),
        ];
    }

#pragma warning disable IDE0051 // Remove unused private members
    private sealed class AttributedScriptsSkill : AgentClassSkill<AttributedScriptsSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("attributed-scripts", "Skill with various attributed scripts.");

        protected override string Instructions => "Body.";

        [AgentSkillScript("do-work")]
        private static string DoWork(string input) => input.ToUpperInvariant();

        [AgentSkillScript]
        private static string DefaultNamed(string input) => input.ToUpperInvariant();

        [AgentSkillScript("process")]
        [Description("Processes the input.")]
        private static string Process(string input) => input;

        [AgentSkillScript("append")]
        private string Append(string input) => input + "-suffix";
    }

    private sealed class AttributedResourcePropertiesSkill : AgentClassSkill<AttributedResourcePropertiesSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("attributed-resource-props", "Skill with various attributed resource properties.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("ref-data")]
        public string ReferenceData => "Reference content.";

        [AgentSkillResource]
        public string DefaultNamed => "Some data.";

        [AgentSkillResource("data")]
        [Description("Some important data.")]
        public string DescribedData => "content";

        [AgentSkillResource("static-data")]
        public static string StaticData => "Static content.";
    }

    private sealed class AttributedResourceMethodsSkill : AgentClassSkill<AttributedResourceMethodsSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("attributed-resource-methods", "Skill with various attributed resource methods.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("dynamic")]
        private static string GetDynamic() => "dynamic-value";

        [AgentSkillResource]
        private static string GetData() => "data";

        [AgentSkillResource("info")]
        [Description("Returns runtime info.")]
        private static string GetInfo() => "runtime-info";

        [AgentSkillResource("instance-dynamic")]
        private string GetValue() => "instance-method-value";
    }

    private sealed class AttributedFullSkill : AgentClassSkill<AttributedFullSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("attributed-full", "Full skill with attributed resources and scripts.");

        protected override string Instructions => "Convert units using the table.";

        [AgentSkillResource("conversion-table")]
        public string ConversionTable => "miles -> km: 1.60934";

        [AgentSkillScript("convert")]
        private static string Convert(double value, double factor) =>
            JsonSerializer.Serialize(new { result = value * factor });
    }

    private sealed class NoAttributesNoOverridesSkill : AgentClassSkill<NoAttributesNoOverridesSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("no-attrs", "Skill with no attributes or overrides.");

        protected override string Instructions => "Body.";
    }

    private sealed class AttributedWithOverrideSkill : AgentClassSkill<AttributedWithOverrideSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("attributed-override", "Skill with attributes and overrides.");

        protected override string Instructions => "Body.";

        // These attributes should be ignored because Resources/Scripts are overridden.
        [AgentSkillResource("ignored-resource")]
        public string IgnoredData => "ignored";

        [AgentSkillScript("ignored-script")]
        private static string IgnoredScript() => "ignored";

        public override IReadOnlyList<AgentSkillResource>? Resources =>
        [
            this.CreateResource("manual-resource", "manual content"),
        ];

        public override IReadOnlyList<AgentSkillScript>? Scripts =>
        [
            this.CreateScript("ManualScript", () => "manual result"),
        ];
    }

    private sealed class AttributedResourceDynamicPropertySkill : AgentClassSkill<AttributedResourceDynamicPropertySkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("attributed-resource-dynamic-prop", "Skill with dynamic property resource.");

        protected override string Instructions => "Body.";

        public int CallCount { get; private set; }

        [AgentSkillResource("counter")]
        public string Counter => $"call-{++this.CallCount}";
    }

    private sealed class AttributedSkillWithCustomSerializer : AgentClassSkill<AttributedSkillWithCustomSerializer>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("attributed-custom-jso", "Skill with custom serializer options.");

        protected override string Instructions => "Body.";

        protected override JsonSerializerOptions? SerializerOptions => SkillTestJsonContext.Default.Options;

        [AgentSkillResource("config")]
        public SkillConfig Config => new() { Theme = "light", Verbose = false };

        [AgentSkillScript("lookup")]
        private static LookupResponse Lookup(LookupRequest request) => new()
        {
            Items = [$"result for {request.Query}"],
            TotalCount = request.MaxResults,
        };
    }

    private sealed class MixedStaticInstanceSkill : AgentClassSkill<MixedStaticInstanceSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("mixed-static-instance", "Skill with both static and instance members.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("static-resource")]
        public static string StaticResource => "static-value";

        [AgentSkillResource("instance-resource")]
        public string InstanceResource => "instance-data";

        [AgentSkillScript("static-script")]
        private static string StaticScript() => "static-result";

        [AgentSkillScript("instance-script")]
        private string InstanceScript() => "instance-data";
    }

    private sealed class CreateMethodsFallbackSkill : AgentClassSkill<CreateMethodsFallbackSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("create-fallback", "Skill testing SerializerOptions fallback for CreateScript/CreateResource.");

        protected override string Instructions => "Body.";

        protected override JsonSerializerOptions? SerializerOptions => SkillTestJsonContext.Default.Options;

        public override IReadOnlyList<AgentSkillResource>? Resources =>
        [
            this.CreateResource("config", () => new SkillConfig
            {
                Theme = "dark",
                Verbose = true,
            }),
        ];

        public override IReadOnlyList<AgentSkillScript>? Scripts =>
        [
            this.CreateScript("Lookup", (LookupRequest request) => new LookupResponse
            {
                Items = [$"result for {request.Query}"],
                TotalCount = request.MaxResults,
            }),
        ];
    }

    private sealed class CreateMethodsExplicitJsoSkill : AgentClassSkill<CreateMethodsExplicitJsoSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("create-explicit-jso", "Skill testing explicit JSO overrides SerializerOptions.");

        protected override string Instructions => "Body.";

        // SerializerOptions is intentionally null — explicit JSO passed to CreateScript/CreateResource should be used.
        public override IReadOnlyList<AgentSkillResource>? Resources =>
        [
            this.CreateResource("config", () => new SkillConfig
            {
                Theme = "explicit-theme",
                Verbose = false,
            }, serializerOptions: SkillTestJsonContext.Default.Options),
        ];

        public override IReadOnlyList<AgentSkillScript>? Scripts =>
        [
            this.CreateScript("Lookup", (LookupRequest request) => new LookupResponse
            {
                Items = [$"result for {request.Query}"],
                TotalCount = request.MaxResults,
            }, serializerOptions: SkillTestJsonContext.Default.Options),
        ];
    }

    private sealed class IndexerResourceSkill : AgentClassSkill<IndexerResourceSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("indexer-skill", "Skill with indexer resource.");

        protected override string Instructions => "Body.";

        private readonly Dictionary<string, string> _data = new() { ["key"] = "value" };

        [AgentSkillResource("indexed")]
        public string this[string key] => this._data[key];
    }

    private sealed class UnsupportedParamResourceMethodSkill : AgentClassSkill<UnsupportedParamResourceMethodSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("unsupported-param-skill", "Skill with unsupported param resource method.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("bad-resource")]
        private static string GetData(string content) => content;
    }

    private sealed class ServiceProviderResourceMethodSkill : AgentClassSkill<ServiceProviderResourceMethodSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("sp-param-skill", "Skill with IServiceProvider param resource method.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("sp-resource")]
        private static string GetData(IServiceProvider? sp) => "from-sp-method";
    }

    private sealed class CancellationTokenResourceMethodSkill : AgentClassSkill<CancellationTokenResourceMethodSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("ct-param-skill", "Skill with CancellationToken param resource method.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("ct-resource")]
        private static string GetData(CancellationToken ct) => "from-ct-method";
    }

    private sealed class BothParamsResourceMethodSkill : AgentClassSkill<BothParamsResourceMethodSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("both-param-skill", "Skill with both IServiceProvider and CancellationToken param resource method.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("both-resource")]
        private static string GetData(IServiceProvider? sp, CancellationToken ct) => "from-both-method";
    }
    private sealed class DuplicateResourcePropertiesSkill : AgentClassSkill<DuplicateResourcePropertiesSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("dup-res-props", "Skill with duplicate resource property names.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("data")]
        public string Data1 => "value1";

        [AgentSkillResource("data")]
        public string Data2 => "value2";
    }

    private sealed class DuplicateResourcePropertyAndMethodSkill : AgentClassSkill<DuplicateResourcePropertyAndMethodSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("dup-res-prop-method", "Skill with duplicate resource from property and method.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("data")]
        public string Data => "property-value";

        [AgentSkillResource("data")]
        private static string GetData() => "method-value";
    }

    private sealed class DuplicateResourceMethodsSkill : AgentClassSkill<DuplicateResourceMethodsSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("dup-res-methods", "Skill with duplicate resource method names.");

        protected override string Instructions => "Body.";

        [AgentSkillResource("data")]
        private static string GetData1() => "value1";

        [AgentSkillResource("data")]
        private static string GetData2() => "value2";
    }

    private sealed class DuplicateScriptsSkill : AgentClassSkill<DuplicateScriptsSkill>
    {
        public override AgentSkillFrontmatter Frontmatter { get; } = new("dup-scripts", "Skill with duplicate script names.");

        protected override string Instructions => "Body.";

        [AgentSkillScript("do-work")]
        private static string DoWork1(string input) => input.ToUpperInvariant();

        [AgentSkillScript("do-work")]
        private static string DoWork2(string input) => input + "-suffix";
    }
#pragma warning restore IDE0051 // Remove unused private members

    #endregion
}
