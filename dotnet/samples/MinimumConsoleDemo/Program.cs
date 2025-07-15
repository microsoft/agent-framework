// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
{
    var conditions = new[] { "sunny", "cloudy", "rainy", "stormy" };
    return $"The weather in {location} is {conditions[new Random().Next(0, 4)]} with a high of {new Random().Next(10, 31)}°C.";
}

IChatClient chatClient = new AzureOpenAIClient(new Uri("https://oai-sk-integration-test-eastus.openai.azure.com/"), new AzureCliCredential()).GetChatClient("gpt-4o-mini").AsIChatClient();

Agent agent = new ChatClientAgent(
    chatClient,
    options: new()
    {
        Instructions = "You are a helpful assistant, you can help the user with weather information.",
        ChatOptions = new() { Tools = [AIFunctionFactory.Create(GetWeather)] }
    });

Console.WriteLine(await agent.RunAsync("What's the weather in Amsterdam?"));
