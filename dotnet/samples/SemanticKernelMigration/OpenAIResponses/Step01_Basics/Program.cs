// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;
using Microsoft.SemanticKernel.Agents.OpenAI;
using OpenAI;

#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY") ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var modelId = System.Environment.GetEnvironmentVariable("OPENAI_MODELID") ?? "gpt-4o";
var userInput = "Tell me a joke about a pirate.";

Console.WriteLine($"User Input: {userInput}");

await SKAgentAsync();
await AFAgentAsync();

async Task SKAgentAsync()
{
    Console.WriteLine("\n=== SK Agent ===\n");

    OpenAIResponseAgent agent = new(new OpenAIClient(apiKey).GetOpenAIResponseClient(modelId))
    {
        Name = "Joker",
        Instructions = "You are good at telling jokes.",
    };

    var agentOptions = new OpenAIResponseAgentInvokeOptions() { ResponseCreationOptions = new() { MaxOutputTokenCount = 1000 } };

    Microsoft.SemanticKernel.Agents.AgentThread? thread = null;
    await foreach (var item in agent.InvokeAsync(userInput, thread, agentOptions))
    {
        Console.WriteLine(item.Message);
    }

    Console.WriteLine("---");
    await foreach (var item in agent.InvokeStreamingAsync(userInput, thread, agentOptions))
    {
        // Thread need to be updated for subsequent calls
        thread = item.Thread;
        Console.Write(item.Message);
    }
}

async Task AFAgentAsync()
{
    Console.WriteLine("\n=== AF Agent ===\n");

    var agent = new OpenAIClient(apiKey).GetOpenAIResponseClient(modelId)
        .CreateAIAgent(name: "Joker", instructions: "You are good at telling jokes.");

    var thread = agent.GetNewThread();
    var agentOptions = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 8000 });

    var result = await agent.RunAsync(userInput, thread, agentOptions);
    Console.WriteLine(result);

    Console.WriteLine("---");
    await foreach (var update in agent.RunStreamingAsync(userInput, thread, agentOptions))
    {
        Console.Write(update);
    }
}
