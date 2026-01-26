// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace SingleAgent;

internal sealed class SloganWriterExecutor : Executor
{
    private readonly AIAgent _agent;
    private AgentThread? _thread;

    /// <summary>
    /// Initializes a new instance of the <see cref="SloganWriterExecutor"/> class.
    /// </summary>
    /// <param name="id">A unique identifier for the executor.</param>
    /// <param name="chatClient">The chat client to use for the AI agent.</param>
    public SloganWriterExecutor(string id, IChatClient chatClient) : base(id)
    {
        ChatClientAgentOptions agentOptions = new()
        {
            ChatOptions = new()
            {
                Instructions = "You are a professional slogan writer. You will be given a task to create a slogan.",
                ResponseFormat = ChatResponseFormat.ForJsonSchema<SloganResult>()
            }
        };

        this._agent = new ChatClientAgent(chatClient, agentOptions);
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<string, SloganResult>(this.HandleAsync)
                    .AddHandler<FeedbackResult, SloganResult>(this.HandleAsync);

    public async ValueTask<SloganResult> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._thread ??= await this._agent.GetNewThreadAsync(cancellationToken);

        var result = await this._agent.RunAsync(message, this._thread, cancellationToken: cancellationToken);

        return JsonSerializer.Deserialize<SloganResult>(result.Text) ?? throw new InvalidOperationException("Failed to deserialize slogan result.");
    }

    public async ValueTask<SloganResult> HandleAsync(FeedbackResult message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        var feedbackMessage = $"""
            Here is the feedback on your previous slogan:
            Comments: {message.Comments}
            Rating: {message.Rating}
            Suggested Actions: {message.Actions}

            Please use this feedback to improve your slogan.
            """;

        var result = await this._agent.RunAsync(feedbackMessage, this._thread, cancellationToken: cancellationToken);
        return JsonSerializer.Deserialize<SloganResult>(result.Text) ?? throw new InvalidOperationException("Failed to deserialize slogan result.");
    }
}
