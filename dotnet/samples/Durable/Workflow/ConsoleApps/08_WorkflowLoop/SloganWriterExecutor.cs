// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowLoop;

/// <summary>
/// Generates slogans based on user input or refines them based on feedback.
/// This executor handles two input types: string (initial request) and FeedbackResult (refinement loop).
/// </summary>
internal sealed class SloganWriterExecutor : Executor
{
    private readonly AIAgent _agent;
    private AgentSession? _session;

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

    /// <summary>
    /// Configures two routes: one for initial string input and one for feedback-based refinement.
    /// </summary>
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<string, SloganResult>(this.HandleAsync)
                    .AddHandler<FeedbackResult, SloganResult>(this.HandleFeedbackAsync);

    /// <summary>
    /// Handles the initial slogan generation request.
    /// </summary>
    public async ValueTask<SloganResult> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine($"  [SloganWriter] Generating slogan for: {message}");
        this._session ??= await this._agent.GetNewSessionAsync(cancellationToken);

        AgentResponse result = await this._agent.RunAsync(message, this._session, cancellationToken: cancellationToken);
        SloganResult slogan = JsonSerializer.Deserialize<SloganResult>(result.Text) ?? throw new InvalidOperationException("Failed to deserialize slogan result.");
        Console.WriteLine($"  [SloganWriter] Generated: \"{slogan.Slogan}\"");
        return slogan;
    }

    /// <summary>
    /// Handles feedback from the feedback executor to refine the slogan.
    /// </summary>
    public async ValueTask<SloganResult> HandleFeedbackAsync(FeedbackResult message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Console.WriteLine($"  [SloganWriter] Refining slogan based on feedback (rating was {message.Rating})...");

        string feedbackMessage = $"""
            Here is the feedback on your previous slogan:
            Comments: {message.Comments}
            Rating: {message.Rating}
            Suggested Actions: {message.Actions}

            Please use this feedback to improve your slogan.
            """;

        AgentResponse result = await this._agent.RunAsync(feedbackMessage, this._session, cancellationToken: cancellationToken);
        SloganResult slogan = JsonSerializer.Deserialize<SloganResult>(result.Text) ?? throw new InvalidOperationException("Failed to deserialize slogan result.");
        Console.WriteLine($"  [SloganWriter] Refined: \"{slogan.Slogan}\"");
        return slogan;
    }
}
