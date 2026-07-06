// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentInlineSkillContentBuilder"/>, focusing on the structure of the
/// emitted <c>&lt;available_resources&gt;</c> and <c>&lt;available_scripts&gt;</c> blocks.
/// </summary>
public sealed class AgentInlineSkillContentBuilderTests
{
    [Fact]
    public void Build_NullResourcesAndScripts_EmitsSelfClosingTags()
    {
        // Act
        var content = AgentInlineSkillContentBuilder.Build("my-skill", "A skill.", "Instructions.", resources: null, scripts: null);

        // Assert — explicit empty elements signal "none available" so the model does not hallucinate names
        Assert.Contains("<available_resources />", content);
        Assert.Contains("<available_scripts />", content);
        Assert.DoesNotContain("<available_resources>", content);
        Assert.DoesNotContain("<available_scripts>", content);
    }

    [Fact]
    public void Build_EmptyResourcesAndScripts_EmitsSelfClosingTags()
    {
        // Act
        var content = AgentInlineSkillContentBuilder.Build(
            "my-skill",
            "A skill.",
            "Instructions.",
            resources: Array.Empty<AgentSkillResource>(),
            scripts: Array.Empty<AgentSkillScript>());

        // Assert
        Assert.Contains("<available_resources />", content);
        Assert.Contains("<available_scripts />", content);
    }

    [Fact]
    public void Build_ResourcesOnly_EmitsResourceEntriesAndSelfClosingScripts()
    {
        // Arrange
        var resources = new AgentSkillResource[]
        {
            new AgentInlineSkillResource("config", "value", "A described resource."),
            new AgentInlineSkillResource("table", "value"),
        };

        // Act
        var content = AgentInlineSkillContentBuilder.Build("my-skill", "A skill.", "Instructions.", resources, scripts: null);

        // Assert — resources are listed by name with optional description, scripts are an empty element
        Assert.Contains("<available_resources>", content);
        Assert.Contains("<resource name=\"config\" description=\"A described resource.\"/>", content);
        Assert.Contains("<resource name=\"table\"/>", content);
        Assert.Contains("</available_resources>", content);
        Assert.Contains("<available_scripts />", content);
    }

    [Fact]
    public void Build_ScriptsOnly_EmitsSelfClosingResourcesAndScriptsBlock()
    {
        // Arrange
        var scripts = new AgentSkillScript[] { new FakeScript("run", ParseSchema("{\"type\":\"object\"}")) };

        // Act
        var content = AgentInlineSkillContentBuilder.Build("my-skill", "A skill.", "Instructions.", resources: null, scripts);

        // Assert
        Assert.Contains("<available_resources />", content);
        Assert.Contains("<available_scripts>", content);
        Assert.Contains("<script name=\"run\">", content);
        Assert.Contains("</available_scripts>", content);
    }

    [Fact]
    public void Build_MultipleResources_RendersAllInRegistrationOrder()
    {
        // Arrange
        var resources = new AgentSkillResource[]
        {
            new AgentInlineSkillResource("first", "v"),
            new AgentInlineSkillResource("second", "v"),
            new AgentInlineSkillResource("third", "v"),
        };

        // Act
        var content = AgentInlineSkillContentBuilder.Build("my-skill", "A skill.", "Instructions.", resources, scripts: null);

        // Assert — order is preserved
        var firstIndex = content.IndexOf("first", StringComparison.Ordinal);
        var secondIndex = content.IndexOf("second", StringComparison.Ordinal);
        var thirdIndex = content.IndexOf("third", StringComparison.Ordinal);
        Assert.True(firstIndex < secondIndex && secondIndex < thirdIndex);
    }

    [Fact]
    public void Build_ResourceNameWithSpecialCharacters_IsXmlEscaped()
    {
        // Arrange
        var resources = new AgentSkillResource[] { new AgentInlineSkillResource("a<b>&\"c", "v") };

        // Act
        var content = AgentInlineSkillContentBuilder.Build("my-skill", "A skill.", "Instructions.", resources, scripts: null);

        // Assert — XML special characters in the name are escaped
        Assert.Contains("<resource name=\"a&lt;b&gt;&amp;&quot;c\"/>", content);
    }

