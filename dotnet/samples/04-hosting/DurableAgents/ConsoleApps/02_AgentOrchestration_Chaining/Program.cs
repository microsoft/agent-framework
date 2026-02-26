// Copyright (c) Microsoft. All rights reserved.

using AgentOrchestration_Chaining;
using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpenAI.Chat;
using Environment = System.Environment;

// Get the Azure OpenAI endpoint and deployment name from environment variables.
string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")
    ?? throw new InvalidOperationException("AZURE_OPENAI_DEPLOYMENT_NAME is not set.");

// Get DTS connection string from environment variable
string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// Use Azure Key Credential if provided, otherwise use Azure CLI Credential.
string? azureOpenAiKey = Environment.GetEnvironmentVariable("AZURE_OPENAI_API_KEY");
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AzureOpenAIClient client = !string.IsNullOrEmpty(azureOpenAiKey)
    ? new AzureOpenAIClient(new Uri(endpoint), new AzureKeyCredential(azureOpenAiKey))
    : new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential());

// Single agent used by the orchestration to demonstrate sequential calls on the same session.
const string WriterName = "WriterAgent";
const string WriterInstructions =
    """
    You refine short pieces of text. When given an initial sentence you enhance it;
    when given an improved sentence you polish it further.
    """;

AIAgent writerAgent = client.GetChatClient(deploymentName).AsAIAgent(WriterInstructions, WriterName);

// Orchestrator function
static async Task<string> RunOrchestratorAsync(TaskOrchestrationContext context)
{
    DurableAIAgent writer = context.GetAgent("WriterAgent");
    AgentSession writerSession = await writer.CreateSessionAsync();

    AgentResponse<TextResponse> initial = await writer.RunAsync<TextResponse>(
        message: "Write a concise inspirational sentence about learning.",
        session: writerSession);

    AgentResponse<TextResponse> refined = await writer.RunAsync<TextResponse>(
        message: $"Improve this further while keeping it under 25 words: {initial.Result.Text}",
        session: writerSession);

    return refined.Result.Text;
}

// Configure the console app to host the AI agent.
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(loggingBuilder => loggingBuilder.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableAgents(
            options => options.AddAIAgent(writerAgent),
            workerBuilder: builder =>
            {
                builder.UseDurableTaskScheduler(dtsConnectionString);
                builder.AddTasks(registry => registry.AddOrchestratorFunc(nameof(RunOrchestratorAsync), RunOrchestratorAsync));
            },
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

DurableTaskClient durableClient = host.Services.GetRequiredService<DurableTaskClient>();

// Console colors for better UX
Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("=== Single Agent Orchestration Chaining Sample ===");
Console.ResetColor();
Console.WriteLine("Starting orchestration...");
Console.WriteLine();

try
{
    // Start the orchestration
    string instanceId = await durableClient.ScheduleNewOrchestrationInstanceAsync(
        orchestratorName: nameof(RunOrchestratorAsync));

    Console.ForegroundColor = ConsoleColor.Gray;
    Console.WriteLine($"Orchestration started with instance ID: {instanceId}");
    Console.WriteLine("Waiting for completion...");
    Console.ResetColor();

    // Wait for orchestration to complete
    OrchestrationMetadata status = await durableClient.WaitForInstanceCompletionAsync(
        instanceId,
        getInputsAndOutputs: true,
        CancellationToken.None);

    Console.WriteLine();

    if (status.RuntimeStatus == OrchestrationRuntimeStatus.Completed)
    {
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine("✓ Orchestration completed successfully!");
        Console.ResetColor();
        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.Write("Result: ");
        Console.ResetColor();
        Console.WriteLine(status.ReadOutputAs<string>());
    }
    else if (status.RuntimeStatus == OrchestrationRuntimeStatus.Failed)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("✗ Orchestration failed!");
        Console.ResetColor();
        if (status.FailureDetails != null)
        {
            Console.WriteLine($"Error: {status.FailureDetails.ErrorMessage}");
        }
        Environment.Exit(1);
    }
    else
    {
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"Orchestration status: {status.RuntimeStatus}");
        Console.ResetColor();
    }
}
catch (Exception ex)
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.Error.WriteLine($"Error: {ex.Message}");
    Console.ResetColor();
    Environment.Exit(1);
}
finally
{
    await host.StopAsync();
}
