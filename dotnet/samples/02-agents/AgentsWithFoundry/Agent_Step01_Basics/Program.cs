// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and run a basic agent with AIProjectClient.AsAIAgent(...).

using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIAgent agent =
    new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .AsAIAgent(model: deploymentName, instructions: "You are good at telling jokes.", name: "JokerAgent");

ProjectResponsesClient projectResponsesClient = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetProjectOpenAIClient()
    .GetProjectResponsesClientForModel(deploymentName);

AIAgent agent2 = new ChatClientAgent(chatClient: projectResponsesClient.AsIChatClient(deploymentName), instructions: "You are good at telling jokes.", name: "JokerAgent2");

// Once you have the agent, you can invoke it like any other AIAgent.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
Console.WriteLine(await agent2.RunAsync("Tell me a joke about a pirate."));