    [Fact]
    public void BuildAvailableResourcesBlock_EmptyList_ReturnsSelfClosingElement()
    {
        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableResourcesBlock(Array.Empty<AgentSkillResource>());

        // Assert — empty list yields a self-closing element so the model knows none are available
        Assert.Equal("\n<available_resources />", block);
    }

    [Fact]
    public void BuildAvailableResourcesBlock_WithResources_EmitsDescriptionWhenPresent()
    {
        // Arrange
        var resources = new AgentSkillResource[]
        {
            new AgentInlineSkillResource("config", "value", "A described resource."),
            new AgentInlineSkillResource("table", "value"),
        };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableResourcesBlock(resources);

        // Assert — resources with description include it as an attribute; those without omit it
        Assert.Contains("<available_resources>", block);
        Assert.Contains("<resource name=\"config\" description=\"A described resource.\"/>", block);
        Assert.Contains("<resource name=\"table\"/>", block);
        Assert.Contains("</available_resources>", block);
    }

    [Fact]
    public void BuildAvailableResourcesBlock_ResourceDescriptionWithSpecialCharacters_IsXmlEscaped()
    {
        // Arrange
        var resources = new AgentSkillResource[] { new AgentInlineSkillResource("cfg", "v", "has <special> & \"chars\"") };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableResourcesBlock(resources);

        // Assert
        Assert.Contains("description=\"has &lt;special&gt; &amp; &quot;chars&quot;\"", block);
    }

    [Fact]
    public void BuildAvailableResourcesBlock_ResourceWithEmptyDescription_OmitsDescriptionAttribute()
    {
        // Arrange
        var resources = new AgentSkillResource[] { new AgentInlineSkillResource("config", "value", string.Empty) };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableResourcesBlock(resources);

        // Assert
        Assert.Contains("<resource name=\"config\"/>", block);
        Assert.DoesNotContain("description=", block);
    }

    [Fact]
    public void BuildAvailableResourcesBlock_ResourceWithWhitespaceDescription_OmitsDescriptionAttribute()
    {
        // Arrange
        var resources = new AgentSkillResource[] { new AgentInlineSkillResource("config", "value", "   ") };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableResourcesBlock(resources);

        // Assert
        Assert.Contains("<resource name=\"config\"/>", block);
        Assert.DoesNotContain("description=", block);
    }

    [Fact]
    public void BuildAvailableResourcesBlock_ResourceNameWithSpecialCharacters_IsXmlEscaped()
    {
        // Arrange
        var resources = new AgentSkillResource[] { new AgentInlineSkillResource("a<b>&\"c", "v") };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableResourcesBlock(resources);

        // Assert
        Assert.Contains("<resource name=\"a&lt;b&gt;&amp;&quot;c\"/>", block);
    }

    [Fact]
    public void BuildAvailableResourcesBlock_NullResources_Throws() =>
        Assert.Throws<ArgumentNullException>(() => AgentInlineSkillContentBuilder.BuildAvailableResourcesBlock(null!));

    [Fact]
    public void BuildAvailableScriptsBlock_EmptyList_ReturnsSelfClosingElement()
    {
        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(Array.Empty<AgentSkillScript>());

        // Assert — empty list yields a self-closing element so the model knows none are available
        Assert.Equal("\n<available_scripts />", block);
    }

    [Fact]
    public void BuildAvailableScriptsBlock_ScriptWithoutSchema_UsesSelfClosingScript()
    {
        // Arrange — a script whose ParametersSchema is null and has no description
        var scripts = new AgentSkillScript[] { new FakeScript("no-params", parametersSchema: null) };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(scripts);

        // Assert — self-closing <script> element with no nested parameters_schema
        Assert.Contains("<script name=\"no-params\"/>", block);
        Assert.DoesNotContain("<parameters_schema>", block);
    }

    [Fact]
    public void BuildAvailableScriptsBlock_ScriptWithDescription_EmitsDescriptionAttribute()
    {
        // Arrange — a script with a description but no schema
        var scripts = new AgentSkillScript[] { new FakeScript("deploy", parametersSchema: null, description: "Deploy the app.") };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(scripts);

        // Assert — description attribute is included
        Assert.Contains("<script name=\"deploy\" description=\"Deploy the app.\"/>", block);
    }

