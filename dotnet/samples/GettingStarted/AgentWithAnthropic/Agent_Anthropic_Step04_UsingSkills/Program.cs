// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Anthropic-managed Skills with an AI agent.
// Skills are pre-built capabilities provided by Anthropic that can be used with the Claude API.
// This sample shows how to use the pptx skill to create PowerPoint presentations.

using Anthropic;
using Anthropic.Models.Beta;
using Anthropic.Models.Beta.Messages;
using Anthropic.Services;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is not set.");
string model = Environment.GetEnvironmentVariable("ANTHROPIC_MODEL") ?? "claude-sonnet-4-20250514";

// Define the pptx skill configuration once to avoid duplication
BetaSkillParams pptxSkill = new()
{
    Type = BetaSkillParamsType.Anthropic,
    SkillID = "pptx",
    Version = "latest"
};

// Create an agent with the pptx skill enabled using the AsAITool extension method.
// Skills require the beta API and specific beta flags to be enabled.
AIAgent agent = new AnthropicClient { APIKey = apiKey }
    .Beta
    .AsAIAgent(
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
                    // Enable extended thinking for better reasoning when creating presentations
                    Thinking = new BetaThinkingConfigParam(new BetaThinkingConfigEnabled(budgetTokens: 10000)),
                    // Enable the skills-2025-10-02 beta flag for skills support
                    Betas = [AnthropicBeta.Skills2025_10_02],
                    // Configure the container with the pptx skill
                    Container = new BetaContainerParams() { Skills = [pptxSkill] }
                })
            .Build());

Console.WriteLine("Creating a presentation about renewable energy...\n");

// Run the agent with a request to create a presentation
AgentResponse response = await agent.RunAsync("Create a simple 3-slide presentation about renewable energy sources. Include a title slide, a slide about solar energy, and a slide about wind energy.");

Console.WriteLine("#### Agent Response ####");
Console.WriteLine(response.Text);

// Display any reasoning/thinking content
List<TextReasoningContent> reasoningContents = response.Messages.SelectMany(m => m.Contents.OfType<TextReasoningContent>()).ToList();
if (reasoningContents.Count > 0)
{
    Console.WriteLine("\n#### Agent Reasoning ####");
    Console.WriteLine($"\e[92m{string.Join("\n", reasoningContents.Select(c => c.Text))}\e[0m");
}

// Display any hosted file content that was generated
List<DataContent> dataContents = response.Messages.SelectMany(m => m.Contents.OfType<DataContent>()).ToList();
if (dataContents.Count > 0)
{
    Console.WriteLine("\n#### Generated Files ####");
    foreach (DataContent content in dataContents)
    {
        Console.WriteLine($"- MediaType: {content.MediaType}, HasData: {!content.Data.IsEmpty}");
    }
}

Console.WriteLine("\nToken usage:");
Console.WriteLine($"Input: {response.Usage?.InputTokenCount}, Output: {response.Usage?.OutputTokenCount}");
if (response.Usage?.AdditionalCounts is not null)
{
    Console.WriteLine($"Additional: {string.Join(", ", response.Usage.AdditionalCounts)}");
}
