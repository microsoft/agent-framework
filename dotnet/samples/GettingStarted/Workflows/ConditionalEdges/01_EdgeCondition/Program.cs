// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace WorkflowEdgeConditionSample;

/// <summary>
/// This sample introduces conditional routing using edge conditions to create decision-based workflows.
///
/// This workflow creates an automated email response system that routes emails down different paths based
/// on spam detection results:
///
/// 1. Spam Detection Agent analyzes incoming emails and classifies them as spam or legitimate
/// 2. Based on the classification:
///    - Legitimate emails → Email Assistant Agent → Send Email Executor
///    - Spam emails → Handle Spam Executor (marks as spam)
///
/// Edge conditions enable workflows to make intelligent routing decisions, allowing you to
/// build sophisticated automation that responds differently based on the data being processed.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// - Shared state is used in this sample to persist email data between executors.
/// - An Azure OpenAI chat completion deployment that supports structured outputs must be configured.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Set up the Azure OpenAI client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName).AsIChatClient();

        // Create agents
        AIAgent spamDetectionAgent = GetSpamDetectionAgent(chatClient);
        AIAgent emailAssistantAgent = GetEmailAssistantAgent(chatClient);

        // Create executors
        var spamDetectionExecutor = new SpamDetectionExecutor(spamDetectionAgent);
        var emailAssistantExecutor = new EmailAssistantExecutor(emailAssistantAgent);
        var sendEmailExecutor = new SendEmailExecutor();
        var handleSpamExecutor = new HandleSpamExecutor();

        // Build the workflow by adding executors and connecting them
        var workflow = new WorkflowBuilder(spamDetectionExecutor)
            .AddEdge(spamDetectionExecutor, emailAssistantExecutor, condition: GetCondition(expectedResult: false))
            .AddEdge(emailAssistantExecutor, sendEmailExecutor)
            .AddEdge(spamDetectionExecutor, handleSpamExecutor, condition: GetCondition(expectedResult: true))
            .Build<ChatMessage>();

        // Read a email from a text file
        string email = Resources.Read("spam.txt");

        // Execute the workflow
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, new ChatMessage(ChatRole.User, email));
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is WorkflowCompletedEvent completedEvent)
            {
                Console.WriteLine($"{completedEvent}");
            }
        }
    }

    /// <summary>
    /// Creates a condition for routing messages based on the expected spam detection result.
    /// </summary>
    /// <param name="expectedResult">The expected spam detection result</param>
    /// <returns>A function that evaluates whether a message meets the expected result</returns>
    private static Func<object?, bool> GetCondition(bool expectedResult) =>
        detectionResult => detectionResult is DetectionResult result && result.IsSpam == expectedResult;

    /// <summary>
    /// Creates a spam detection agent.
    /// </summary>
    /// <returns>A ChatClientAgent configured for spam detection</returns>
    private static ChatClientAgent GetSpamDetectionAgent(IChatClient chatClient) =>
        new(chatClient, new ChatClientAgentOptions(instructions: "You are a spam detection assistant that identifies spam emails.")
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormat.ForJsonSchema(AIJsonUtilities.CreateJsonSchema(typeof(DetectionResult)))
            }
        });

    /// <summary>
    /// Creates an email assistant agent.
    /// </summary>
    /// <returns>A ChatClientAgent configured for email assistance</returns>
    private static ChatClientAgent GetEmailAssistantAgent(IChatClient chatClient) =>
        new(chatClient, new ChatClientAgentOptions(instructions: "You are an email assistant that helps users draft responses to emails with professionalism.")
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormat.ForJsonSchema(AIJsonUtilities.CreateJsonSchema(typeof(EmailResponse)))
            }
        });
}

/// <summary>
/// Constants for shared state scopes.
/// </summary>
internal static class EmailStateConstants
{
    public const string EmailStateScope = "EmailState";
}

/// <summary>
/// Represents the result of spam detection.
/// </summary>
public sealed class DetectionResult
{
    [JsonPropertyName("is_spam")]
    public bool IsSpam { get; set; }

    [JsonPropertyName("reason")]
    public string Reason { get; set; } = string.Empty;

    // Email ID is generated by the executor not the agent
    [JsonIgnore]
    public string EmailId { get; set; } = string.Empty;
}

