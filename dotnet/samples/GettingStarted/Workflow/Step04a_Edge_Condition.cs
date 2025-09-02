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
/// This sample demonstrates conditional routing using edge conditions to create decision-based workflows.
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
public class Step04a_Edge_Condition(ITestOutputHelper output) : WorkflowSample(output)
{
    [Fact]
    public async Task RunAsync()
    {
        // Create agents
        AIAgent spamDetectionAgent = GetSpamDetectionAgent();
        AIAgent emailAssistantAgent = GetEmailAssistantAgent();

        // Create executors
        var sendEmailExecutor = new SendEmailExecutor();
        var handleSpamExecutor = new HandleSpamExecutor();

        // Build the workflow
        WorkflowBuilder builder = new(spamDetectionAgent);
        builder.AddEdge(spamDetectionAgent, emailAssistantAgent, condition: GetCondition(expectedResult: false));
        builder.AddEdge(emailAssistantAgent, sendEmailExecutor);
        builder.AddEdge(spamDetectionAgent, handleSpamExecutor, condition: GetCondition(expectedResult: true));
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
        }
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

        // The agent has to include the email content in the detection result.
        // This is necessary for the email assistant to generate a proper response.
        [JsonPropertyName("email_content")]
        public string EmailContent { get; set; } = string.Empty;
    }

    /// <summary>
    /// Creates a condition for routing messages based on the expected spam detection result.
    /// </summary>
    /// <param name="expectedResult">The expected spam detection result</param>
    /// <returns>A function that evaluates whether a message meets the expected result</returns>
    private Func<object?, bool> GetCondition(bool expectedResult)
    {
        return message =>
        {
            if (message is not ChatMessage chatMessage)
            {
                // Allow turn token to pass through
                return true;
            }

            var detectionResult = JsonSerializer.Deserialize<DetectionResult>(chatMessage.Text);
            return detectionResult?.IsSpam == expectedResult;
        };
    }

    /// <summary>
    /// Creates a spam detection agent.
    /// </summary>
    /// <returns>A ChatClientAgent configured for spam detection</returns>
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
    /// Executor that sends the email.
    /// </summary>
    private sealed class SendEmailExecutor() : ReflectingExecutor<SendEmailExecutor>("SendEmailExecutor"), IMessageHandler<ChatMessage>
    {
        /// <summary>
        /// Simulate the sending of an email.
        /// </summary>
        public async ValueTask HandleAsync(ChatMessage message, IWorkflowContext context)
        {
            var emailResponse = JsonSerializer.Deserialize<EmailResponse>(message.Text);
            await context.AddEventAsync(new WorkflowCompletedEvent($"Email sent:\n{emailResponse?.Response}"));
        }
    }

    /// <summary>
    /// Executor that handles spam messages.
    /// </summary>
    private sealed class HandleSpamExecutor() : ReflectingExecutor<HandleSpamExecutor>("HandleSpamExecutor"), IMessageHandler<ChatMessage>
    {
        /// <summary>
        /// Simulate the handling of a spam message.
        /// </summary>
        public async ValueTask HandleAsync(ChatMessage message, IWorkflowContext context)
        {
            var detectionResult = JsonSerializer.Deserialize<DetectionResult>(message.Text);

            if (detectionResult?.IsSpam == true)
            {
                await context.AddEventAsync(new WorkflowCompletedEvent($"Email marked as spam: {detectionResult.Reason}"));
            }
            else
            {
                throw new InvalidOperationException("This executor should only handle spam messages.");
            }
        }
    }
}
