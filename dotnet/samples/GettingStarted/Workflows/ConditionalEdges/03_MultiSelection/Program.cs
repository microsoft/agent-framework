// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace WorkflowMultiSelectionSample;

/// <summary>
/// This sample introduces multi-selection routing where one executor can trigger multiple downstream executors.
///
/// Extending the switch-case pattern from the previous sample, the workflow can now
/// trigger multiple executors simultaneously when certain conditions are met.
///
/// Key features:
/// - For legitimate emails: triggers Email Assistant (always) + Email Summary (if email is long)
/// - For spam emails: triggers Handle Spam executor only
/// - For uncertain emails: triggers Handle Uncertain executor only
/// - Database logging happens for both short emails and summarized long emails
///
/// This pattern is powerful for workflows that need parallel processing based on data characteristics,
/// such as triggering different analytics pipelines or multiple notification systems.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// - Shared state is used in this sample to persist email data between executors.
/// - An Azure OpenAI chat completion deployment that supports structured outputs must be configured.
/// </remarks>
public static class Program
{
    private const int LongEmailThreshold = 100;

    private static async Task Main()
    {
        // Set up the Azure OpenAI client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName).AsIChatClient();

        // Create agents
        AIAgent emailAnalysisAgent = GetEmailAnalysisAgent(chatClient);
        AIAgent emailAssistantAgent = GetEmailAssistantAgent(chatClient);
        AIAgent emailSummaryAgent = GetEmailSummaryAgent(chatClient);

        // Create executors
        var emailAnalysisExecutor = new EmailAnalysisExecutor(emailAnalysisAgent);
        var emailAssistantExecutor = new EmailAssistantExecutor(emailAssistantAgent);
        var emailSummaryExecutor = new EmailSummaryExecutor(emailSummaryAgent);
        var sendEmailExecutor = new SendEmailExecutor();
        var handleSpamExecutor = new HandleSpamExecutor();
        var handleUncertainExecutor = new HandleUncertainExecutor();
        var databaseAccessExecutor = new DatabaseAccessExecutor();

        // Build the workflow by adding executors and connecting them
        WorkflowBuilder builder = new(emailAnalysisExecutor);
        builder.AddFanOutEdge(
            emailAnalysisExecutor,
            targets: [
                handleSpamExecutor,
                emailAssistantExecutor,
                emailSummaryExecutor,
                handleUncertainExecutor,
            ],
            partitioner: GetPartitioner()
        )
        // After the email assistant writes a response, it will be sent to the send email executor
        .AddEdge(emailAssistantExecutor, sendEmailExecutor)
        // Save the analysis result to the database if summary is not needed
        .AddEdge<AnalysisResult>(
            emailAnalysisExecutor,
            databaseAccessExecutor,
            condition: analysisResult => analysisResult?.EmailLength <= LongEmailThreshold)
        // Save the analysis result to the database with summary
        .AddEdge(emailSummaryExecutor, databaseAccessExecutor);
        var workflow = builder.Build<ChatMessage>();

        // Read a email from a text file
        string email = Resources.Read("email.txt");

        // Execute the workflow
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, new ChatMessage(ChatRole.User, email));
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is WorkflowCompletedEvent completedEvent)
            {
                Console.WriteLine($"{completedEvent}");
            }

            if (evt is DatabaseEvent databaseEvent)
            {
                Console.WriteLine($"{databaseEvent}");
            }
        }
    }

    /// <summary>
    /// Creates a partitioner for routing messages based on the analysis result.
    /// </summary>
    /// <returns>A function that takes an analysis result and returns the target partitions.</returns>
    private static Func<AnalysisResult?, int, IEnumerable<int>> GetPartitioner()
    {
        return (analysisResult, targetCount) =>
        {
            if (analysisResult is not null)
            {
                if (analysisResult.spamDecision == SpamDecision.Spam)
                {
                    return [0]; // Route to spam handler
                }
                else if (analysisResult.spamDecision == SpamDecision.NotSpam)
                {
                    List<int> targets = [1]; // Route to the email assistant

                    if (analysisResult.EmailLength > LongEmailThreshold)
                    {
                        targets.Add(2); // Route to the email summarizer too
                    }

                    return targets;
                }
                else
                {
                    return [3];
                }
            }
            throw new InvalidOperationException("Invalid analysis result.");
        };
    }

    /// <summary>
    /// Create an email analysis agent.
    /// </summary>
    /// <returns>A ChatClientAgent configured for email analysis</returns>
    private static ChatClientAgent GetEmailAnalysisAgent(IChatClient chatClient) =>
        new(chatClient, new ChatClientAgentOptions(instructions: "You are a spam detection assistant that identifies spam emails.")
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormat.ForJsonSchema(AIJsonUtilities.CreateJsonSchema(typeof(AnalysisResult)))
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

    /// <summary>
    /// Creates an agent that summarizes emails.
    /// </summary>
    /// <returns>A ChatClientAgent configured for email summarization</returns>
    private static ChatClientAgent GetEmailSummaryAgent(IChatClient chatClient) =>
        new(chatClient, new ChatClientAgentOptions(instructions: "You are an assistant that helps users summarize emails.")
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormat.ForJsonSchema(AIJsonUtilities.CreateJsonSchema(typeof(EmailSummary)))
            }
        });
}

