// Copyright (c) Microsoft. All rights reserved.

using AgentOrchestration_Conditionals;
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

// Spam detection agent
const string SpamDetectionAgentName = "SpamDetectionAgent";
const string SpamDetectionAgentInstructions =
    """
    You are an expert email spam detection system. Analyze emails and determine if they are spam.
    Return your analysis as JSON with 'is_spam' (boolean) and 'reason' (string) fields.
    """;

// Email assistant agent
const string EmailAssistantAgentName = "EmailAssistantAgent";
const string EmailAssistantAgentInstructions =
    """
    You are a professional email assistant. Draft professional, courteous, and helpful email responses.
    Return your response as JSON with a 'response' field containing the reply.
    """;

AIAgent spamDetectionAgent = client.GetChatClient(deploymentName).AsAIAgent(SpamDetectionAgentInstructions, SpamDetectionAgentName);
AIAgent emailAssistantAgent = client.GetChatClient(deploymentName).AsAIAgent(EmailAssistantAgentInstructions, EmailAssistantAgentName);

// Orchestrator function
static async Task<string> RunOrchestratorAsync(TaskOrchestrationContext context, Email email)
{
    // Get the spam detection agent
    DurableAIAgent spamDetectionAgent = context.GetAgent(SpamDetectionAgentName);
    AgentSession spamSession = await spamDetectionAgent.CreateSessionAsync();

    // Step 1: Check if the email is spam
    AgentResponse<DetectionResult> spamDetectionResponse = await spamDetectionAgent.RunAsync<DetectionResult>(
        message:
            $"""
            Analyze this email for spam content and return a JSON response with 'is_spam' (boolean) and 'reason' (string) fields:
            Email ID: {email.EmailId}
            Content: {email.EmailContent}
            """,
        session: spamSession);
    DetectionResult result = spamDetectionResponse.Result;

    // Step 2: Conditional logic based on spam detection result
    if (result.IsSpam)
    {
        // Handle spam email
        return await context.CallActivityAsync<string>(nameof(HandleSpamEmail), result.Reason);
    }

    // Generate and send response for legitimate email
    DurableAIAgent emailAssistantAgent = context.GetAgent(EmailAssistantAgentName);
    AgentSession emailSession = await emailAssistantAgent.CreateSessionAsync();

    AgentResponse<EmailResponse> emailAssistantResponse = await emailAssistantAgent.RunAsync<EmailResponse>(
        message:
            $"""
            Draft a professional response to this email. Return a JSON response with a 'response' field containing the reply:
            
            Email ID: {email.EmailId}
            Content: {email.EmailContent}
            """,
        session: emailSession);

    EmailResponse emailResponse = emailAssistantResponse.Result;

    return await context.CallActivityAsync<string>(nameof(SendEmail), emailResponse.Response);
}

// Activity functions
static void HandleSpamEmail(TaskActivityContext context, string reason)
{
    Console.WriteLine($"Email marked as spam: {reason}");
}

static void SendEmail(TaskActivityContext context, string message)
{
    Console.WriteLine($"Email sent: {message}");
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
                    .AddAIAgent(spamDetectionAgent)
                    .AddAIAgent(emailAssistantAgent);
            },
            workerBuilder: builder =>
            {
                builder.UseDurableTaskScheduler(dtsConnectionString);
                builder.AddTasks(registry =>
                {
                    registry.AddOrchestratorFunc<Email>(nameof(RunOrchestratorAsync), RunOrchestratorAsync);
                    registry.AddActivityFunc<string>(nameof(HandleSpamEmail), HandleSpamEmail);
                    registry.AddActivityFunc<string>(nameof(SendEmail), SendEmail);
                });
            },
            clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
    })
    .Build();

await host.StartAsync();

DurableTaskClient durableTaskClient = host.Services.GetRequiredService<DurableTaskClient>();

// Console colors for better UX
Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("=== Multi-Agent Conditional Orchestration Sample ===");
Console.ResetColor();
Console.WriteLine("Enter email content:");
Console.WriteLine();

// Read email content from stdin
string? emailContent = Console.ReadLine();
if (string.IsNullOrWhiteSpace(emailContent))
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.Error.WriteLine("Error: Email content is required.");
    Console.ResetColor();
    Environment.Exit(1);
    return;
}

// Generate email ID automatically
Email email = new()
{
    EmailId = $"email-{Guid.NewGuid():N}",
    EmailContent = emailContent
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
        input: email);

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
