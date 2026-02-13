// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates the THREE ways to configure durable agents and workflows
// in an Azure Functions app:
//
// 1. ConfigureDurableAgents()   - For standalone agents only
// 2. ConfigureDurableWorkflows() - For workflows only
// 3. ConfigureDurableOptions()   - For both agents AND workflows
//
// KEY: All methods can be called MULTIPLE times - configurations are ADDITIVE.
//
// Workflow structure:
//
//  PhysicsExpertReview:   ParseQuestion ──► Physicist (AI Agent)
//
//  ExpertTeamReview:      ParseQuestion ──┬──► Physicist (AI Agent) ──┬──► Aggregator
//                                         └──► Chemist   (AI Agent) ──┘
//
//  ChemistryExpertReview: ParseQuestion ──► Chemist (AI Agent)

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AzureFunctions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Azure.Functions.Worker.Builder;
using Microsoft.Extensions.Hosting;
using OpenAI.Chat;
using WorkflowAndAgentsFunctionApp;

// Configuration
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT is not set.");
string? azureOpenAiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_KEY");

// Create Azure OpenAI client
AzureOpenAIClient openAiClient = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());
ChatClient chatClient = openAiClient.GetChatClient(deploymentName);

// Create AI agents
AIAgent physicist = chatClient.AsAIAgent("You are a physics expert. Explain concepts clearly in 2-3 sentences.", "Physicist");
AIAgent chemist = chatClient.AsAIAgent("You are a chemistry expert. Explain concepts clearly in 2-3 sentences.", "Chemist");
AIAgent biologist = chatClient.AsAIAgent("You are a biology expert. Explain concepts clearly in 2-3 sentences.", "Biologist");

// Create custom executors
ParseQuestionExecutor questionParser = new();
ResponseAggregatorExecutor responseAggregator = new();

// Workflow 1: Single-agent workflow (Physics)
Workflow physicsWorkflow = new WorkflowBuilder(questionParser)
    .WithName("PhysicsExpertReview")
    .AddEdge(questionParser, physicist)
    .Build();

// Workflow 2: Multi-agent workflow with fan-out/fan-in (Expert Team)
Workflow expertTeamWorkflow = new WorkflowBuilder(questionParser)
    .WithName("ExpertTeamReview")
    .AddFanOutEdge(questionParser, [physicist, chemist])
    .AddFanInEdge([physicist, chemist], responseAggregator)
    .Build();

// Workflow 3: Single-agent workflow (Chemistry)
Workflow chemistryWorkflow = new WorkflowBuilder(questionParser)
    .WithName("ChemistryExpertReview")
    .AddEdge(questionParser, chemist)
    .Build();

// Configure the function app using all 3 methods to demonstrate additive configuration.
// Each method can be called one or more times - configurations accumulate.
using IHost app = FunctionsApplication
    .CreateBuilder(args)
    .ConfigureFunctionsWebApplication()

    // METHOD 1: ConfigureDurableAgents - for standalone agents only.
    // Registers the biologist agent as a standalone agent (not part of any workflow).
    .ConfigureDurableAgents(options => options.AddAIAgent(biologist))

    // METHOD 2: ConfigureDurableWorkflows - for workflows only.
    // Registers the physics workflow. Agents referenced in the workflow (Physicist) are auto-discovered.
    .ConfigureDurableWorkflows(options => options.AddWorkflow(physicsWorkflow))

    // METHOD 3: ConfigureDurableOptions - for both agents AND workflows.
    // Registers the chemist agent explicitly and the expert team workflow together.
    .ConfigureDurableOptions(options =>
    {
        options.Agents.AddAIAgent(chemist);
        options.Workflows.AddWorkflow(expertTeamWorkflow);
    })

    // Second call to ConfigureDurableOptions (additive - adds to existing config).
    .ConfigureDurableOptions(options => options.Workflows.AddWorkflow(chemistryWorkflow))

    .Build();
app.Run();