/// <summary>
/// Represents an email.
/// </summary>
internal sealed class Email
{
    [JsonPropertyName("email_id")]
    public string EmailId { get; set; } = string.Empty;

    [JsonPropertyName("email_content")]
    public string EmailContent { get; set; } = string.Empty;
}

/// <summary>
/// Executor that detects spam using an AI agent.
/// </summary>
internal sealed class SpamDetectionExecutor : ReflectingExecutor<SpamDetectionExecutor>, IMessageHandler<ChatMessage, DetectionResult>
{
    private readonly AIAgent _spamDetectionAgent;

    /// <summary>
    /// Creates a new instance of the <see cref="SpamDetectionExecutor"/> class.
    /// </summary>
    /// <param name="spamDetectionAgent">The AI agent used for spam detection</param>
    public SpamDetectionExecutor(AIAgent spamDetectionAgent) : base("SpamDetectionExecutor")
    {
        this._spamDetectionAgent = spamDetectionAgent;
    }

    public async ValueTask<DetectionResult> HandleAsync(ChatMessage message, IWorkflowContext context)
    {
        // Generate a random email ID and store the email content to the shared state
        var newEmail = new Email
        {
            EmailId = Guid.NewGuid().ToString(),
            EmailContent = message.Text
        };
        await context.QueueStateUpdateAsync(newEmail.EmailId, newEmail, scopeName: EmailStateConstants.EmailStateScope);

        // Invoke the agent
        var response = await this._spamDetectionAgent.RunAsync(message);
        var detectionResult = JsonSerializer.Deserialize<DetectionResult>(response.Text);

        detectionResult!.EmailId = newEmail.EmailId;

        return detectionResult;
    }
}

/// <summary>
/// Represents the response from the email assistant.
/// </summary>
public sealed class EmailResponse
{
    [JsonPropertyName("response")]
    public string Response { get; set; } = string.Empty;
}

/// <summary>
/// Executor that assists with email responses using an AI agent.
/// </summary>
internal sealed class EmailAssistantExecutor : ReflectingExecutor<EmailAssistantExecutor>, IMessageHandler<DetectionResult, EmailResponse>
{
    private readonly AIAgent _emailAssistantAgent;

    /// <summary>
    /// Creates a new instance of the <see cref="EmailAssistantExecutor"/> class.
    /// </summary>
    /// <param name="emailAssistantAgent">The AI agent used for email assistance</param>
    public EmailAssistantExecutor(AIAgent emailAssistantAgent) : base("EmailAssistantExecutor")
    {
        this._emailAssistantAgent = emailAssistantAgent;
    }

    public async ValueTask<EmailResponse> HandleAsync(DetectionResult message, IWorkflowContext context)
    {
        if (message.IsSpam)
        {
            throw new InvalidOperationException("This executor should only handle non-spam messages.");
        }

        // Retrieve the email content from the shared state
        var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateConstants.EmailStateScope)
            ?? throw new InvalidOperationException("Email not found.");

        // Invoke the agent
        var response = await this._emailAssistantAgent.RunAsync(email.EmailContent);
        var emailResponse = JsonSerializer.Deserialize<EmailResponse>(response.Text);

        return emailResponse!;
    }
}

/// <summary>
/// Executor that sends emails.
/// </summary>
internal sealed class SendEmailExecutor() : ReflectingExecutor<SendEmailExecutor>("SendEmailExecutor"), IMessageHandler<EmailResponse>
{
    /// <summary>
    /// Simulate the sending of an email.
    /// </summary>
    public async ValueTask HandleAsync(EmailResponse message, IWorkflowContext context) =>
        await context.AddEventAsync(new WorkflowCompletedEvent($"Email sent: {message.Response}"));
}

/// <summary>
/// Executor that handles spam messages.
/// </summary>
internal sealed class HandleSpamExecutor() : ReflectingExecutor<HandleSpamExecutor>("HandleSpamExecutor"), IMessageHandler<DetectionResult>
{
    /// <summary>
    /// Simulate the handling of a spam message.
    /// </summary>
    public async ValueTask HandleAsync(DetectionResult message, IWorkflowContext context)
    {
        if (message.IsSpam)
        {
            await context.AddEventAsync(new WorkflowCompletedEvent($"Email marked as spam: {message.Reason}"));
        }
        else
        {
            throw new InvalidOperationException("This executor should only handle spam messages.");
        }
    }
}
