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
    return $"The weather in {location} is cloudy with a high of 15°C.";
}

IChatClient chatClient = new AzureOpenAIClient(
    new Uri(Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!),
    new AzureCliCredential())
     .GetChatClient("gpt-4o-mini")
     .AsIChatClient();

AIAgent agent = new ChatClientAgent(
    chatClient,
    instructions: "You are a helpful assistant, you can help the user with weather information.",
    tools: [AIFunctionFactory.Create(GetWeather)]);

Console.WriteLine(await agent.RunAsync("What's the weather in Amsterdam?"));
