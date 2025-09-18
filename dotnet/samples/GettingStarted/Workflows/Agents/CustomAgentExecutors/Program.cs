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

namespace WorkflowCustomAgentExecutorsSample;

/// <summary>
/// This sample demonstrates how to create custom executors for AI agents.
/// This is useful when you want more control over the agent's behaviors in a workflow.
///
/// In this example, we create two custom executors:
/// 1. SloganWriterExecutor: An AI agent that generates slogans based on a given task.
/// 2. FeedbackExecutor: An AI agent that provides feedback on the generated slogans.
/// (These two executors manage the agent instances and their conversation threads.)
///
/// The workflow alternates between these two executors until the slogan meets a certain
/// quality threshold or a maximum number of attempts is reached.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
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

        // Create the executors
        var sloganWriter = new SloganWriterExecutor(chatClient);
        var feedbackProvider = new FeedbackExecutor(chatClient);

        // Build the workflow by adding executors and connecting them
        var workflow = new WorkflowBuilder(sloganWriter)
            .AddEdge(sloganWriter, feedbackProvider)
            .AddEdge(feedbackProvider, sloganWriter)
            .Build<string>();

        // Execute the workflow
        StreamingRun run = await InProcessExecution.StreamAsync(workflow, "Create a slogan for a new electric SUV that is affordable and fun to drive.");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is SloganGeneratedEvent or FeedbackEvent)
            {
                // Custom events to allow us to monitor the progress of the workflow.
                Console.WriteLine($"{evt}");
            }

            if (evt is WorkflowCompletedEvent completedEvent)
            {
                Console.WriteLine($"{completedEvent}");
            }
        }
    }
}

/// <summary>
/// A class representing the output of the slogan writer agent.
/// </summary>
public sealed class SloganResult
{
    [JsonPropertyName("task")]
    public required string Task { get; set; }

    [JsonPropertyName("slogan")]
    public required string Slogan { get; set; }
}

/// <summary>
/// A class representing the output of the feedback agent.
/// </summary>
public sealed class FeedbackResult
{
    [JsonPropertyName("comments")]
    public string Comments { get; set; } = string.Empty;

    [JsonPropertyName("rating")]
    public int Rating { get; set; }

    [JsonPropertyName("actions")]
    public string Actions { get; set; } = string.Empty;
}

/// <summary>
/// A custom event to indicate that a slogan has been generated.
/// </summary>
internal sealed class SloganGeneratedEvent(SloganResult sloganResult) : WorkflowEvent(sloganResult)
{
    public override string ToString() => $"Slogan: {sloganResult.Slogan}";
}

/// <summary>
/// A custom executor that uses an AI agent to generate slogans based on a given task.
/// Note that this executor has two message handlers:
/// 1. HandleAsync(string message): Handles the initial task to create a slogan.
/// 2. HandleAsync(Feedback message): Handles feedback to improve the slogan.
/// </summary>
internal sealed class SloganWriterExecutor
    : ReflectingExecutor<SloganWriterExecutor>,
      IMessageHandler<string, SloganResult>,
      IMessageHandler<FeedbackResult, SloganResult>
{
    private readonly AIAgent _agent;
    private readonly AgentThread _thread;

    /// <summary>
    /// Initializes a new instance of the <see cref="SloganWriterExecutor"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use for the AI agent.</param>
    public SloganWriterExecutor(IChatClient chatClient)
    {
        ChatClientAgentOptions agentOptions = new(instructions: "You are a professional slogan writer. You will be given a task to create a slogan.")
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormat.ForJsonSchema(AIJsonUtilities.CreateJsonSchema(typeof(SloganResult)))
            }
        };

        this._agent = new ChatClientAgent(chatClient, agentOptions);
        this._thread = this._agent.GetNewThread();
    }

    public async ValueTask<SloganResult> HandleAsync(string message, IWorkflowContext context)
    {
        var result = await this._agent.RunAsync(message, this._thread);

        var sloganResult = JsonSerializer.Deserialize<SloganResult>(result.Text) ?? throw new InvalidOperationException("Failed to deserialize slogan result.");

        await context.AddEventAsync(new SloganGeneratedEvent(sloganResult));
        return sloganResult;
    }

    public async ValueTask<SloganResult> HandleAsync(FeedbackResult message, IWorkflowContext context)
    {
        var feedbackMessage = $"""
            Here is the feedback on your previous slogan:
            Comments: {message.Comments}
            Rating: {message.Rating}
            Suggested Actions: {message.Actions}

            Please use this feedback to improve your slogan.
            """;

        var result = await this._agent.RunAsync(feedbackMessage, this._thread);
        var sloganResult = JsonSerializer.Deserialize<SloganResult>(result.Text) ?? throw new InvalidOperationException("Failed to deserialize slogan result.");

        await context.AddEventAsync(new SloganGeneratedEvent(sloganResult));
        return sloganResult;
    }
}

/// <summary>
/// A custom event to indicate that feedback has been provided.
/// </summary>
internal sealed class FeedbackEvent(FeedbackResult feedbackResult) : WorkflowEvent(feedbackResult)
{
    private readonly JsonSerializerOptions _options = new() { WriteIndented = true };
    public override string ToString() => $"Feedback:\n{JsonSerializer.Serialize(feedbackResult, this._options)}";
}

/// <summary>
/// A custom executor that uses an AI agent to provide feedback on a slogan.
/// </summary>
internal sealed class FeedbackExecutor : ReflectingExecutor<FeedbackExecutor>, IMessageHandler<SloganResult>
{
    private readonly AIAgent _agent;
    private readonly AgentThread _thread;

    public int MinimumRating { get; init; } = 8;

    public int MaxAttempts { get; init; } = 3;

    private int _attempts;

    /// <summary>
    /// Initializes a new instance of the <see cref="FeedbackExecutor"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use for the AI agent.</param>
    public FeedbackExecutor(IChatClient chatClient)
    {
        ChatClientAgentOptions agentOptions = new(instructions: "You are a professional editor. You will be given a slogan and the task it is meant to accomplish.")
        {
            ChatOptions = new()
            {
                ResponseFormat = ChatResponseFormat.ForJsonSchema(AIJsonUtilities.CreateJsonSchema(typeof(FeedbackResult)))
            }
        };

        this._agent = new ChatClientAgent(chatClient, agentOptions);
        this._thread = this._agent.GetNewThread();
    }

    public async ValueTask HandleAsync(SloganResult message, IWorkflowContext context)
    {
        var sloganMessage = $"""
            Here is a slogan for the task '{message.Task}':
            Slogan: {message.Slogan}
            Please provide feedback on this slogan, including comments, a rating from 1 to 10, and suggested actions for improvement.
            """;

        var response = await this._agent.RunAsync(sloganMessage, this._thread);
        var feedback = JsonSerializer.Deserialize<FeedbackResult>(response.Text) ?? throw new InvalidOperationException("Failed to deserialize feedback.");

        await context.AddEventAsync(new FeedbackEvent(feedback));

        if (feedback.Rating >= this.MinimumRating)
        {
            await context.AddEventAsync(new WorkflowCompletedEvent($"The following slogan was accepted:\n\n{message.Slogan}"));
            return;
        }

        if (this._attempts >= this.MaxAttempts)
        {
            await context.AddEventAsync(new WorkflowCompletedEvent($"The slogan was rejected after {this.MaxAttempts} attempts. Final slogan:\n\n{message.Slogan}"));
            return;
        }

        await context.SendMessageAsync(feedback);
        this._attempts++;
    }
}
