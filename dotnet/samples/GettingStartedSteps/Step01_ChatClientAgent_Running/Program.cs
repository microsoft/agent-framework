// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with Azure OpenAI as the backend.

using System;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using OpenAI;

var azureOpenAIEndpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var azureOpenAIDeploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

AIAgent agent = new AzureOpenAIClient(
    new Uri(azureOpenAIEndpoint),
    new AzureCliCredential())
     .GetChatClient(azureOpenAIDeploymentName)
     .CreateAIAgent(JokerInstructions, JokerName);

// Invoke the agent and output the text result.
Console.WriteLine("--- Run the agent ---\n");
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

// Invoke the agent with streaming support.
Console.WriteLine("\n--- Run the agent with streaming ---\n");
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.Write(update);
}
