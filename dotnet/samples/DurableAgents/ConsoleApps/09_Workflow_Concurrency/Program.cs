// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates the Fan-out/Fan-in pattern in a durable workflow.
// The workflow uses 4 executors: 2 class-based executors and 2 AI agents.
//
// WORKFLOW PATTERN (4 Executors):
//
//     ┌──────────────────┐
//     │  ParseQuestion   │  ← Class-based Executor
//     └────────┬─────────┘
//              │
//     ┌────────┴────────┐
//     ▼                 ▼
// ┌──────────┐   ┌──────────┐
// │ Physicist│   │ Chemist  │  ← AI Agents (parallel)
// └────┬─────┘   └────┬─────┘
//      │              │
//      └──────┬───────┘
//             ▼
//     ┌──────────────────┐
//     │   Aggregator     │  ← Class-based Executor
//     └──────────────────┘

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
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

// Create Azure OpenAI client
AzureOpenAIClient openAiClient = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());
ChatClient chatClient = openAiClient.GetChatClient(deploymentName);

// Define the 4 executors for the workflow
ParseQuestionExecutor parseQuestion = new();                                                                          // Executor 1: Class-based
AIAgent physicist = chatClient.AsAIAgent("You are a physics expert. Be concise (2-3 sentences).", "Physicist");       // Executor 2: AI Agent
AIAgent chemist = chatClient.AsAIAgent("You are a chemistry expert. Be concise (2-3 sentences).", "Chemist");         // Executor 3: AI Agent
AggregatorExecutor aggregator = new();                                                                                // Executor 4: Class-based

// Build workflow: ParseQuestion → [Physicist, Chemist] (parallel) → Aggregator
Workflow workflow = new WorkflowBuilder(parseQuestion)
    .WithName("ExpertReview")
    .AddFanOutEdge(parseQuestion, [physicist, chemist])
    .AddFanInEdge([physicist, chemist], aggregator)
    .Build();

// Configure and start the host
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableWorkflows(
            options => options.Workflows.AddWorkflow(workflow),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

// Get the IWorkflowClient from DI - no need to manually resolve DurableTaskClient
IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

// Console UI
Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("╔═══════════════════════════════════════════════════════════════════════╗");
Console.WriteLine("║  Fan-out/Fan-in Workflow Sample (4 Executors)                         ║");
Console.WriteLine("║                                                                       ║");
Console.WriteLine("║  ParseQuestion → [Physicist, Chemist] → Aggregator                    ║");
Console.WriteLine("║  (class-based)    (AI agents, parallel)  (class-based)                ║");
Console.WriteLine("╚═══════════════════════════════════════════════════════════════════════╝");
Console.ResetColor();
Console.WriteLine();

await Task.Delay(TimeSpan.FromSeconds(2)); // Allow pending workflows to resume

Console.WriteLine("Enter a science question (or 'exit' to quit):");
Console.WriteLine();

while (true)
{
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.Write("Question: ");
    Console.ResetColor();

    string? input = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(input) || input.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    try
    {
        // Cast to DurableRun for durable-specific features like InstanceId and WaitForCompletionAsync
        await using DurableRun run = (DurableRun)await workflowClient.RunAsync(workflow, input);
        Console.ForegroundColor = ConsoleColor.Gray;
        Console.WriteLine($"Instance: {run.InstanceId}");
        Console.ResetColor();

        string? result = await run.WaitForCompletionAsync();

        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine("\n✓ Workflow completed!\n");
        Console.ResetColor();
        Console.WriteLine(result);
    }
    catch (Exception ex)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine($"✗ Error: {ex.Message}");
        Console.ResetColor();
    }

    Console.WriteLine();
}

await host.StopAsync();
