// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use the OpenAI SDK to create and use a simple AI agent with any model hosted in Azure AI Foundry.
// You could use models from Microsoft, OpenAI, DeepSeek, Hugging Face, Meta, xAI or any other model you have deployed in your Azure AI Foundry resource.
// Note: Ensure that you pick a model that suits your needs. For example, if you want to use function calling, ensure that the model you pick supports function calling.

using System.ClientModel;
using System.ClientModel.Primitives;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_OPENAI_ENDPOINT is not set.");
var apiKey = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_OPENAI_APIKEY");
var model = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_MODEL_DEPLOYMENT") ?? "Phi-4-mini-instruct";

// Since we are using the OpenAI Client SDK, we need to override the default endpoint to point to Azure Foundry.
var clientOptions = new OpenAIClientOptions() { Endpoint = new Uri(endpoint) };

// Create the OpenAI client with either an API key or Azure CLI credential.
OpenAIClient client = string.IsNullOrWhiteSpace(apiKey)
    ? new OpenAIClient(new BearerTokenPolicy(new AzureCliCredential(), "https://ai.azure.com/.default"), clientOptions)
    : new OpenAIClient(new ApiKeyCredential(apiKey), clientOptions);

AIAgent agent = client
    .GetChatClient(model)
    .CreateAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
