// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

public sealed partial class AgentMcpSkillsTests
{
    [Fact]
    public async Task GetSkillsAsync_MixedManifestAndDynamicSkills_LoadsThroughProviderOnDemandAsync()
    {
        // Arrange
        JsonObject dynamicEntry = Entry("skill://dynamic/unit-converter/");
        dynamicEntry["resources"] = "dynamic";
        dynamicEntry["frontmatter"]!["description"] = "A dynamic skill.";
        List<string> reads = [];
        await using var server = CreateServer(
            (_, _) => ValueTask.FromResult<JsonNode?>(ListResult(Entry(), dynamicEntry)),
            (uri, _) =>
            {
                reads.Add(uri);
                return ValueTask.FromResult(Text(uri, uri.EndsWith("/SKILL.md", StringComparison.Ordinal)
                    ? SkillContent.Replace("Convert units.", "A dynamic skill.")
                    : "Dynamic reference."));
            });
        await using var client = await server.CreateClientAsync();
        using var source = new AgentMcpSkillsSource(client);
        IList<AgentSkill> skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        Assert.IsType<AgentMcpSkill>(skills[0]);
        var dynamicSkill = Assert.IsType<AgentMcpSkill>(skills[1]);
        using var provider = new AgentSkillsProvider(dynamicSkill);
        var context = await provider.InvokingAsync(
            new AIContextProvider.InvokingContext(TestAgentSkillsSourceContextFactory.Create().Agent, session: null, new AIContext()),
            CancellationToken.None);
        Assert.Empty(reads);
        var load = Assert.IsAssignableFrom<AIFunction>(Assert.Single(context.Tools!, tool => tool.Name == AgentSkillsProvider.LoadSkillToolName));
        var read = Assert.IsAssignableFrom<AIFunction>(Assert.Single(context.Tools!, tool => tool.Name == AgentSkillsProvider.ReadSkillResourceToolName));
        using var services = new ServiceCollection().BuildServiceProvider();

        // Act
        Assert.Null(await skills[0].GetResourceAsync("references/not-in-a-manifest.md"));
        object? instructions = await load.InvokeAsync(new AIFunctionArguments { ["skillName"] = "unit-converter" });
        object? resource = await read.InvokeAsync(new AIFunctionArguments(new Dictionary<string, object?>
        {
            ["skillName"] = "unit-converter",
            ["resourceName"] = "references/not-in-a-manifest.md",
        })
        { Services = services });

        // Assert
        Assert.Equal(SkillContent.Replace("Convert units.", "A dynamic skill."), instructions!.ToString());
        Assert.Equal("Dynamic reference.", resource!.ToString());
        Assert.Equal(["skill://dynamic/unit-converter/SKILL.md", "skill://dynamic/unit-converter/references/not-in-a-manifest.md"], reads);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GetSkillsAsync_MetadataRefresh_CanSwitchResourceModesAsync(bool startDynamic)
    {
        // Arrange
        var clock = new ManualTimeProvider();
        int gets = 0;
        List<string> methods = [];
        JsonObject CreateEntry(bool dynamic)
        {
            JsonObject entry = Entry();
            if (dynamic)
            {
                entry["resources"] = "dynamic";
            }

            return entry;
        }

        var client = CreateTtlClient((request, _) =>
        {
            methods.Add(request.Method);
            return Task.FromResult(request.Method switch
            {
                "skills/list" => TtlListResult(60000, CreateEntry(false)),
                "skills/get" => GetSkillResult(CreateEntry(++gets == 1 ? startDynamic : !startDynamic), 1000),
                "resources/read" => ResourceReadResult(SkillUri, 0, SkillContent + "\nChanged."),
                _ => throw new InvalidOperationException(request.Method),
            });
        });
        var catalog = new McpSkillsCatalog(client.Object, timeProvider: clock);
        var original = Assert.IsType<AgentMcpSkill>(Assert.Single(await catalog.GetSkillsAsync(CancellationToken.None)));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await original.GetContentAsync());
        var first = Assert.IsType<AgentMcpSkill>(Assert.Single(await catalog.GetSkillsAsync(CancellationToken.None)));

        // Act
        clock.Advance(TimeSpan.FromMilliseconds(999));
        Assert.Same(first, Assert.Single(await catalog.GetSkillsAsync(CancellationToken.None)));
        clock.Advance(TimeSpan.FromMilliseconds(1));
        var second = Assert.IsType<AgentMcpSkill>(Assert.Single(await catalog.GetSkillsAsync(CancellationToken.None)));

        // Assert
        Assert.NotSame(first, second);
        if (startDynamic)
        {
            Assert.Equal(SkillContent + "\nChanged.", await first.GetContentAsync());
            await Assert.ThrowsAsync<InvalidOperationException>(async () => await second.GetContentAsync());
        }
        else
        {
            await Assert.ThrowsAsync<InvalidOperationException>(async () => await first.GetContentAsync());
            Assert.Equal(SkillContent + "\nChanged.", await second.GetContentAsync());
        }

        Assert.Equal(["skills/list", "resources/read", "skills/get", "skills/get", "resources/read", "resources/read"], methods);
    }
}
