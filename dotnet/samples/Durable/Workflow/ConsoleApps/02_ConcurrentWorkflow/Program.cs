// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates the Fan-out/Fan-in pattern in a durable workflow.
// The workflow uses 4 executors: 2 class-based executors and 2 AI agents.
//
// WORKFLOW PATTERN:
//
//                  ParseQuestion (class-based)
//                         |
//              +----------+----------+
//              |                     |
//          Physicist              Chemist
//          (AI Agent)            (AI Agent)
//              |                     |
//              +----------+----------+
//                         |
//                    Aggregator (class-based)

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

// Create Azure OpenAI client
AzureOpenAIClient openAiClient = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());
ChatClient chatClient = openAiClient.GetChatClient(deploymentName);

// Define the 4 executors for the workflow
ParseQuestionExecutor parseQuestion = new();
AIAgent physicist = chatClient.AsAIAgent("You are a physics expert. Be concise (2-3 sentences).", "Physicist");
AIAgent chemist = chatClient.AsAIAgent("You are a chemistry expert. Be concise (2-3 sentences).", "Chemist");
AggregatorExecutor aggregator = new();

// Build workflow: ParseQuestion -> [Physicist, Chemist] (parallel) -> Aggregator
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
        services.ConfigureDurableOptions(
            options => options.Workflows.AddWorkflow(workflow),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

Console.WriteLine("Fan-out/Fan-in Workflow Sample");
Console.WriteLine("ParseQuestion -> [Physicist, Chemist] -> Aggregator");
Console.WriteLine();
Console.WriteLine("Enter a science question (or 'exit' to quit):");

while (true)
{
    Console.Write("> ");
    string? input = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(input) || input.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    try
    {
        IWorkflowRun run = await workflowClient.RunAsync(workflow, input);
        Console.WriteLine($"Run ID: {run.RunId}");

        if (run is IAwaitableWorkflowRun awaitableRun)
        {
            string? result = await awaitableRun.WaitForCompletionAsync<string>();

            Console.WriteLine("Workflow completed!");
            Console.WriteLine(result);
        }
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();
