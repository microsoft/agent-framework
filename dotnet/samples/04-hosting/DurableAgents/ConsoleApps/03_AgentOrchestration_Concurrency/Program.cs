// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using AgentOrchestration_Concurrency;
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

// Two agents used by the orchestration to demonstrate concurrent execution.
const string PhysicistName = "PhysicistAgent";
const string PhysicistInstructions = "You are an expert in physics. You answer questions from a physics perspective.";

const string ChemistName = "ChemistAgent";
const string ChemistInstructions = "You are a middle school chemistry teacher. You answer questions so that middle school students can understand.";

AIAgent physicistAgent = client.GetChatClient(deploymentName).AsAIAgent(PhysicistInstructions, PhysicistName);
AIAgent chemistAgent = client.GetChatClient(deploymentName).AsAIAgent(ChemistInstructions, ChemistName);

// Orchestrator function
static async Task<object> RunOrchestratorAsync(TaskOrchestrationContext context, string prompt)
{
    // Get both agents
    DurableAIAgent physicist = context.GetAgent(PhysicistName);
    DurableAIAgent chemist = context.GetAgent(ChemistName);

    // Start both agent runs concurrently
    Task<AgentResponse<TextResponse>> physicistTask = physicist.RunAsync<TextResponse>(prompt);
    Task<AgentResponse<TextResponse>> chemistTask = chemist.RunAsync<TextResponse>(prompt);

    // Wait for both tasks to complete using Task.WhenAll
    await Task.WhenAll(physicistTask, chemistTask);

    // Get the results
    TextResponse physicistResponse = (await physicistTask).Result;
    TextResponse chemistResponse = (await chemistTask).Result;

    // Return the result as a structured, anonymous type
    return new
    {
        physicist = physicistResponse.Text,
        chemist = chemistResponse.Text,
    };
}

// Configure the console app to host the AI agents.
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(loggingBuilder => loggingBuilder.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableAgents(
            options =>
            {
                options
                    .AddAIAgent(physicistAgent)
                    .AddAIAgent(chemistAgent);
            },
            workerBuilder: builder =>
            {
                builder.UseDurableTaskScheduler(dtsConnectionString);
                builder.AddTasks(
                    registry => registry.AddOrchestratorFunc<string, object>(nameof(RunOrchestratorAsync), RunOrchestratorAsync));
            },
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

DurableTaskClient durableTaskClient = host.Services.GetRequiredService<DurableTaskClient>();

// Console colors for better UX
Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("=== Multi-Agent Concurrent Orchestration Sample ===");
Console.ResetColor();
Console.WriteLine("Enter a question for the agents:");
Console.WriteLine();

// Read prompt from stdin
string? prompt = Console.ReadLine();
if (string.IsNullOrWhiteSpace(prompt))
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.Error.WriteLine("Error: Prompt is required.");
    Console.ResetColor();
    Environment.Exit(1);
    return;
}

Console.WriteLine();
Console.ForegroundColor = ConsoleColor.Gray;
Console.WriteLine("Starting orchestration...");
Console.ResetColor();

try
{
    // Start the orchestration
    string instanceId = await durableTaskClient.ScheduleNewOrchestrationInstanceAsync(
        orchestratorName: nameof(RunOrchestratorAsync),
        input: prompt);

    Console.ForegroundColor = ConsoleColor.Gray;
    Console.WriteLine($"Orchestration started with instance ID: {instanceId}");
    Console.WriteLine("Waiting for completion...");
    Console.ResetColor();

    // Wait for orchestration to complete
    OrchestrationMetadata status = await durableTaskClient.WaitForInstanceCompletionAsync(
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

        // Parse the output
        using JsonDocument doc = JsonDocument.Parse(status.SerializedOutput!);
        JsonElement output = doc.RootElement;

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine("Physicist's response:");
        Console.ResetColor();
        Console.WriteLine(output.GetProperty("physicist").GetString());
        Console.WriteLine();

        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine("Chemist's response:");
        Console.ResetColor();
        Console.WriteLine(output.GetProperty("chemist").GetString());
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
