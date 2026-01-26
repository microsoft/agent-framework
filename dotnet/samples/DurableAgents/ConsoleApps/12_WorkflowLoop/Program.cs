// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to run a CYCLIC WORKFLOW as a durable orchestration.
// The workflow contains a loop: SloganWriter ⟷ FeedbackProvider
//
// WORKFLOW LOOP PATTERN:
// 1. SloganWriter generates a slogan based on user input
// 2. FeedbackProvider evaluates the slogan and provides feedback
// 3. If the rating is below threshold, FeedbackProvider sends feedback back to SloganWriter
// 4. SloganWriter improves the slogan based on feedback
// 5. Loop continues until FeedbackProvider accepts the slogan (rating >= threshold)
//
// This demonstrates:
// - Cyclic workflow support (back-edges in the graph)
// - Multi-type executor handlers (SloganWriter handles both string and FeedbackResult)
// - Message routing via SendMessageAsync for void-returning executors
// - YieldOutputAsync for final output when the loop completes

using Azure.Identity;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SingleAgent;
using Azure.AI.OpenAI;

// Get DTS connection string from environment variable
string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName).AsIChatClient();

// Define executors for the workflow
var sloganWriter = new SloganWriterExecutor("SloganWriter", chatClient);
var feedbackProvider = new FeedbackExecutor("FeedbackProvider", chatClient);

// Build the workflow by adding executors and connecting them
var workflow = new WorkflowBuilder(sloganWriter)
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
            options => options.Workflows.AddWorkflow(workflow),
            workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

DurableTaskClient durableClient = host.Services.GetRequiredService<DurableTaskClient>();

Console.WriteLine("Workflow Events Demo - Enter input for slogan generation (or 'exit'):");

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
        await RunWorkflowWithStreamingAsync(input, workflow, durableClient);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();

// Runs a workflow and streams events as they occur
async Task RunWorkflowWithStreamingAsync(string orderId, Workflow workflow, DurableTaskClient client)
{
    // StreamAsync starts the workflow and returns a handle for observing events
    await using DurableStreamingRun run = await DurableWorkflow.StreamAsync(workflow, orderId, client);
    Console.WriteLine($"Started: {run.InstanceId}");

    // WatchStreamAsync yields events as they're emitted by executors
    await foreach (WorkflowEvent evt in run.WatchStreamAsync())
    {
        // Always print the event type name
        WriteColored($"  Event: {evt.GetType().Name}", ConsoleColor.Gray);
    }
}

void WriteColored(string message, ConsoleColor color)
{
    Console.ForegroundColor = color;
    Console.WriteLine(message);
    Console.ResetColor();
}
