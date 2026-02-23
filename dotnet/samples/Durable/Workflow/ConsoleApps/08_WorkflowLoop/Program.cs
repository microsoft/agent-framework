// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates a CYCLIC WORKFLOW (back-edges in the graph).
// SloganWriter and FeedbackProvider loop until the slogan meets quality criteria.

using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using WorkflowLoop;

// Get DTS connection string from environment variable
string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT is not set.");
string? azureOpenAiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_KEY");

// Create the chat client using key-based or Azure CLI credential authentication
AzureOpenAIClient openAiClient = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential());
IChatClient chatClient = openAiClient.GetChatClient(deploymentName).AsIChatClient();

// Define executors for the workflow
SloganWriterExecutor sloganWriter = new("SloganWriter", chatClient);
FeedbackExecutor feedbackProvider = new("FeedbackProvider", chatClient);

// Build the workflow with a circular edge: SloganWriter → FeedbackProvider → SloganWriter
Workflow workflow = new WorkflowBuilder(sloganWriter)
    .WithName("SloganCreationWorkflow")
    .AddEdge(sloganWriter, feedbackProvider)
    .AddEdge(feedbackProvider, sloganWriter)
    .WithOutputFrom(feedbackProvider)
    .Build();

IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableWorkflows(
            workflowOptions => workflowOptions.AddWorkflow(workflow),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

Console.WriteLine("Workflow Loop Demo - Enter a topic for slogan generation (or 'exit'):");

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
        // RunAsync starts the workflow; cast to IAwaitableWorkflowRun to wait for the result
        IAwaitableWorkflowRun run = (IAwaitableWorkflowRun)await workflowClient.RunAsync(workflow, input);
        Console.WriteLine($"Started run: {run.RunId}");

        string? result = await run.WaitForCompletionAsync<string>();
        Console.WriteLine($"Result: {result}");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();