internal static class EmailStateConstants
{
    public const string EmailStateScope = "EmailState";
}

/// <summary>
/// Represents the possible decisions for spam detection.
/// </summary>
public enum SpamDecision
{
    NotSpam,
    Spam,
    Uncertain
}

/// <summary>
/// Represents the result of email analysis.
/// </summary>
public sealed class AnalysisResult
{
    [JsonPropertyName("spam_decision")]
    [JsonConverter(typeof(JsonStringEnumConverter))]
    public SpamDecision spamDecision { get; set; }

    [JsonPropertyName("reason")]
    public string Reason { get; set; } = string.Empty;

    [JsonIgnore]
    public int EmailLength { get; set; }

    [JsonIgnore]
    public string EmailSummary { get; set; } = string.Empty;

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
/// Executor that analyzes emails using an AI agent.
/// </summary>
internal sealed class EmailAnalysisExecutor : ReflectingExecutor<EmailAnalysisExecutor>, IMessageHandler<ChatMessage, AnalysisResult>
{
    private readonly AIAgent _emailAnalysisAgent;

    /// <summary>
    /// Creates a new instance of the <see cref="EmailAnalysisExecutor"/> class.
    /// </summary>
    /// <param name="emailAnalysisAgent">The AI agent used for email analysis</param>
    public EmailAnalysisExecutor(AIAgent emailAnalysisAgent) : base("EmailAnalysisExecutor")
    {
        this._emailAnalysisAgent = emailAnalysisAgent;
    }

