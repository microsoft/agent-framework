// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a ChatClientAgent with function tools provided via an OpenAPI spec.
// It uses functionality from Semantic Kernel to parse the OpenAPI spec and create function tools to use with the Agent Framework Agent.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Plugins.OpenApi;
using OpenAI;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Load the OpenAPI Spec from a file.
KernelPlugin plugin = await OpenApiKernelPluginFactory.CreateFromOpenApiAsync("github", "OpenAPISpec.json");

// Convert the Semantic Kernel plugin to Agent Framework function tools.
// This requires a dummy Kernel instance, since KernelFunctions cannot execute without one.
Kernel kernel = new();
List<AITool> tools = plugin.Select(x => x.WithKernel(kernel)).Cast<AITool>().ToList();

// Create the chat client and agent, and provide the OpenAPI function tools to the agent.
AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(instructions: "You are a helpful assistant", tools: tools);

// Run the agent with the OpenAPI function tools.
Console.WriteLine(await agent.RunAsync("Please list the names, colors and descriptions of all the labels available in the microsoft/agent-framework repository on github."));
