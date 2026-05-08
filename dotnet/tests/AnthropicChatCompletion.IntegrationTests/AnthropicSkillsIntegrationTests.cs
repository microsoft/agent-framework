// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using AgentConformance.IntegrationTests.Support;
using Anthropic;
using Anthropic.Models.Beta;
using Anthropic.Models.Beta.Messages;
using Anthropic.Models.Beta.Skills;
using Anthropic.Services;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Shared.IntegrationTests;

namespace AnthropicChatCompletion.IntegrationTests;

/// <summary>
/// Integration tests for Anthropic Skills functionality.
/// These tests are designed to be run locally with a valid Anthropic API key.
/// </summary>
/// <remarks>
/// Temporarily disabled due to Anthropic SDK binary incompatibility with
/// the current Microsoft.Extensions.AI version (WebSearchToolResultContent.Results).
/// </remarks>
[Trait("Category", "IntegrationDisabled")]
public sealed class AnthropicSkillsIntegrationTests
{
    [Fact]
    public async Task CreateAgentWithPptxSkillAsync()
    {
        AnthropicClient? anthropicClient;
        string? model;
        try
        {
            anthropicClient = new() { ApiKey = TestConfiguration.GetRequiredValue(TestSettings.AnthropicApiKey) };
            model = TestConfiguration.GetRequiredValue(TestSettings.AnthropicChatModelName);
        }
        catch (InvalidOperationException ex)
        {
            Assert.Skip("Anthropic configuration could not be loaded. Error:" + ex.Message);
            return;
        }

        BetaSkillParams pptxSkill = new()
        {
            Type = BetaSkillParamsType.Anthropic,
            SkillID = "pptx",
            Version = "latest"
        };

        ChatClientAgent agent = anthropicClient.Beta.AsAIAgent(
            model: model,
            instructions: "You are a helpful agent for creating PowerPoint presentations.",
            tools: [pptxSkill.AsAITool()]);

        // Act
        AgentResponse response = await agent.RunAsync(
            "Create a simple 2-slide presentation: a title slide and one content slide about AI.");

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Text);
        Assert.NotEmpty(response.Text);
    }

    [Fact]
    public async Task ListAnthropicManagedSkillsAsync()
    {
        AnthropicClient? anthropicClient;
        try
        {
            anthropicClient = new() { ApiKey = TestConfiguration.GetRequiredValue(TestSettings.AnthropicApiKey) };
        }
        catch (InvalidOperationException ex)
        {
            Assert.Skip("Anthropic configuration could not be loaded. Error:" + ex.Message);
            return;
        }

        // Act
        SkillListPage skills = await anthropicClient.Beta.Skills.List(
            new SkillListParams { Source = "anthropic", Betas = [AnthropicBeta.Skills2025_10_02] });

        // Assert
        Assert.NotNull(skills);
        Assert.NotNull(skills.Items);
        Assert.Contains(skills.Items, skill => skill.ID == "pptx");
    }
}
