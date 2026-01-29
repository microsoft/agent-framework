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

    private static readonly AnthropicConfiguration s_config = TestConfiguration.LoadSection<AnthropicConfiguration>();

    [Fact(Skip = SkipReason)]
    public async Task CreateAgentWithPptxSkillAsync()
    {
        // Arrange
        AnthropicClient anthropicClient = new() { APIKey = s_config.ApiKey };
        string model = s_config.ChatModelId;

        // Define the pptx skill configuration once to avoid duplication
        BetaSkillParams pptxSkill = new()
        {
            Type = BetaSkillParamsType.Anthropic,
            SkillID = "pptx",
            Version = "latest"
        };

        // Create an agent with the pptx skill using AsAITool extension method
        ChatClientAgent agent = anthropicClient.Beta.AsAIAgent(
            model: model,
            instructions: "You are a helpful agent for creating PowerPoint presentations.",
            tools: [pptxSkill.AsAITool()],
            clientFactory: (chatClient) => chatClient
                .AsBuilder()
                .ConfigureOptions(
                    options => options.RawRepresentationFactory = (_) => new MessageCreateParams()
                    {
                        Model = options.ModelId ?? model,
                        MaxTokens = options.MaxOutputTokens ?? 20000,
                        Messages = [],
                        Thinking = new BetaThinkingConfigParam(new BetaThinkingConfigEnabled(budgetTokens: 10000)),
                        Betas = [AnthropicBeta.Skills2025_10_02],
                        Container = new BetaContainerParams() { Skills = [pptxSkill] }
                    })
                .Build());

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
        AnthropicClient anthropicClient = new() { APIKey = s_config.ApiKey };

        // Act - List available Anthropic-managed skills
        SkillListPageResponse skills = await anthropicClient.Beta.Skills.List(
            new SkillListParams { Source = "anthropic", Betas = [AnthropicBeta.Skills2025_10_02] });

        // Assert
        Assert.NotNull(skills);
        Assert.NotNull(skills.Data);

        // Check that the pptx skill is available
        bool hasPptxSkill = false;
        foreach (var skill in skills.Data)
        {
            if (skill.ID == "pptx")
            {
                hasPptxSkill = true;
                break;
            }
        }

        Assert.True(hasPptxSkill, "Expected pptx skill to be available");
    }
}
