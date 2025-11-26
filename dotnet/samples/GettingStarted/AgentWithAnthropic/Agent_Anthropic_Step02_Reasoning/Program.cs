// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an AI agent with reasoning capabilities.

using Anthropic;
using Anthropic.Core;
using Anthropic.Models.Messages;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

var apiKey = Environment.GetEnvironmentVariable("ANTHROPIC_API_KEY") ?? throw new InvalidOperationException("ANTHROPIC_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("ANTHROPIC_MODEL") ?? "claude-haiku-4-5";
var maxTokens = 4096;
var thinkingTokens = 2048;

var agent = new AnthropicClient(new ClientOptions { APIKey = apiKey })
    .CreateAIAgent(
        model: model,
        clientFactory: (chatClient) => chatClient
            .AsBuilder()
            .ConfigureOptions(
                options => options.RawRepresentationFactory = (_) => new MessageCreateParams()
                {
                    Model = options.ModelId ?? model,
                    MaxTokens = options.MaxOutputTokens ?? maxTokens,
                    Messages = [],
                    Thinking = new ThinkingConfigParam(new ThinkingConfigEnabled(budgetTokens: thinkingTokens))
                })
            .Build());

Console.WriteLine("1. Non-streaming:");
var response = await agent.RunAsync("Solve this problem step by step: If a train travels 60 miles per hour and needs to cover 180 miles, how long will the journey take? Show your reasoning.");

Console.WriteLine("#### Start Thinking ####");
Console.WriteLine($"\e[92m{string.Join("\n", response.Messages.SelectMany(m => m.Contents.OfType<TextReasoningContent>().Select(c => c.Text)))}\e[0m");
Console.WriteLine("#### End Thinking ####");

Console.WriteLine("\n#### Final Answer ####");
Console.WriteLine(response.Text);

Console.WriteLine("Token usage:");
Console.WriteLine($"Input: {response.Usage?.InputTokenCount}, Output: {response.Usage?.OutputTokenCount}, {string.Join(", ", response.Usage?.AdditionalCounts ?? [])}");
Console.WriteLine();

Console.WriteLine("2. Streaming");
await foreach (var update in agent.RunStreamingAsync("Explain the theory of relativity in simple terms."))
{
    foreach (var item in update.Contents)
    {
        if (item is TextReasoningContent reasoningContent)
        {
            Console.WriteLine($"\e[92m{reasoningContent.Text}\e[0m");
        }
        else if (item is TextContent textContent)
        {
            Console.WriteLine(textContent.Text);
        }
    }
}
