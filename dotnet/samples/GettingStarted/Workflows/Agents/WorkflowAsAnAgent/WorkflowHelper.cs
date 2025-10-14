// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowAsAnAgentsSample;

internal static class WorkflowHelper
{
    /// <summary>
    /// Creates a workflow that uses two language agents to process input concurrently.
    /// </summary>
    /// <param name="chatClient">The chat client to use for the agents</param>
    /// <returns>A workflow that processes input using two language agents</returns>
    internal static ValueTask<Workflow<List<ChatMessage>>> GetWorkflowAsync(IChatClient chatClient)
    {
        // Create executors
        var startExecutor = new ConcurrentStartExecutor();
        var aggregationExecutor = new ConcurrentAggregationExecutor();
        AIAgent frenchAgent = GetLanguageAgent("French", chatClient);
        AIAgent englishAgent = GetLanguageAgent("English", chatClient);

        // Build the workflow by adding executors and connecting them
        return new WorkflowBuilder(startExecutor)
            .AddFanOutEdge(startExecutor, targets: [frenchAgent, englishAgent])
            .AddFanInEdge(aggregationExecutor, sources: [frenchAgent, englishAgent])
            .WithOutputFrom(aggregationExecutor)
            .BuildAsync<List<ChatMessage>>();
    }

    /// <summary>
    /// Creates a language agent for the specified target language.
    /// </summary>
    /// <param name="targetLanguage">The target language for translation</param>
    /// <param name="chatClient">The chat client to use for the agent</param>
    /// <returns>A ChatClientAgent configured for the specified language</returns>
    private static ChatClientAgent GetLanguageAgent(string targetLanguage, IChatClient chatClient) =>
        new(chatClient, instructions: $"You're a helpful assistant who always responds in {targetLanguage}.", name: $"{targetLanguage}Agent");

    /// <summary>
    /// Executor that starts the concurrent processing by sending messages to the agents.
    /// </summary>
    private sealed class ConcurrentStartExecutor() :
        Executor<List<ChatMessage>>("ConcurrentStartExecutor")
    {
        /// <summary>
        /// Starts the concurrent processing by sending messages to the agents.
        /// </summary>
        /// <param name="message">The user message to process</param>
        /// <param name="context">Workflow context for accessing workflow services and adding events</param>
        /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
        /// The default is <see cref="CancellationToken.None"/>.</param>
        public override async ValueTask HandleAsync(List<ChatMessage> message, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            // Broadcast the message to all connected agents. Receiving agents will queue
            // the message but will not start processing until they receive a turn token.
            await context.SendMessageAsync(message, cancellationToken: cancellationToken);
            // Broadcast the turn token to kick off the agents.
            await context.SendMessageAsync(new TurnToken(emitEvents: true), cancellationToken: cancellationToken);
        }
    }

    /// <summary>
    /// Executor that aggregates the results from the concurrent agents.
    /// </summary>
    private sealed class ConcurrentAggregationExecutor() :
        Executor<ChatMessage>("ConcurrentAggregationExecutor")
    {
        private readonly List<ChatMessage> _messages = [];

        /// <summary>
        /// Handles incoming messages from the agents and aggregates their responses.
        /// </summary>
        /// <param name="message">The message from the agent</param>
        /// <param name="context">Workflow context for accessing workflow services and adding events</param>
        /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
        /// The default is <see cref="CancellationToken.None"/>.</param>
        public override async ValueTask HandleAsync(ChatMessage message, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            this._messages.Add(message);

            if (this._messages.Count == 2)
            {
                var formattedMessages = string.Join(Environment.NewLine, this._messages.Select(m => $"{m.Text}"));
                await context.YieldOutputAsync(formattedMessages, cancellationToken);
            }
        }
    }
}
