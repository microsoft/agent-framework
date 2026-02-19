// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowAsAnAgentSample;

internal static class WorkflowFactory
{
    /// <summary>
    /// Creates a workflow that uses two language agents to process input concurrently.
    /// </summary>
    /// <param name="chatClient">The chat client to use for the agents</param>
    /// <returns>A workflow that processes input using two language agents</returns>
    internal static Workflow BuildWorkflow(IChatClient chatClient)
    {
        // Create executors
        var startExecutor = new ChatForwardingExecutor("Start");
        var aggregationExecutor = new ConcurrentAggregationExecutor();
        AIAgent frenchAgent = GetLanguageAgent("French", chatClient);
        AIAgent englishAgent = GetLanguageAgent("English", chatClient);

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
    /// <returns>A ChatClientAgent configured for the specified language</returns>
    private static ChatClientAgent GetLanguageAgent(string targetLanguage, IChatClient chatClient) =>
        new(chatClient, instructions: $"You're a helpful assistant who always responds in {targetLanguage}.", name: $"{targetLanguage}Agent");

    /// <summary>
    /// Executor that aggregates the results from the concurrent agents.
    /// </summary>
    private sealed class ConcurrentAggregationExecutor() :
        Executor<List<ChatMessage>>("ConcurrentAggregationExecutor"), IResettableExecutor
    {
        private readonly List<ChatMessage> _messages = [];

        /// <summary>
        /// Handles incoming messages from the agents and aggregates their responses.
        /// </summary>
        /// <param name="message">The messages from the agent</param>
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

        /// <inheritdoc/>
        public ValueTask ResetAsync()
        {
            this._messages.Clear();
            return default;
        }
    }
}