    public async ValueTask<AnalysisResult> HandleAsync(ChatMessage message, IWorkflowContext context)
    {
        // Generate a random email ID and store the email content
        var newEmail = new Email
        {
            EmailId = Guid.NewGuid().ToString(),
            EmailContent = message.Text
        };
        await context.QueueStateUpdateAsync(newEmail.EmailId, newEmail, scopeName: EmailStateConstants.EmailStateScope);

        // Invoke the agent
        var response = await this._emailAnalysisAgent.RunAsync(message);
        var AnalysisResult = JsonSerializer.Deserialize<AnalysisResult>(response.Text);

        AnalysisResult!.EmailId = newEmail.EmailId;
        AnalysisResult!.EmailLength = newEmail.EmailContent.Length;

        return AnalysisResult;
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
internal sealed class EmailAssistantExecutor : ReflectingExecutor<EmailAssistantExecutor>, IMessageHandler<AnalysisResult, EmailResponse>
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

    public async ValueTask<EmailResponse> HandleAsync(AnalysisResult message, IWorkflowContext context)
    {
        if (message.spamDecision == SpamDecision.Spam)
        {
            throw new InvalidOperationException("This executor should only handle non-spam messages.");
        }

        // Retrieve the email content from the context
        var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateConstants.EmailStateScope);

        // Invoke the agent
        var response = await this._emailAssistantAgent.RunAsync(email!.EmailContent);
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
internal sealed class HandleSpamExecutor() : ReflectingExecutor<HandleSpamExecutor>("HandleSpamExecutor"), IMessageHandler<AnalysisResult>
{
    /// <summary>
    /// Simulate the handling of a spam message.
    /// </summary>
    public async ValueTask HandleAsync(AnalysisResult message, IWorkflowContext context)
    {
        if (message.spamDecision == SpamDecision.Spam)
        {
            await context.AddEventAsync(new WorkflowCompletedEvent($"Email marked as spam: {message.Reason}"));
        }
        else
        {
            throw new InvalidOperationException("This executor should only handle spam messages.");
        }
    }
}

/// <summary>
/// Executor that handles uncertain messages.
/// </summary>
internal sealed class HandleUncertainExecutor() : ReflectingExecutor<HandleUncertainExecutor>("HandleUncertainExecutor"), IMessageHandler<AnalysisResult>
{
    /// <summary>
    /// Simulate the handling of an uncertain spam decision.
    /// </summary>
    public async ValueTask HandleAsync(AnalysisResult message, IWorkflowContext context)
    {
        if (message.spamDecision == SpamDecision.Uncertain)
        {
            var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateConstants.EmailStateScope);
            await context.AddEventAsync(new WorkflowCompletedEvent($"Email marked as uncertain: {message.Reason}. Email content: {email?.EmailContent}"));
        }
        else
        {
            throw new InvalidOperationException("This executor should only handle uncertain spam decisions.");
        }
    }
}

/// <summary>
/// Represents the response from the email summary agent.
/// </summary>
public sealed class EmailSummary
{
    [JsonPropertyName("summary")]
    public string Summary { get; set; } = string.Empty;
}

/// <summary>
/// Executor that summarizes emails using an AI agent.
/// </summary>
internal sealed class EmailSummaryExecutor : ReflectingExecutor<EmailSummaryExecutor>, IMessageHandler<AnalysisResult, AnalysisResult>
{
    private readonly AIAgent _emailSummaryAgent;

    /// <summary>
    /// Creates a new instance of the <see cref="EmailSummaryExecutor"/> class.
    /// </summary>
    /// <param name="emailSummaryAgent">The AI agent used for email summarization</param>
    public EmailSummaryExecutor(AIAgent emailSummaryAgent) : base("EmailSummaryExecutor")
    {
        this._emailSummaryAgent = emailSummaryAgent;
    }

    public async ValueTask<AnalysisResult> HandleAsync(AnalysisResult message, IWorkflowContext context)
    {
        // Read the email content from the shared states
        var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateConstants.EmailStateScope);

        // Invoke the agent
        var response = await this._emailSummaryAgent.RunAsync(email!.EmailContent);
        var emailSummary = JsonSerializer.Deserialize<EmailSummary>(response.Text);
        message.EmailSummary = emailSummary!.Summary;

        return message;
    }
}

/// <summary>
/// A custom workflow event for database operations.
/// </summary>
/// <param name="message">The message associated with the event</param>
internal sealed class DatabaseEvent(string message) : WorkflowEvent(message) { }

/// <summary>
/// Executor that handles database access.
/// </summary>
internal sealed class DatabaseAccessExecutor() : ReflectingExecutor<DatabaseAccessExecutor>("DatabaseAccessExecutor"), IMessageHandler<AnalysisResult>
{
    public async ValueTask HandleAsync(AnalysisResult message, IWorkflowContext context)
    {
        // 1. Save the email content
        await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateConstants.EmailStateScope);
        await Task.Delay(100); // Simulate database access delay

        // 2. Save the analysis result
        await Task.Delay(100); // Simulate database access delay

        // Not using the `WorkflowCompletedEvent` because this is not the end of the workflow.
        // The end of the workflow is signaled by the `SendEmailExecutor` or the `HandleUnknownExecutor`.
        await context.AddEventAsync(new DatabaseEvent($"Email {message.EmailId} saved to database."));
    }
}
