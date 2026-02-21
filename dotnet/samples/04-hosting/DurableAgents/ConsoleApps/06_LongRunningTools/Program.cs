// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Azure;
using Azure.AI.OpenAI;
using Azure.Identity;
using LongRunningTools;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.AI;
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

// Agent used by the orchestration to write content.
const string WriterAgentName = "Writer";
const string WriterAgentInstructions =
    """
    You are a professional content writer who creates high-quality articles on various topics.
    You write engaging, informative, and well-structured content that follows best practices for readability and accuracy.
    """;

AIAgent writerAgent = client.GetChatClient(deploymentName).AsAIAgent(WriterAgentInstructions, WriterAgentName);

// Agent that can start content generation workflows using tools
const string PublisherAgentName = "Publisher";
const string PublisherAgentInstructions =
    """
    You are a publishing agent that can manage content generation workflows.
    You have access to tools to start, monitor, and raise events for content generation workflows.
    """;

const string HumanFeedbackEventName = "HumanFeedback";

// Orchestrator function
static async Task<object> RunOrchestratorAsync(TaskOrchestrationContext context, ContentGenerationInput input)
{
    // Get the writer agent
    DurableAIAgent writerAgent = context.GetAgent(WriterAgentName);
    AgentSession writerSession = await writerAgent.CreateSessionAsync();

    // Set initial status
    context.SetCustomStatus($"Starting content generation for topic: {input.Topic}");

    // Step 1: Generate initial content
    AgentResponse<GeneratedContent> writerResponse = await writerAgent.RunAsync<GeneratedContent>(
        message: $"Write a short article about '{input.Topic}'.",
        session: writerSession);
    GeneratedContent content = writerResponse.Result;

    // Human-in-the-loop iteration - we set a maximum number of attempts to avoid infinite loops
    int iterationCount = 0;
    while (iterationCount++ < input.MaxReviewAttempts)
    {
        context.SetCustomStatus(
            new
            {
                message = "Requesting human feedback.",
                approvalTimeoutHours = input.ApprovalTimeoutHours,
                iterationCount,
                content
            });

        // Step 2: Notify user to review the content
        await context.CallActivityAsync(nameof(NotifyUserForApproval), content);

        // Step 3: Wait for human feedback with configurable timeout
        HumanFeedbackResponse humanResponse;
        try
        {
            humanResponse = await context.WaitForExternalEvent<HumanFeedbackResponse>(
                eventName: HumanFeedbackEventName,
                timeout: TimeSpan.FromHours(input.ApprovalTimeoutHours));
        }
        catch (OperationCanceledException)
        {
            // Timeout occurred - treat as rejection
            context.SetCustomStatus(
                new
                {
                    message = $"Human approval timed out after {input.ApprovalTimeoutHours} hour(s). Treating as rejection.",
                    iterationCount,
                    content
                });
            throw new TimeoutException($"Human approval timed out after {input.ApprovalTimeoutHours} hour(s).");
        }

        if (humanResponse.Approved)
        {
            context.SetCustomStatus(new
            {
                message = "Content approved by human reviewer. Publishing content...",
                content
            });

            // Step 4: Publish the approved content
            await context.CallActivityAsync(nameof(PublishContent), content);

            context.SetCustomStatus(new
            {
                message = $"Content published successfully at {context.CurrentUtcDateTime:s}",
                humanFeedback = humanResponse,
                content
            });
            return new { content = content.Content };
        }

        context.SetCustomStatus(new
        {
            message = "Content rejected by human reviewer. Incorporating feedback and regenerating...",
            humanFeedback = humanResponse,
            content
        });

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
    Console.ForegroundColor = ConsoleColor.DarkMagenta;
    Console.WriteLine(
        $"""
        NOTIFICATION: Please review the following content for approval:
        Title: {content.Title}
        Content: {content.Content}
        """);
    Console.ResetColor();
}

static void PublishContent(TaskActivityContext context, GeneratedContent content)
{
    // In a real implementation, this would publish to a CMS, website, etc.
    Console.ForegroundColor = ConsoleColor.DarkMagenta;
    Console.WriteLine(
        $"""
        PUBLISHING: Content has been published successfully.
        Title: {content.Title}
        Content: {content.Content}
        """);
    Console.ResetColor();
}

// Tools that demonstrate starting orchestrations from agent tool calls.
[Description("Starts a content generation workflow and returns the instance ID for tracking.")]
static string StartContentGenerationWorkflow([Description("The topic for content generation")] string topic)
{
    const int MaxReviewAttempts = 3;
    const float ApprovalTimeoutHours = 72;

    // Schedule the orchestration, which will start running after the tool call completes.
    string instanceId = DurableAgentContext.Current.ScheduleNewOrchestration(
        name: nameof(RunOrchestratorAsync),
        input: new ContentGenerationInput
        {
            Topic = topic,
            MaxReviewAttempts = MaxReviewAttempts,
            ApprovalTimeoutHours = ApprovalTimeoutHours
        });

    return $"Workflow started with instance ID: {instanceId}";
}

[Description("Gets the status of a workflow orchestration and returns a summary of the workflow's current status.")]
static async Task<object> GetWorkflowStatusAsync(
    [Description("The instance ID of the workflow to check")] string instanceId,
    [Description("Whether to include detailed information")] bool includeDetails = true)
{
    // Get the current agent context using the session-static property
    OrchestrationMetadata? status = await DurableAgentContext.Current.GetOrchestrationStatusAsync(
        instanceId,
        includeDetails);

    if (status is null)
    {
        return new
        {
            instanceId,
            error = $"Workflow instance '{instanceId}' not found.",
        };
    }

    return new
    {
        instanceId = status.InstanceId,
        createdAt = status.CreatedAt,
        executionStatus = status.RuntimeStatus,
        workflowStatus = status.SerializedCustomStatus,
        lastUpdatedAt = status.LastUpdatedAt,
        failureDetails = status.FailureDetails
    };
}

[Description(
    "Raises a feedback event for the content generation workflow. If approved, the workflow will be published. " +
    "If rejected, the workflow will generate new content.")]
static async Task SubmitHumanFeedbackAsync(
    [Description("The instance ID of the workflow to submit feedback for")] string instanceId,
    [Description("Feedback to submit")] HumanFeedbackResponse feedback)
{
    await DurableAgentContext.Current.RaiseOrchestrationEventAsync(instanceId, HumanFeedbackEventName, feedback);
}

// Configure the console app to host the AI agents.
IHost host = Host.CreateDefaultBuilder(args)
    .ConfigureLogging(loggingBuilder => loggingBuilder.SetMinimumLevel(LogLevel.Warning))
    .ConfigureServices(services =>
    {
        services.ConfigureDurableAgents(
            options =>
            {
                // Add the writer agent used by the orchestration
                options.AddAIAgent(writerAgent);

                // Define the agent that can start orchestrations from tool calls
                options.AddAIAgentFactory(PublisherAgentName, sp =>
                {
                    return client.GetChatClient(deploymentName).AsAIAgent(
                        instructions: PublisherAgentInstructions,
                        name: PublisherAgentName,
                        services: sp,
                        tools: [
                            AIFunctionFactory.Create(StartContentGenerationWorkflow),
                            AIFunctionFactory.Create(GetWorkflowStatusAsync),
                            AIFunctionFactory.Create(SubmitHumanFeedbackAsync),
                        ]);
                });
            },
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

// Get the agent proxy from services
IServiceProvider services = host.Services;
AIAgent? agentProxy = services.GetKeyedService<AIAgent>(PublisherAgentName);
if (agentProxy == null)
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.Error.WriteLine("Agent 'Publisher' not found.");
    Console.ResetColor();
    Environment.Exit(1);
    return;
}

// Console colors for better UX
Console.ForegroundColor = ConsoleColor.Cyan;
Console.WriteLine("=== Long Running Tools Sample ===");
Console.ResetColor();
Console.WriteLine("Enter a topic for the Publisher agent to write about (or 'exit' to quit):");
Console.WriteLine();

// Create a session for the conversation
AgentSession session = await agentProxy.CreateSessionAsync();

using CancellationTokenSource cts = new();
Console.CancelKeyPress += (sender, e) =>
{
    e.Cancel = true;
    cts.Cancel();
};

while (!cts.Token.IsCancellationRequested)
{
    // Read input from stdin
    Console.ForegroundColor = ConsoleColor.Yellow;
    Console.Write("You: ");
    Console.ResetColor();

    string? input = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(input) || input.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    // Run the agent
    Console.ForegroundColor = ConsoleColor.Green;
    Console.Write("Publisher: ");
    Console.ResetColor();

    try
    {
        AgentResponse agentResponse = await agentProxy.RunAsync(
            message: input,
            session: session,
            cancellationToken: cts.Token);

        Console.WriteLine(agentResponse.Text);
        Console.WriteLine();
    }
    catch (Exception ex)
    {
        Console.ForegroundColor = ConsoleColor.Red;
        Console.Error.WriteLine($"Error: {ex.Message}");
        Console.ResetColor();
        Console.WriteLine();
    }

    Console.WriteLine("(Press Enter to prompt the Publisher agent again)");
    _ = Console.ReadLine();
}

await host.StopAsync();
