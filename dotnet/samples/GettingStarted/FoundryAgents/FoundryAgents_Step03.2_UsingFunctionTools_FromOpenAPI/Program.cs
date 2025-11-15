// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use an agent with function tools provided via an OpenAPI spec.
// It uses functionality from Semantic Kernel to parse the OpenAPI spec and create function tools to use with the Agent Framework Agent.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Plugins.OpenApi;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Load the OpenAPI Spec from a file.
KernelPlugin plugin = await OpenApiKernelPluginFactory.CreateFromOpenApiAsync("github", "OpenAPISpec.json");

// Convert the Semantic Kernel plugin to Agent Framework function tools.
// This requires a dummy Kernel instance, since KernelFunctions cannot execute without one.
Kernel kernel = new();
List<AITool> tools = plugin.Select(x => x.WithKernel(kernel)).Cast<AITool>().ToList();

const string AssistantInstructions = "You are a helpful assistant that can query GitHub repositories.";
const string AssistantName = "GitHubAssistant";

// Get a client to create/retrieve/delete server side agents with Azure Foundry Agents.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new AzureCliCredential());

// Create AIAgent directly
AIAgent agent = await aiProjectClient.CreateAIAgentAsync(name: AssistantName, model: deploymentName, instructions: AssistantInstructions, tools: tools);

// Run the agent with the OpenAPI function tools.
AgentThread thread = agent.GetNewThread();
Console.WriteLine(await agent.RunAsync("Please list the names, colors and descriptions of all the labels available in the microsoft/agent-framework repository on github.", thread));

// Cleanup by agent name removes the agent version created.
await aiProjectClient.Agents.DeleteAgentAsync(agent.Name);
