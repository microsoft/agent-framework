// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI.Chat;

// Get the Azure OpenAI endpoint and deployment name from environment variables.
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT is not set.");

// Use Azure Key Credential if provided, otherwise use Azure CLI Credential.
string? azureOpenAiKey = System.Environment.GetEnvironmentVariable("AZURE_OPENAI_KEY");
AzureOpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());

// Set up an AI agent following the standard Microsoft Agent Framework pattern.
const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";

AIAgent agent = client.GetChatClient(deploymentName).CreateAIAgent(JokerInstructions, JokerName);
AIAgent agent2 = client.GetChatClient(deploymentName).CreateAIAgent("You are good at telling inspirational quotes.", "InspirationBot");

Func<string, string> uppercaseFunc = s => s.ToUpperInvariant();
var uppercase = uppercaseFunc.BindAsExecutor("UppercaseExecutor");

Func<string, string> reverseTextFunc = s => s.ToUpperInvariant();
var reverse = reverseTextFunc.BindAsExecutor("ReverseTextExecutor");

WorkflowBuilder builder = new(uppercase);
builder.AddEdge(uppercase, agent2);
builder.AddEdge(agent2, reverse).WithOutputFrom(agent2);

var workflow = builder.WithName("MyTestWorkflow").Build();

// Configure the function app to host AI agents and workflows in a unified way.
// This will automatically generate HTTP API endpoints for agents and workflows.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()
    //.ConfigureDurableAgents(op => op.AddAIAgent(agent, timeToLive: TimeSpan.FromHours(1)))
    .ConfigureDurableOptions(options =>
    {
        // Configure workflows - agents referenced in workflows are automatically registered!
        options.Workflows.AddWorkflow(workflow);
    })
    .Build();
app.Run();
