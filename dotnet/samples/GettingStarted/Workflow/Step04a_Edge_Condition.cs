// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Workflow;

/// <summary>
/// This class demonstrates the use of edge conditions in a workflow. By providing conditions
/// on the edges, the workflow can route messages according to the conditions defined for each edge.
/// In this sample, we are creating a simple automatic email response workflow. There is a spam
/// detection agent that intelligently analyzes incoming emails and classifies them as spam or not.
/// Based on the classification, the email will either be handled by the HandleSpamExecutor
/// or routed to the EmailAssistantExecutor, after which the reply will be sent to the SendEmailExecutor
/// for final delivery.
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
        // If it's not a spam, the result will be routed to the email assistant
        builder.AddEdge(spamDetectionAgent, emailAssistantAgent, condition: GetCondition(expectedResult: false));
        // After the email assistant writes a response, it will be sent to the send email executor
        builder.AddEdge(emailAssistantAgent, sendEmailExecutor);
        // If it's spam, the result will be routed to the handle spam executor
        builder.AddEdge(spamDetectionAgent, handleSpamExecutor, condition: GetCondition(expectedResult: true));
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

    /// <summary>
    /// Represents the result of spam detection.
    /// </summary>
    public sealed class DetectionResult
    {
        [JsonPropertyName("is_spam")]
        public bool IsSpam { get; set; }

        [JsonPropertyName("reason")]
        public string Reason { get; set; } = string.Empty;

        [JsonPropertyName("email_content")]
        public string EmailContent { get; set; } = string.Empty;
    }

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
