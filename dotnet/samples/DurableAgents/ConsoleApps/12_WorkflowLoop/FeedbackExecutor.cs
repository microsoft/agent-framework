// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace SingleAgent;

internal sealed class FeedbackExecutor : Executor<SloganResult>
{
    private readonly AIAgent _agent;
    private AgentThread? _thread;

    public int MinimumRating { get; init; } = 9;

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

    public override async ValueTask HandleAsync(SloganResult message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._thread ??= await this._agent.GetNewThreadAsync(cancellationToken);

        var sloganMessage = $"""
            Here is a slogan for the task '{message.Task}':
            Slogan: {message.Slogan}
            Please provide feedback on this slogan, including comments, a rating from 1 to 10, and suggested actions for improvement.
            """;

        var response = await this._agent.RunAsync(sloganMessage, this._thread, cancellationToken: cancellationToken);
        var feedback = JsonSerializer.Deserialize<FeedbackResult>(response.Text) ?? throw new InvalidOperationException("Failed to deserialize feedback.");

        if (feedback.Rating >= this.MinimumRating)
        {
            await context.YieldOutputAsync($"The following slogan was accepted:\n\n{message.Slogan}", cancellationToken);
            return;
        }

        if (this._attempts >= this.MaxAttempts)
        {
            await context.YieldOutputAsync($"The slogan was rejected after {this.MaxAttempts} attempts. Final slogan:\n\n{message.Slogan}", cancellationToken);
            return;
        }

        await context.SendMessageAsync(feedback, cancellationToken: cancellationToken);
        this._attempts++;
    }
}
