// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Samples;

namespace Workflow;

/// <summary>
/// This sample demonstrates advanced conditional routing using switch-case logic for complex decision trees.
///
/// Building on the previous email automation examples, this workflow adds a third decision path
/// to handle ambiguous cases where spam detection is uncertain. Now the workflow can route emails
/// three ways based on the detection result:
///
/// 1. ✅ Not Spam → Email Assistant → Send Email
/// 2. ❌ Spam → Handle Spam Executor
/// 3. ❓ Uncertain → Handle Uncertain Executor (default case)
///
/// The switch-case pattern provides cleaner syntax than multiple individual edge conditions,
/// especially when dealing with multiple possible outcomes. This approach scales well for
/// workflows that need to handle many different scenarios.
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
        var handleUncertainExecutor = new HandleUncertainExecutor();

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
                handleUncertainExecutor
            )
        )
        // After the email assistant writes a response, it will be sent to the send email executor
        .AddEdge(emailAssistantExecutor, sendEmailExecutor);
        var workflow = builder.Build<ChatMessage>();

        // Read a email from a text file
        string email = Resources.Read("ambiguous_email.txt");

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
    /// Represents the possible decisions for spam detection.
    /// </summary>
    public enum SpamDecision
    {
        NotSpam,
        Spam,
        Uncertain
    }

    /// <summary>
    /// Represents the result of spam detection.
    /// </summary>
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

    /// <summary>
    /// Represents an email.
    /// </summary>
    private sealed class Email
    {
        [JsonPropertyName("email_id")]
        public string EmailId { get; set; } = string.Empty;

        [JsonPropertyName("email_content")]
        public string EmailContent { get; set; } = string.Empty;
    }

    /// <summary>
    /// Creates a condition for routing messages based on the expected spam detection result.
    /// </summary>
    /// <param name="expectedDecision">The expected spam detection decision</param>
    /// <returns>A function that evaluates whether a message meets the expected result</returns>
    private Func<object?, bool> GetCondition(SpamDecision expectedDecision)
    {
        return detectionResult =>
        {
            return detectionResult is DetectionResult result && result.spamDecision == expectedDecision;
        };
    }

    /// <summary>
    /// Creates a spam detection agent.
    /// </summary>
    /// <returns>A ChatClientAgent configured for spam detection</returns>
    private ChatClientAgent GetSpamDetectionAgent()
    {
        string instructions = "You are a spam detection assistant that identifies spam emails. Be less confident in your assessments.";
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

    /// <summary>
    /// Executor that detects spam using an AI agent.
    /// </summary>
    private sealed class SpamDetectionExecutor : ReflectingExecutor<SpamDetectionExecutor>, IMessageHandler<ChatMessage, DetectionResult>
    {
        private readonly AIAgent _spamDetectionAgent;

        /// <summary>
        /// Creates a new instance of the <see cref="SpamDetectionExecutor"/> class.
        /// </summary>
        /// <param name="spamDetectionAgent">The AI agent used for spam detection</param>
        public SpamDetectionExecutor(AIAgent spamDetectionAgent) : base("SpamDetectionExecutor")
        {
            _spamDetectionAgent = spamDetectionAgent;
        }

        public async ValueTask<DetectionResult> HandleAsync(ChatMessage message, IWorkflowContext context)
        {
            // Generate a random email ID and store the email content
            var newEmail = new Email
            {
                EmailId = Guid.NewGuid().ToString(),
                EmailContent = message.Text
            };
            await context.QueueStateUpdateAsync<Email>(newEmail.EmailId, newEmail, scopeName: EmailStateScope);

            // Invoke the agent
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

    /// <summary>
    /// Creates an email assistant agent.
    /// </summary>
    /// <returns>A ChatClientAgent configured for email assistance</returns>
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

    /// <summary>
    /// Executor that assists with email responses using an AI agent.
    /// </summary>
    private sealed class EmailAssistantExecutor : ReflectingExecutor<EmailAssistantExecutor>, IMessageHandler<DetectionResult, EmailResponse>
    {
        private readonly AIAgent _emailAssistantAgent;

        /// <summary>
        /// Creates a new instance of the <see cref="EmailAssistantExecutor"/> class.
        /// </summary>
        /// <param name="emailAssistantAgent">The AI agent used for email assistance</param>
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

            // Invoke the agent
            var response = await _emailAssistantAgent.RunAsync(email!.EmailContent);
            var emailResponse = JsonSerializer.Deserialize<EmailResponse>(response.Text);

            return emailResponse!;
        }
    }

    /// <summary>
    /// Executor that sends emails.
    /// </summary>
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

    /// <summary>
    /// Executor that handles spam messages.
    /// </summary>
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

    /// <summary>
    /// Executor that handles uncertain emails.
    /// </summary>
    private sealed class HandleUncertainExecutor() : ReflectingExecutor<HandleUncertainExecutor>("HandleUncertainExecutor"), IMessageHandler<DetectionResult>
    {
        /// <summary>
        /// Simulate the handling of an uncertain spam decision.
        /// </summary>
        public async ValueTask HandleAsync(DetectionResult message, IWorkflowContext context)
        {
            if (message.spamDecision == SpamDecision.Uncertain)
            {
                var email = await context.ReadStateAsync<Email>(message.EmailId, scopeName: EmailStateScope);
                await context.AddEventAsync(new WorkflowCompletedEvent($"Email marked as uncertain: {message.Reason}. Email content: {email?.EmailContent}"));
            }
            else
            {
                throw new InvalidOperationException("This executor should only handle uncertain spam decisions.");
            }
        }
    }
}
