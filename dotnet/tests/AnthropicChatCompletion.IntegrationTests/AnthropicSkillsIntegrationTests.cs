// Copyright (c) Microsoft. All rights reserved.

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
public sealed class AnthropicSkillsIntegrationTests
{
    // All tests for Anthropic are intended to be ran locally as the CI pipeline for Anthropic is not setup.
    private const string SkipReason = "Integrations tests for local execution only";

    [Fact(Skip = SkipReason)]
    public async Task CreateAgentWithPptxSkillAsync()
    {
        // Arrange
        AnthropicClient anthropicClient = new() { ApiKey = TestConfiguration.GetRequiredValue(TestSettings.AnthropicApiKey) };
        string model = TestConfiguration.GetRequiredValue(TestSettings.AnthropicChatModelName);

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

    [Fact(Skip = SkipReason)]
    public async Task ListAnthropicManagedSkillsAsync()
    {
        // Arrange
        AnthropicClient anthropicClient = new() { ApiKey = TestConfiguration.GetRequiredValue(TestSettings.AnthropicApiKey) };

        // Act
        SkillListPage skills = await anthropicClient.Beta.Skills.List(
            new SkillListParams { Source = "anthropic", Betas = [AnthropicBeta.Skills2025_10_02] });

        // Assert
        Assert.NotNull(skills);
        Assert.NotNull(skills.Items);
        Assert.Contains(skills.Items, skill => skill.ID == "pptx");
    }
}
