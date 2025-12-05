// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use an AI agent with reasoning capabilities.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-5";

var client = new OpenAIClient(apiKey)
        .GetOpenAIResponseClient(model)
        .AsIChatClient().AsBuilder()
        .ConfigureOptions(o =>
        {
            o.RawRepresentationFactory = _ => new ResponseCreationOptions()
            {
                ReasoningOptions = new()
                {
                    ReasoningEffortLevel = ResponseReasoningEffortLevel.Medium,
                    // Verbosity requires OpenAI verified Organization
                    ReasoningSummaryVerbosity = ResponseReasoningSummaryVerbosity.Detailed
                }
            };
        }).Build();

AIAgent agent = new ChatClientAgent(client);

Console.WriteLine("1. Non-streaming:");
var response = await agent.RunAsync("Solve this problem step by step: If a train travels 60 miles per hour and needs to cover 180 miles, how long will the journey take? Show your reasoning.");

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
            Console.Write($"\e[97m{reasoningContent.Text}\e[0m");
        }
        else if (item is TextContent textContent)
        {
            Console.Write(textContent.Text);
        }
    }
}
