// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents.OpenAI;
using Microsoft.SemanticKernel.Connectors.OpenAI;
using OpenAI;
using OpenAI.Assistants;

var endpoint = Environment.GetEnvironmentVariable("AZUREOPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZUREOPENAI_ENDPOINT is not set.");
var deploymentName = System.Environment.GetEnvironmentVariable("AZUREOPENAI_DEPLOYMENT_NAME") ?? "gpt-4o";
var userInput = "What is the weather like in Amsterdam?";

[KernelFunction]
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

Console.WriteLine($"User Input: {userInput}");

await SKAgent();
await AFAgent();

async Task SKAgent()
{
    Console.WriteLine("\n=== SK Agent ===\n");

    var builder = Kernel.CreateBuilder();
    var assistantsClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetAssistantClient();

    Assistant assistant = await assistantsClient.CreateAssistantAsync(deploymentName,
        instructions: "You are a helpful assistant");

    OpenAIAssistantAgent agent = new(assistant, assistantsClient)
    {
        Kernel = builder.Build(),
        Arguments = new KernelArguments(new OpenAIPromptExecutionSettings()
        {
            MaxTokens = 1000,
            FunctionChoiceBehavior = FunctionChoiceBehavior.Auto()
        }),
    };

    // Initialize plugin and add to the agent's Kernel (same as direct Kernel usage).
    agent.Kernel.Plugins.Add(KernelPluginFactory.CreateFromFunctions("KernelPluginName", [KernelFunctionFactory.CreateFromMethod(GetWeather)]));

    // Create a thread for the agent conversation.
    var thread = new OpenAIAssistantAgentThread(assistantsClient);

    await foreach (var result in agent.InvokeAsync(userInput, thread))
    {
        Console.WriteLine(result.Message);
    }

    Console.WriteLine("---");
    await foreach (var update in agent.InvokeStreamingAsync(userInput, thread))
    {
        Console.Write(update.Message);
    }

    // Clean up
    await thread.DeleteAsync();
    await assistantsClient.DeleteAssistantAsync(agent.Id);
}

async Task AFAgent()
{
    Console.WriteLine("\n=== AF Agent ===\n");

    var assistantClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetAssistantClient();

    var agent = await assistantClient.CreateAIAgentAsync(deploymentName,
        instructions: "You are a helpful assistant",
        tools: [AIFunctionFactory.Create(GetWeather)]);

    var thread = agent.GetNewThread();
    var agentOptions = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });

    var result = await agent.RunAsync(userInput, thread, agentOptions);
    Console.WriteLine(result);

    Console.WriteLine("---");
    await foreach (var update in agent.RunStreamingAsync(userInput, thread, agentOptions))
    {
        Console.Write(update);
    }

    // Clean up
    await assistantClient.DeleteThreadAsync(thread.ConversationId);
    await assistantClient.DeleteAssistantAsync(agent.Id);
}
