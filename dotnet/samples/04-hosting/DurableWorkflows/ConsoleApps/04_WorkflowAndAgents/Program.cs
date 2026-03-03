// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates the THREE ways to configure durable agents and workflows:
//
// 1. ConfigureDurableAgents()   - For standalone agents only
// 2. ConfigureDurableWorkflows() - For workflows only
// 3. ConfigureDurableOptions()   - For both agents AND workflows
//
// KEY: All methods can be called MULTIPLE times - configurations are ADDITIVE.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenAI.Chat;
using WorkflowConcurrency;

// Configuration
string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT is not set.");
string? azureOpenAiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_KEY");

// Create AI agents
AzureOpenAIClient openAiClient = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());
ChatClient chatClient = openAiClient.GetChatClient(deploymentName);

AIAgent biologist = chatClient.AsAIAgent("You are a biology expert. Explain concepts clearly in 2-3 sentences.", "Biologist");
AIAgent physicist = chatClient.AsAIAgent("You are a physics expert. Explain concepts clearly in 2-3 sentences.", "Physicist");
AIAgent chemist = chatClient.AsAIAgent("You are a chemistry expert. Explain concepts clearly in 2-3 sentences.", "Chemist");

// Create workflows
ParseQuestionExecutor questionParser = new();
ResponseAggregatorExecutor responseAggregator = new();

Workflow physicsWorkflow = new WorkflowBuilder(questionParser)
    .WithName("PhysicsExpertReview")
    .AddEdge(questionParser, physicist)
    .Build();

Workflow expertTeamWorkflow = new WorkflowBuilder(questionParser)
.WithName("ExpertTeamReview")
.AddFanOutEdge(questionParser, [biologist, physicist])
.AddFanInEdge([biologist, physicist], responseAggregator)
.Build();

Workflow chemistryWorkflow = new WorkflowBuilder(questionParser)
    .WithName("ChemistryExpertReview")
    .AddEdge(questionParser, chemist)
    .Build();

// Configure services - demonstrating all 3 methods (each can be called multiple times)
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        // METHOD 1: ConfigureDurableAgents - for standalone agents only
        services.ConfigureDurableAgents(
            options => options.AddAIAgent(biologist),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));

        // METHOD 2: ConfigureDurableWorkflows - for workflows only
        services.ConfigureDurableWorkflows(options => options.AddWorkflow(physicsWorkflow));

        // METHOD 3: ConfigureDurableOptions - for both agents AND workflows
        services.ConfigureDurableOptions(options =>
        {
            options.Agents.AddAIAgent(chemist);
            options.Workflows.AddWorkflow(expertTeamWorkflow);
        });

        // Second call to ConfigureDurableOptions (additive - adds to existing config)
        services.ConfigureDurableOptions(options => options.Workflows.AddWorkflow(chemistryWorkflow));
    })
    .Build();

await host.StartAsync();
IServiceProvider services = host.Services;
IWorkflowClient workflowClient = services.GetRequiredService<IWorkflowClient>();

// DEMO 1: Direct agent conversation (standalone agents)
Console.WriteLine("\n═══ DEMO 1: Direct Agent Conversation ═══\n");

AIAgent biologistProxy = services.GetRequiredKeyedService<AIAgent>("Biologist");
AgentSession session = await biologistProxy.GetNewSessionAsync();
AgentResponse response = await biologistProxy.RunAsync("What is photosynthesis?", session);
Console.WriteLine($"🧬 Biologist: {response.Text}\n");

AIAgent chemistProxy = services.GetRequiredKeyedService<AIAgent>("Chemist");
session = await chemistProxy.GetNewSessionAsync();
response = await chemistProxy.RunAsync("What is a chemical bond?", session);
Console.WriteLine($"🧪 Chemist: {response.Text}\n");

// DEMO 2: Single-agent workflow
Console.WriteLine("═══ DEMO 2: Single-Agent Workflow ═══\n");
await RunWorkflowAsync(workflowClient, physicsWorkflow, "What is the relationship between energy and mass?");

// DEMO 3: Multi-agent workflow
Console.WriteLine("═══ DEMO 3: Multi-Agent Workflow ═══\n");
await RunWorkflowAsync(workflowClient, expertTeamWorkflow, "How does radiation affect living cells?");

// DEMO 4: Workflow from second ConfigureDurableOptions call
Console.WriteLine("═══ DEMO 4: Workflow (added via 2nd ConfigureDurableOptions) ═══\n");
await RunWorkflowAsync(workflowClient, chemistryWorkflow, "What happens during combustion?");

Console.WriteLine("\n✅ All demos completed!");
await host.StopAsync();

// Helper method
static async Task RunWorkflowAsync(IWorkflowClient client, Workflow workflow, string question)
{
    Console.WriteLine($"📋 {workflow.Name}: \"{question}\"");
    IWorkflowRun run = await client.RunAsync(workflow, question);
    if (run is IAwaitableWorkflowRun awaitable)
    {
        string? result = await awaitable.WaitForCompletionAsync<string>();
        Console.WriteLine($"✅ {result}\n");
    }
}
