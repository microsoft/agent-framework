// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Workflow;

/// <summary>
/// This class demonstrates how to configure a workflow with switch-case logic using edges.
/// Building on top the previous examples, this workflow incorporates conditional branching
/// to handle different scenarios based on the spam detection results. More specifically,
/// a new "unknown" case is added to handle situations where the agent cannot determine if
/// an email is spam, in which case it will trigger the default case and route the email
/// to a new executor for special handling.
/// </summary>
public class Step04d_Multi_Selection_Edge_Group(ITestOutputHelper output) : WorkflowSample(output)
{
    private const string EmailStateScope = "EmailState";
    private const int LongEmailThreshold = 100;

    [Fact]
    public async Task RunAsync()
    {
        // Create agents
        AIAgent emailAnalysisAgent = GetEmailAnalysisAgent();
        AIAgent emailAssistantAgent = GetEmailAssistantAgent();
        AIAgent emailSummaryAgent = GetEmailSummaryAgent();

        // Create executors
        var emailAnalysisExecutor = new EmailAnalysisExecutor(emailAnalysisAgent);
        var emailAssistantExecutor = new EmailAssistantExecutor(emailAssistantAgent);
        var emailSummaryExecutor = new EmailSummaryExecutor(emailSummaryAgent);
        var sendEmailExecutor = new SendEmailExecutor();
        var handleSpamExecutor = new HandleSpamExecutor();
        var handleUnknownExecutor = new HandleUnknownExecutor();
        var databaseAccessExecutor = new DatabaseAccessExecutor();

        // Build the workflow
        WorkflowBuilder builder = new(emailAnalysisExecutor);
        builder.AddFanOutEdge(
            emailAnalysisExecutor,
            targets: [
                handleSpamExecutor,
                emailAssistantExecutor,
                emailSummaryExecutor,
                handleUnknownExecutor,
            ],
            partitioner: GetPartitioner()
        )
        // After the email assistant writes a response, it will be sent to the send email executor
        .AddEdge(emailAssistantExecutor, sendEmailExecutor)
        // Save the analysis result to the database if summary is not needed
        .AddEdge(
            emailAnalysisExecutor,
            databaseAccessExecutor,
            condition: analysisResult => analysisResult is AnalysisResult result && result.EmailLength <= LongEmailThreshold)
        // Save the analysis result to the database with summary
        .AddEdge(emailSummaryExecutor, databaseAccessExecutor);

        var workflow = builder.Build<ChatMessage>();

        // Execute the workflow
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, new ChatMessage(ChatRole.User, "Hello World!"));
        await run.TrySendMessageAsync(new TurnToken(emitEvents: true));
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is WorkflowCompletedEvent completedEvent)
            {
                Console.WriteLine($"{completedEvent}");
            }
        }
    }

    public enum SpamDecision
    {
        NotSpam,
        Spam,
        Unknown
    }

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

    private sealed class Email
    {
        [JsonPropertyName("email_id")]
        public string EmailId { get; set; } = string.Empty;

        [JsonPropertyName("email_content")]
        public string EmailContent { get; set; } = string.Empty;
    }

    private Func<object?, int, IEnumerable<int>> GetPartitioner()
    {
        return (analysisResult, targetCount) =>
        {
            if (analysisResult is AnalysisResult result)
            {
                if (result.spamDecision == SpamDecision.Spam)
                {
                    return [0]; // Route to spam handler
                }
                else if (result.spamDecision == SpamDecision.NotSpam)
                {
                    List<int> targets = [1]; // Route to the email assistant

                    if (result.EmailLength > LongEmailThreshold)
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

    private ChatClientAgent GetEmailAnalysisAgent()
    {
        string instructions = "You are a spam detection assistant that identifies spam emails.";
        var agentOptions = new ChatClientAgentOptions(instructions: instructions)
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormatJson.ForJsonSchema(
                    schema: AIJsonUtilities.CreateJsonSchema(typeof(AnalysisResult))
                )
            }
        };

        return new ChatClientAgent(GetAzureOpenAIChatClient(), agentOptions);
    }

    private sealed class EmailAnalysisExecutor : ReflectingExecutor<EmailAnalysisExecutor>, IMessageHandler<ChatMessage, AnalysisResult>
    {
        private readonly AIAgent _spamDetectionAgent;

        public EmailAnalysisExecutor(AIAgent spamDetectionAgent) : base("EmailAnalysisExecutor")
        {
            _spamDetectionAgent = spamDetectionAgent;
        }

        /// <summary>
        /// Simulate the detection of spam.
        /// </summary>
        public async ValueTask<AnalysisResult> HandleAsync(ChatMessage message, IWorkflowContext context)
        {
            // Generate a random email ID and store the email content
            var newEmail = new Email
            {
                EmailId = Guid.NewGuid().ToString(),
                EmailContent = message.Text
            };
            await context.QueueStateUpdateAsync<Email>(newEmail.EmailId, newEmail, scopeName: EmailStateScope);

            var response = await _spamDetectionAgent.RunAsync(message);
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

    private ChatClientAgent GetEmailAssistantAgent()
    {
        string instructions = "You are an email assistant that helps users draft responses to emails with professionalism.";
        var agentOptions = new ChatClientAgentOptions(instructions: instructions)
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormatJson.ForJsonSchema(
                    schema: AIJsonUtilities.CreateJsonSchema(typeof(EmailResponse))
                )
            }
        };

        return new ChatClientAgent(GetAzureOpenAIChatClient(), agentOptions);
    }

    private sealed class EmailAssistantExecutor : ReflectingExecutor<EmailAssistantExecutor>, IMessageHandler<AnalysisResult, EmailResponse>
    {
        private readonly AIAgent _emailAssistantAgent;

        public EmailAssistantExecutor(AIAgent emailAssistantAgent) : base("EmailAssistantExecutor")
        {
            _emailAssistantAgent = emailAssistantAgent;
        }

        public async ValueTask<EmailResponse> HandleAsync(AnalysisResult message, IWorkflowContext context)
        {
            if (message.spamDecision == SpamDecision.Spam)
            {
                throw new InvalidOperationException("This executor should only handle non-spam messages.");
            }

            // Retrieve the email content from the context
            var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateScope);

            var response = await _emailAssistantAgent.RunAsync(email!.EmailContent);
            var emailResponse = JsonSerializer.Deserialize<EmailResponse>(response.Text);

            return emailResponse!;
        }
    }

    private sealed class SendEmailExecutor() : ReflectingExecutor<SendEmailExecutor>("SendEmailExecutor"), IMessageHandler<EmailResponse>
    {
        /// <summary>
        /// Simulate the sending of an email.
        /// </summary>
        public async ValueTask HandleAsync(EmailResponse message, IWorkflowContext context)
        {
            await context.AddEventAsync(new WorkflowCompletedEvent($"Email sent: {message.Response}"));
        }
    }

    private sealed class HandleSpamExecutor() : ReflectingExecutor<HandleSpamExecutor>("HandleSpamExecutor"), IMessageHandler<AnalysisResult>
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

    private sealed class HandleUnknownExecutor() : ReflectingExecutor<HandleUnknownExecutor>("HandleUnknownExecutor"), IMessageHandler<AnalysisResult>
    {
        /// <summary>
        /// Simulate the handling of an unknown spam decision.
        /// </summary>
        public async ValueTask HandleAsync(AnalysisResult message, IWorkflowContext context)
        {
            if (message.spamDecision == SpamDecision.Unknown)
            {
                var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateScope);
                await context.AddEventAsync(new WorkflowCompletedEvent($"Email marked as unknown: {message.Reason}. Email content: {email?.EmailContent}"));
            }
            else
            {
                throw new InvalidOperationException("This executor should only handle unknown spam decisions.");
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

    private ChatClientAgent GetEmailSummaryAgent()
    {
        string instructions = "You are an assistant that helps users summarize emails.";
        var agentOptions = new ChatClientAgentOptions(instructions: instructions)
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormatJson.ForJsonSchema(
                    schema: AIJsonUtilities.CreateJsonSchema(typeof(EmailSummary))
                )
            }
        };

        return new ChatClientAgent(GetAzureOpenAIChatClient(), agentOptions);
    }

    private sealed class EmailSummaryExecutor : ReflectingExecutor<EmailSummaryExecutor>, IMessageHandler<AnalysisResult, AnalysisResult>
    {
        private readonly AIAgent _emailSummaryAgent;

        public EmailSummaryExecutor(AIAgent emailSummaryAgent) : base("EmailSummaryExecutor")
        {
            _emailSummaryAgent = emailSummaryAgent;
        }

        public async ValueTask<AnalysisResult> HandleAsync(AnalysisResult message, IWorkflowContext context)
        {
            var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateScope);
            var response = await _emailSummaryAgent.RunAsync(email!.EmailContent);

            var emailSummary = JsonSerializer.Deserialize<EmailSummary>(response.Text);
            message.EmailSummary = emailSummary!.Summary;

            return message;
        }
    }

    private sealed class DatabaseAccessExecutor() : ReflectingExecutor<DatabaseAccessExecutor>("DatabaseAccessExecutor"), IMessageHandler<AnalysisResult>
    {
        public async ValueTask HandleAsync(AnalysisResult message, IWorkflowContext context)
        {
            // 1. Save the email content
            var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateScope);
            await Task.Delay(100); // Simulate database access delay

            // 2. Save the analysis result
            await Task.Delay(100); // Simulate database access delay

            // Not using the `WorkflowCompletedEvent` because this is not the end of the workflow.
            // The end of the workflow is signaled by the `SendEmailExecutor` or the `HandleUnknownExecutor`.
            await context.AddEventAsync(new WorkflowEvent($"Email {message.EmailId} saved to database."));
        }
    }
}
