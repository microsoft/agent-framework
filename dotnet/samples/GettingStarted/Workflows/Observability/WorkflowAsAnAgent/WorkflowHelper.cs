// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowAsAnAgentObservabilitySample;

internal static class WorkflowHelper
{
    /// <summary>
    /// Creates a workflow that uses two language agents to process input concurrently.
    /// </summary>
    /// <param name="chatClient">The chat client to use for the agents</param>
    /// <param name="sourceName">The source name for OpenTelemetry instrumentation</param>
    /// <returns>A workflow that processes input using two language agents</returns>
    internal static Workflow GetWorkflow(IChatClient chatClient, string sourceName)
    {
        // Create executors
        var startExecutor = new ConcurrentStartExecutor();
        var aggregationExecutor = new ConcurrentAggregationExecutor();
        AIAgent frenchAgent = GetLanguageAgent("French", chatClient, sourceName);
        AIAgent englishAgent = GetLanguageAgent("English", chatClient, sourceName);

        // Build the workflow by adding executors and connecting them
        return new WorkflowBuilder(startExecutor)
            .AddFanOutEdge(startExecutor, [frenchAgent, englishAgent])
            .AddFanInEdge([frenchAgent, englishAgent], aggregationExecutor)
            .WithOutputFrom(aggregationExecutor)
            .Build();
    }

    /// <summary>
    /// Creates a language agent for the specified target language.
    /// </summary>
    /// <param name="targetLanguage">The target language for translation</param>
    /// <param name="chatClient">The chat client to use for the agent</param>
    /// <param name="sourceName">The source name for OpenTelemetry instrumentation</param>
    /// <returns>An AIAgent configured for the specified language</returns>
    private static AIAgent GetLanguageAgent(string targetLanguage, IChatClient chatClient, string sourceName) =>
        new ChatClientAgent(
            chatClient,
            instructions: $"You're a helpful assistant who always responds in {targetLanguage}.",
            name: $"{targetLanguage}Agent"
        )
        .AsBuilder()
        .UseOpenTelemetry(sourceName, configure: (cfg) => cfg.EnableSensitiveData = true)   // enable telemetry at the agent level
        .Build();

    /// <summary>
    /// Executor that starts the concurrent processing by sending messages to the agents.
    /// </summary>
    private sealed class ConcurrentStartExecutor() : Executor("ConcurrentStartExecutor")
    {
        protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
        {
            return routeBuilder
                .AddHandler<List<ChatMessage>>(this.RouteMessages)
                .AddHandler<TurnToken>(this.RouteTurnTokenAsync);
        }

        private ValueTask RouteMessages(List<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken)
        {
            return context.SendMessageAsync(messages, cancellationToken: cancellationToken);
        }

        private ValueTask RouteTurnTokenAsync(TurnToken token, IWorkflowContext context, CancellationToken cancellationToken)
        {
            return context.SendMessageAsync(token, cancellationToken: cancellationToken);
        }
    }

    /// <summary>
    /// Executor that aggregates the results from the concurrent agents.
    /// </summary>
    private sealed class ConcurrentAggregationExecutor() : Executor<List<ChatMessage>>("ConcurrentAggregationExecutor")
    {
        private readonly List<ChatMessage> _messages = [];

        /// <summary>
        /// Handles incoming messages from the agents and aggregates their responses.
        /// </summary>
        /// <param name="message">The message from the agent</param>
        /// <param name="context">Workflow context for accessing workflow services and adding events</param>
        /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
        /// The default is <see cref="CancellationToken.None"/>.</param>
        public override async ValueTask HandleAsync(List<ChatMessage> message, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            this._messages.AddRange(message);

            if (this._messages.Count == 2)
            {
                var formattedMessages = string.Join(Environment.NewLine, this._messages.Select(m => $"{m.Text}"));
                await context.YieldOutputAsync(formattedMessages, cancellationToken);
            }
        }
    }
}
