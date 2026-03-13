// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using AgentOrchestration_HITL;
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

// Single agent used by the orchestration to demonstrate human-in-the-loop workflow.
const string WriterName = "WriterAgent";
const string WriterInstructions =
    """
    You are a professional content writer who creates high-quality articles on various topics.
    You write engaging, informative, and well-structured content that follows best practices for readability and accuracy.
    """;

AIAgent writerAgent = client.GetChatClient(deploymentName).AsAIAgent(WriterInstructions, WriterName);

// Orchestrator function
static async Task<object> RunOrchestratorAsync(TaskOrchestrationContext context, ContentGenerationInput input)
{
    // Get the writer agent
    DurableAIAgent writerAgent = context.GetAgent("WriterAgent");
    AgentSession writerSession = await writerAgent.CreateSessionAsync();

    // Set initial status
    context.SetCustomStatus($"Starting content generation for topic: {input.Topic}");

    // Step 1: Generate initial content
    AgentResponse<GeneratedContent> writerResponse = await writerAgent.RunAsync<GeneratedContent>(
        message: $"Write a short article about '{input.Topic}' in less than 300 words.",
        session: writerSession);
    GeneratedContent content = writerResponse.Result;

    // Human-in-the-loop iteration - we set a maximum number of attempts to avoid infinite loops
    int iterationCount = 0;
    while (iterationCount++ < input.MaxReviewAttempts)
    {
        context.SetCustomStatus(
            $"Requesting human feedback. Iteration #{iterationCount}. Timeout: {input.ApprovalTimeoutHours} hour(s).");

        // Step 2: Notify user to review the content
        await context.CallActivityAsync(nameof(NotifyUserForApproval), content);

        // Step 3: Wait for human feedback with configurable timeout
        HumanApprovalResponse humanResponse;
        try
        {
            humanResponse = await context.WaitForExternalEvent<HumanApprovalResponse>(
                eventName: "HumanApproval",
                timeout: TimeSpan.FromHours(input.ApprovalTimeoutHours));
        }
        catch (OperationCanceledException)
        {
            // Timeout occurred - treat as rejection
            context.SetCustomStatus(
                $"Human approval timed out after {input.ApprovalTimeoutHours} hour(s). Treating as rejection.");
            throw new TimeoutException($"Human approval timed out after {input.ApprovalTimeoutHours} hour(s).");
        }

        if (humanResponse.Approved)
        {
            context.SetCustomStatus("Content approved by human reviewer. Publishing content...");

            // Step 4: Publish the approved content
            await context.CallActivityAsync(nameof(PublishContent), content);

            context.SetCustomStatus($"Content published successfully at {context.CurrentUtcDateTime:s}");
            return new { content = content.Content };
        }

        context.SetCustomStatus("Content rejected by human reviewer. Incorporating feedback and regenerating...");

        // Incorporate human feedback and regenerate
        writerResponse = await writerAgent.RunAsync<GeneratedContent>(
            message: $"""
                The content was rejected by a human reviewer. Please rewrite the article incorporating their feedback.
                
                Human Feedback: {humanResponse.Feedback}
                """,
            session: writerSession);

        content = writerResponse.Result;
    }

    // If we reach here, it means we exhausted the maximum number of iterations
    throw new InvalidOperationException(
        $"Content could not be approved after {input.MaxReviewAttempts} iterations.");
}

// Activity functions
static void NotifyUserForApproval(TaskActivityContext context, GeneratedContent content)
{
    // In a real implementation, this would send notifications via email, SMS, etc.
    Console.WriteLine(
        $"""
        NOTIFICATION: Please review the following content for approval:
        Title: {content.Title}
        Content: {content.Content}
        Use the approval endpoint to approve or reject this content.
        """);
}

static void PublishContent(TaskActivityContext context, GeneratedContent content)
{
    // In a real implementation, this would publish to a CMS, website, etc.
    Console.WriteLine(
        $"""
        PUBLISHING: Content has been published successfully.
        Title: {content.Title}
        Content: {content.Content}
        """);
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
                builder.AddTasks(registry =>
                {
                    registry.AddOrchestratorFunc<ContentGenerationInput>(nameof(RunOrchestratorAsync), RunOrchestratorAsync);
                    registry.AddActivityFunc<GeneratedContent>(nameof(NotifyUserForApproval), NotifyUserForApproval);
                    registry.AddActivityFunc<GeneratedContent>(nameof(PublishContent), PublishContent);
                });
            },
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

DurableTaskClient durableTaskClient = host.Services.GetRequiredService<DurableTaskClient>();

// Console colors for better UX
Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("=== Human-in-the-Loop Orchestration Sample ===");
Console.ResetColor();
Console.WriteLine("Enter topic for content generation:");
Console.WriteLine();

