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
public class Step04c_Switch_Case_Edge_Group(ITestOutputHelper output) : WorkflowSample(output)
{
    private const string EmailStateScope = "EmailState";

    [Fact]
    public async Task RunAsync()
    {
        // Create agents
        AIAgent spamDetectionAgent = GetSpamDetectionAgent();
        AIAgent emailAssistantAgent = GetEmailAssistantAgent();

        // Create executors
        var spamDetectionExecutor = new SpamDetectionExecutor(spamDetectionAgent);
        var emailAssistantExecutor = new EmailAssistantExecutor(emailAssistantAgent);
        var sendEmailExecutor = new SendEmailExecutor();
        var handleSpamExecutor = new HandleSpamExecutor();
        var handleUnknownExecutor = new HandleUnknownExecutor();

        // Build the workflow
        WorkflowBuilder builder = new(spamDetectionExecutor);
        builder.AddSwitch(spamDetectionExecutor, switchBuilder =>
            switchBuilder
            .AddCase(
                GetCondition(expectedDecision: SpamDecision.NotSpam),
                emailAssistantExecutor
            )
            .AddCase(
                GetCondition(expectedDecision: SpamDecision.Spam),
                handleSpamExecutor
            )
            .WithDefault(
                handleUnknownExecutor
            )
        )
        // After the email assistant writes a response, it will be sent to the send email executor
        .AddEdge(emailAssistantExecutor, sendEmailExecutor);

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

    public sealed class DetectionResult
    {
        [JsonPropertyName("spam_decision")]
        [JsonConverter(typeof(JsonStringEnumConverter))]
        public SpamDecision spamDecision { get; set; }

        [JsonPropertyName("reason")]
        public string Reason { get; set; } = string.Empty;

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

    private Func<object?, bool> GetCondition(SpamDecision expectedDecision)
    {
        return detectionResult =>
        {
            return detectionResult is DetectionResult result && result.spamDecision == expectedDecision;
        };
    }

    private ChatClientAgent GetSpamDetectionAgent()
    {
        string instructions = "You are a spam detection assistant that identifies spam emails.";
        var agentOptions = new ChatClientAgentOptions(instructions: instructions)
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormatJson.ForJsonSchema(
                    schema: AIJsonUtilities.CreateJsonSchema(typeof(DetectionResult))
                )
            }
        };

        return new ChatClientAgent(GetAzureOpenAIChatClient(), agentOptions);
    }

    private sealed class SpamDetectionExecutor : ReflectingExecutor<SpamDetectionExecutor>, IMessageHandler<ChatMessage, DetectionResult>
    {
        private readonly AIAgent _spamDetectionAgent;

        public SpamDetectionExecutor(AIAgent spamDetectionAgent) : base("SpamDetectionExecutor")
        {
            _spamDetectionAgent = spamDetectionAgent;
        }

        /// <summary>
        /// Simulate the detection of spam.
        /// </summary>
        public async ValueTask<DetectionResult> HandleAsync(ChatMessage message, IWorkflowContext context)
        {
            // Generate a random email ID and store the email content
            var newEmail = new Email
            {
                EmailId = Guid.NewGuid().ToString(),
                EmailContent = message.Text
            };
            await context.QueueStateUpdateAsync<Email>(newEmail.EmailId, newEmail, scopeName: EmailStateScope);

            var response = await _spamDetectionAgent.RunAsync(message);
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

    private sealed class EmailAssistantExecutor : ReflectingExecutor<EmailAssistantExecutor>, IMessageHandler<DetectionResult, EmailResponse>
    {
        private readonly AIAgent _emailAssistantAgent;

        public EmailAssistantExecutor(AIAgent emailAssistantAgent) : base("EmailAssistantExecutor")
        {
            _emailAssistantAgent = emailAssistantAgent;
        }

        public async ValueTask<EmailResponse> HandleAsync(DetectionResult message, IWorkflowContext context)
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

    private sealed class HandleSpamExecutor() : ReflectingExecutor<HandleSpamExecutor>("HandleSpamExecutor"), IMessageHandler<DetectionResult>
    {
        /// <summary>
        /// Simulate the handling of a spam message.
        /// </summary>
        public async ValueTask HandleAsync(DetectionResult message, IWorkflowContext context)
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

    private sealed class HandleUnknownExecutor() : ReflectingExecutor<HandleUnknownExecutor>("HandleUnknownExecutor"), IMessageHandler<DetectionResult>
    {
        /// <summary>
        /// Simulate the handling of an unknown spam decision.
        /// </summary>
        public async ValueTask HandleAsync(DetectionResult message, IWorkflowContext context)
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
}