    [Fact]
    public void BuildAvailableScriptsBlock_ScriptDescriptionWithSpecialCharacters_IsXmlEscaped()
    {
        // Arrange
        var scripts = new AgentSkillScript[] { new FakeScript("deploy", parametersSchema: null, description: "has <special> & \"chars\"") };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(scripts);

        // Assert
        Assert.Contains("description=\"has &lt;special&gt; &amp; &quot;chars&quot;\"", block);
    }

    [Fact]
    public void BuildAvailableScriptsBlock_ScriptWithEmptyDescription_OmitsDescriptionAttribute()
    {
        // Arrange
        var scripts = new AgentSkillScript[] { new FakeScript("deploy", parametersSchema: null, description: string.Empty) };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(scripts);

        // Assert
        Assert.Contains("<script name=\"deploy\"/>", block);
        Assert.DoesNotContain("description=", block);
    }

    [Fact]
    public void BuildAvailableScriptsBlock_ScriptWithWhitespaceDescription_OmitsDescriptionAttribute()
    {
        // Arrange
        var scripts = new AgentSkillScript[] { new FakeScript("deploy", parametersSchema: null, description: "   ") };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(scripts);

        // Assert
        Assert.Contains("<script name=\"deploy\"/>", block);
        Assert.DoesNotContain("description=", block);
    }

    [Fact]
    public void BuildAvailableScriptsBlock_ScriptWithDescriptionAndSchema_EmitsDescriptionAttribute()
    {
        // Arrange — a script with both description and schema
        var scripts = new AgentSkillScript[] { new FakeScript("search", ParseSchema("{\"type\":\"object\"}"), description: "Search something.") };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(scripts);

        // Assert — description attribute is on the opening tag, schema is nested
        Assert.Contains("<script name=\"search\" description=\"Search something.\">", block);
        Assert.Contains("<parameters_schema>", block);
    }

    [Fact]
    public void BuildAvailableScriptsBlock_ScriptWithSchema_WrapsSchemaInParametersSchemaElement()
    {
        // Arrange
        var scripts = new AgentSkillScript[] { new FakeScript("search", ParseSchema("{\"type\":\"object\",\"properties\":{\"query\":{\"type\":\"string\"}}}")) };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(scripts);

        // Assert — schema is wrapped in <parameters_schema> with preserved quotes (no CDATA)
        Assert.Contains("<script name=\"search\">", block);
        Assert.Contains("<parameters_schema>", block);
        Assert.Contains("\"query\"", block);
        Assert.Contains("</parameters_schema>", block);
        Assert.Contains("</script>", block);
        Assert.DoesNotContain("<![CDATA[", block);
    }

    [Fact]
    public void BuildAvailableScriptsBlock_ScriptNameWithSpecialCharacters_IsXmlEscaped()
    {
        // Arrange
        var scripts = new AgentSkillScript[] { new FakeScript("a<b>&\"c", parametersSchema: null) };

        // Act
        var block = AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(scripts);

        // Assert
        Assert.Contains("<script name=\"a&lt;b&gt;&amp;&quot;c\"/>", block);
    }

    [Fact]
    public void BuildAvailableScriptsBlock_NullScripts_Throws() =>
        Assert.Throws<ArgumentNullException>(() => AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(null!));

    private static JsonElement ParseSchema(string json) => JsonDocument.Parse(json).RootElement.Clone();

    private sealed class FakeScript : AgentSkillScript
    {
        private readonly JsonElement? _parametersSchema;

        public FakeScript(string name, JsonElement? parametersSchema, string? description = null)
            : base(name, description)
        {
            this._parametersSchema = parametersSchema;
        }

        public override JsonElement? ParametersSchema => this._parametersSchema;

        public override Task<object?> RunAsync(AgentSkill skill, JsonElement? arguments, IServiceProvider? serviceProvider, CancellationToken cancellationToken = default) =>
            Task.FromResult<object?>(null);
    }
}
