// Copyright (c) Microsoft. All rights reserved.
// Description: Conditional routing between workflow steps using edge conditions.
// Docs: https://learn.microsoft.com/agent-framework/workflows/overview

using System.Text.Json;
using System.Text.Json.Serialization;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowSamples.Branching;

// <branching_workflow>
/// <summary>
/// Demonstrates conditional routing using edge conditions.
/// An email spam detection system routes emails to different paths:
/// - Legitimate emails → Email Assistant → Send Email
/// - Spam emails → Handle Spam
/// </summary>
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

        // Build the workflow with conditional edges
        var workflow = new WorkflowBuilder(spamDetectionExecutor)
            .AddEdge(spamDetectionExecutor, emailAssistantExecutor, condition: GetCondition(expectedResult: false))
            .AddEdge(emailAssistantExecutor, sendEmailExecutor)
            .AddEdge(spamDetectionExecutor, handleSpamExecutor, condition: GetCondition(expectedResult: true))
            .WithOutputFrom(handleSpamExecutor, sendEmailExecutor)
            .Build();

        // Execute the workflow
        string email = "Subject: You won $1,000,000! Click here to claim your prize!";
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, new ChatMessage(ChatRole.User, email));
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is WorkflowOutputEvent outputEvent)
            {
                Console.WriteLine($"{outputEvent}");
            }
        }
    }

    private static Func<object?, bool> GetCondition(bool expectedResult) =>
        detectionResult => detectionResult is DetectionResult result && result.IsSpam == expectedResult;

    private static ChatClientAgent GetSpamDetectionAgent(IChatClient chatClient) =>
        new(chatClient, new ChatClientAgentOptions()
        {
            ChatOptions = new()
            {
                Instructions = "You are a spam detection assistant that identifies spam emails.",
                ResponseFormat = ChatResponseFormat.ForJsonSchema<DetectionResult>()
            }
        });

    private static ChatClientAgent GetEmailAssistantAgent(IChatClient chatClient) =>
        new(chatClient, new ChatClientAgentOptions()
        {
            ChatOptions = new()
            {
                Instructions = "You are an email assistant that helps users draft responses to emails with professionalism.",
                ResponseFormat = ChatResponseFormat.ForJsonSchema<EmailResponse>()
            }
        });
}
// </branching_workflow>

// <branching_models>
public sealed class DetectionResult
{
    [JsonPropertyName("is_spam")]
    public bool IsSpam { get; set; }

    [JsonPropertyName("reason")]
    public string Reason { get; set; } = string.Empty;

    [JsonIgnore]
    public string EmailId { get; set; } = string.Empty;
}

internal sealed class Email
{
    [JsonPropertyName("email_id")]
    public string EmailId { get; set; } = string.Empty;

    [JsonPropertyName("email_content")]
    public string EmailContent { get; set; } = string.Empty;
}

public sealed class EmailResponse
{
    [JsonPropertyName("response")]
    public string Response { get; set; } = string.Empty;
}
// </branching_models>

// <branching_executors>
internal static class EmailStateConstants
{
    public const string EmailStateScope = "EmailState";
}

internal sealed class SpamDetectionExecutor : Executor<ChatMessage, DetectionResult>
{
    private readonly AIAgent _spamDetectionAgent;

    public SpamDetectionExecutor(AIAgent spamDetectionAgent) : base("SpamDetectionExecutor")
    {
        this._spamDetectionAgent = spamDetectionAgent;
    }

    public override async ValueTask<DetectionResult> HandleAsync(ChatMessage message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        var newEmail = new Email
        {
            EmailId = Guid.NewGuid().ToString("N"),
            EmailContent = message.Text
        };
        await context.QueueStateUpdateAsync(newEmail.EmailId, newEmail, scopeName: EmailStateConstants.EmailStateScope, cancellationToken);

        var response = await this._spamDetectionAgent.RunAsync(message, cancellationToken: cancellationToken);
        var detectionResult = JsonSerializer.Deserialize<DetectionResult>(response.Text);
        detectionResult!.EmailId = newEmail.EmailId;

        return detectionResult;
    }
}

internal sealed class EmailAssistantExecutor : Executor<DetectionResult, EmailResponse>
{
    private readonly AIAgent _emailAssistantAgent;

    public EmailAssistantExecutor(AIAgent emailAssistantAgent) : base("EmailAssistantExecutor")
    {
        this._emailAssistantAgent = emailAssistantAgent;
    }

    public override async ValueTask<EmailResponse> HandleAsync(DetectionResult message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateConstants.EmailStateScope, cancellationToken)
            ?? throw new InvalidOperationException("Email not found.");
        var response = await this._emailAssistantAgent.RunAsync(email.EmailContent, cancellationToken: cancellationToken);
        return JsonSerializer.Deserialize<EmailResponse>(response.Text)!;
    }
}

internal sealed class SendEmailExecutor() : Executor<EmailResponse>("SendEmailExecutor")
{
    public override async ValueTask HandleAsync(EmailResponse message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
        await context.YieldOutputAsync($"Email sent: {message.Response}", cancellationToken);
}

internal sealed class HandleSpamExecutor() : Executor<DetectionResult>("HandleSpamExecutor")
{
    public override async ValueTask HandleAsync(DetectionResult message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
        await context.YieldOutputAsync($"Email marked as spam: {message.Reason}", cancellationToken);
}
// </branching_executors>
