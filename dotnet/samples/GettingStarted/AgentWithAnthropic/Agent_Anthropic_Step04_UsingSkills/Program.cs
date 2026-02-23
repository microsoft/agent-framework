// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use Anthropic-managed Skills with an AI agent.
// Skills are pre-built capabilities provided by Anthropic that can be used with the Claude API.
// This sample shows how to:
// 1. List available Anthropic-managed skills
// 2. Use the pptx skill to create PowerPoint presentations
// 3. Download and save generated files

using Anthropic;
using Anthropic.Core;
using Anthropic.Models.Beta;
using Anthropic.Models.Beta.Files;
using Anthropic.Models.Beta.Messages;
using Anthropic.Models.Beta.Skills;
using Anthropic.Services;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is not set.");
// Skills require Claude 4.5 models (Sonnet 4.5, Haiku 4.5, or Opus 4.5)
string model = Environment.GetEnvironmentVariable("ANTHROPIC_MODEL") ?? "claude-sonnet-4-5-20250929";

// Create the Anthropic client
AnthropicClient anthropicClient = new() { ApiKey = apiKey };

// List available Anthropic-managed skills (optional - API may not be available in all regions)
Console.WriteLine("Available Anthropic-managed skills:");
try
{
    SkillListPage skills = await anthropicClient.Beta.Skills.List(
        new SkillListParams { Source = "anthropic", Betas = [AnthropicBeta.Skills2025_10_02] });

    foreach (var skill in skills.Items)
    {
        Console.WriteLine($"  {skill.Source}: {skill.ID} (version: {skill.LatestVersion})");
    }
}
catch (Exception ex)
{
    Console.WriteLine($"  (Skills listing not available: {ex.Message})");
}

Console.WriteLine();

// Define the pptx skill - the SDK handles all beta flags and container configuration automatically
// when using AsAITool(), so no manual RawRepresentationFactory configuration is needed.
BetaSkillParams pptxSkill = new()
{
    Type = BetaSkillParamsType.Anthropic,
    SkillID = "pptx",
    Version = "latest"
};

// Create an agent with the pptx skill enabled.
// Skills require extended thinking and higher max tokens for complex file generation.
// The SDK's AsAITool() handles beta flags and container config automatically.
ChatClientAgent agent = anthropicClient.Beta.AsAIAgent(
    model: model,
    instructions: "You are a helpful agent for creating PowerPoint presentations.",
    tools: [pptxSkill.AsAITool()],
    clientFactory: (chatClient) => chatClient
        .AsBuilder()
        .ConfigureOptions(options =>
        {
            options.RawRepresentationFactory = (_) => new MessageCreateParams()
            {
                Model = model,
                MaxTokens = 20000,
                Messages = [],
                Thinking = new BetaThinkingConfigParam(
                    new BetaThinkingConfigEnabled(budgetTokens: 10000))
            };
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

// Collect generated files from CodeInterpreterToolResultContent outputs
List<HostedFileContent> hostedFiles = response.Messages
    .SelectMany(m => m.Contents.OfType<CodeInterpreterToolResultContent>())
    .Where(c => c.Outputs is not null)
    .SelectMany(c => c.Outputs!.OfType<HostedFileContent>())
    .ToList();

if (hostedFiles.Count > 0)
{
    Console.WriteLine("\n#### Generated Files ####");
    foreach (HostedFileContent file in hostedFiles)
    {
        Console.WriteLine($"  FileId: {file.FileId}");

        // Download the file using the Anthropic Files API
        using HttpResponse fileResponse = await anthropicClient.Beta.Files.Download(
            file.FileId,
            new FileDownloadParams { Betas = ["files-api-2025-04-14"] });

        // Save the file to disk
        string fileName = $"presentation_{file.FileId.Substring(0, 8)}.pptx";
        using FileStream fileStream = File.Create(fileName);
        Stream contentStream = await fileResponse.ReadAsStream();
        await contentStream.CopyToAsync(fileStream);

        Console.WriteLine($"  Saved to: {fileName}");
    }
}

Console.WriteLine("\nToken usage:");
Console.WriteLine($"Input: {response.Usage?.InputTokenCount}, Output: {response.Usage?.OutputTokenCount}");
if (response.Usage?.AdditionalCounts is not null)
{
    Console.WriteLine($"Additional: {string.Join(", ", response.Usage.AdditionalCounts)}");
}
