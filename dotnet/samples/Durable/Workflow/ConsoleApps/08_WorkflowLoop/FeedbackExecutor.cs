// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowLoop;

/// <summary>
/// Evaluates slogans and either accepts them or sends feedback back for refinement.
/// Uses SendMessageAsync to loop back to SloganWriter and YieldOutputAsync to end the workflow.
/// </summary>
internal sealed class FeedbackExecutor : Executor<SloganResult>
{
    private readonly AIAgent _agent;
    private AgentSession? _session;

    /// <summary>
    /// Gets or sets the minimum rating required to accept a slogan.
    /// </summary>
    public int MinimumRating { get; init; } = 9;

    /// <summary>
    /// Gets or sets the maximum number of refinement attempts before accepting the slogan.
    /// </summary>
    public int MaxAttempts { get; init; } = 3;

    private int _attempts;

    /// <summary>
    /// Initializes a new instance of the <see cref="FeedbackExecutor"/> class.
    /// </summary>
    /// <param name="id">A unique identifier for the executor.</param>
    /// <param name="chatClient">The chat client to use for the AI agent.</param>
    public FeedbackExecutor(string id, IChatClient chatClient) : base(id)
    {
        ChatClientAgentOptions agentOptions = new()
        {
            ChatOptions = new()
            {
                Instructions = "You are a professional editor. You will be given a slogan and the task it is meant to accomplish.",
                ResponseFormat = ChatResponseFormat.ForJsonSchema<FeedbackResult>()
            }
        };

        this._agent = new ChatClientAgent(chatClient, agentOptions);
    }

    /// <inheritdoc/>
    public override async ValueTask HandleAsync(SloganResult message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine($"  [FeedbackProvider] Evaluating slogan: \"{message.Slogan}\"");
        this._session ??= await this._agent.GetNewSessionAsync(cancellationToken);

        string sloganMessage = $"""
            Here is a slogan for the task '{message.Task}':
            Slogan: {message.Slogan}
            Please provide feedback on this slogan, including comments, a rating from 1 to 10, and suggested actions for improvement.
            """;

        AgentResponse response = await this._agent.RunAsync(sloganMessage, this._session, cancellationToken: cancellationToken);
        FeedbackResult feedback = JsonSerializer.Deserialize<FeedbackResult>(response.Text) ?? throw new InvalidOperationException("Failed to deserialize feedback.");

        Console.WriteLine($"  [FeedbackProvider] Rating: {feedback.Rating}/{this.MinimumRating} - {feedback.Comments}");

        // If the rating meets the threshold, accept the slogan and end the workflow
        if (feedback.Rating >= this.MinimumRating)
        {
            Console.WriteLine("  [FeedbackProvider] Accepted!");
            await context.YieldOutputAsync($"The following slogan was accepted:\n\n{message.Slogan}", cancellationToken);
            return;
        }

        // If we've exceeded max attempts, accept the slogan anyway
        if (this._attempts >= this.MaxAttempts)
        {
            Console.WriteLine("  [FeedbackProvider] Max attempts reached, accepting final slogan.");
            await context.YieldOutputAsync($"The slogan was accepted after {this.MaxAttempts} attempts. Final slogan:\n\n{message.Slogan}", cancellationToken);
            return;
        }

        // Otherwise, send feedback back to the slogan writer for refinement (circular edge)
        Console.WriteLine($"  [FeedbackProvider] Sending back for refinement (attempt {this._attempts + 1}/{this.MaxAttempts})...");
        await context.SendMessageAsync(feedback, cancellationToken: cancellationToken);
        this._attempts++;
    }
}