// Read topic from stdin
string? topic = Console.ReadLine();
if (string.IsNullOrWhiteSpace(topic))
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.Error.WriteLine("Error: Topic is required.");
    Console.ResetColor();
    Environment.Exit(1);
    return;
}

// Prompt for optional parameters with defaults
Console.WriteLine();
Console.WriteLine("Max review attempts (default: 3):");
string? maxAttemptsInput = Console.ReadLine();
int maxReviewAttempts = int.TryParse(maxAttemptsInput, out int maxAttempts) && maxAttempts > 0
    ? maxAttempts
    : 3;

Console.WriteLine("Approval timeout in hours (default: 72):");
string? timeoutInput = Console.ReadLine();
float approvalTimeoutHours = float.TryParse(timeoutInput, out float timeout) && timeout > 0
    ? timeout
    : 72;

ContentGenerationInput input = new()
{
    Topic = topic,
    MaxReviewAttempts = maxReviewAttempts,
    ApprovalTimeoutHours = approvalTimeoutHours
};

Console.WriteLine();
Console.ForegroundColor = ConsoleColor.Gray;
Console.WriteLine("Starting orchestration...");
Console.ResetColor();

try
{
    // Start the orchestration
    string instanceId = await durableTaskClient.ScheduleNewOrchestrationInstanceAsync(
        orchestratorName: nameof(RunOrchestratorAsync),
        input: input);

    Console.ForegroundColor = ConsoleColor.Gray;
    Console.WriteLine($"Orchestration started with instance ID: {instanceId}");
    Console.WriteLine("Waiting for human approval...");
    Console.ResetColor();
    Console.WriteLine();

    // Monitor orchestration status and handle approval prompts
    using CancellationTokenSource cts = new();
    Task orchestrationTask = Task.Run(async () =>
    {
        while (!cts.Token.IsCancellationRequested)
        {
            OrchestrationMetadata? status = await durableTaskClient.GetInstanceAsync(
                instanceId,
                getInputsAndOutputs: true,
                cts.Token);

            if (status == null)
            {
                await Task.Delay(TimeSpan.FromSeconds(1), cts.Token);
                continue;
            }

            // Check if we're waiting for approval
            if (status.SerializedCustomStatus != null)
            {
                string? customStatus = status.ReadCustomStatusAs<string>();
                if (customStatus?.StartsWith("Requesting human feedback", StringComparison.OrdinalIgnoreCase) == true)
                {
                    // Prompt user for approval
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine("Content is ready for review. Check the logs above for details.");
                    Console.Write("Approve? (y/n): ");
                    Console.ResetColor();

                    string? approvalInput = Console.ReadLine();
                    bool approved = approvalInput?.Trim().Equals("y", StringComparison.OrdinalIgnoreCase) == true;

                    Console.Write("Feedback (optional): ");
                    string? feedback = Console.ReadLine() ?? "";

                    HumanApprovalResponse approvalResponse = new()
                    {
                        Approved = approved,
                        Feedback = feedback
                    };

                    await durableTaskClient.RaiseEventAsync(instanceId, "HumanApproval", approvalResponse);
                }
            }

            if (status.RuntimeStatus is OrchestrationRuntimeStatus.Completed or OrchestrationRuntimeStatus.Failed or OrchestrationRuntimeStatus.Terminated)
            {
                break;
            }

            await Task.Delay(TimeSpan.FromSeconds(1), cts.Token);
        }
    }, cts.Token);

    // Wait for orchestration to complete
    OrchestrationMetadata finalStatus = await durableTaskClient.WaitForInstanceCompletionAsync(
        instanceId,
        getInputsAndOutputs: true,
        CancellationToken.None);

    cts.Cancel();
    await orchestrationTask;

    Console.WriteLine();

    if (finalStatus.RuntimeStatus == OrchestrationRuntimeStatus.Completed)
    {
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine("✓ Orchestration completed successfully!");
        Console.ResetColor();
        Console.WriteLine();

        JsonElement output = finalStatus.ReadOutputAs<JsonElement>();
        if (output.TryGetProperty("content", out JsonElement contentElement))
        {
            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("Published content:");
            Console.ResetColor();
            Console.WriteLine(contentElement.GetString());
        }
    }
    else if (finalStatus.RuntimeStatus == OrchestrationRuntimeStatus.Failed)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.WriteLine("✗ Orchestration failed!");
        Console.ResetColor();
        if (finalStatus.FailureDetails != null)
        {
            Console.WriteLine($"Error: {finalStatus.FailureDetails.ErrorMessage}");
        }
        Environment.Exit(1);
    }
    else
    {
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.WriteLine($"Orchestration status: {finalStatus.RuntimeStatus}");
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
