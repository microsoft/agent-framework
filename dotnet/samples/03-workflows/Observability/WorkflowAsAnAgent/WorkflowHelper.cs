// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowAsAnAgentObservabilitySample;

internal static partial class WorkflowHelper
{
    /// <summary>
    /// Creates a workflow that uses two language agents to process input concurrently.
    /// </summary>
    /// <param name="client">The AI project client to use for the agents</param>
    /// <param name="model">The model deployment name</param>
    /// <param name="sourceName">The source name for OpenTelemetry instrumentation</param>
    /// <returns>A workflow that processes input using two language agents</returns>
    internal static Workflow GetWorkflow(AIProjectClient client, string model, string sourceName)
    {
        // Create executors
        var startExecutor = new ConcurrentStartExecutor();
        var aggregationExecutor = new ConcurrentAggregationExecutor();
        AIAgent frenchAgent = GetLanguageAgent("French", client, model, sourceName);
        AIAgent englishAgent = GetLanguageAgent("English", client, model, sourceName);

        // Build the workflow by adding executors and connecting them
        return new WorkflowBuilder(startExecutor)
            .AddFanOutEdge(startExecutor, [frenchAgent, englishAgent])
            .AddFanInBarrierEdge([frenchAgent, englishAgent], aggregationExecutor)
            .WithOutputFrom(aggregationExecutor)
            .Build();
    }

    /// <summary>
    /// Creates a language agent for the specified target language.
    /// </summary>
    /// <param name="targetLanguage">The target language for translation</param>
    /// <param name="client">The AI project client to use for the agent</param>
    /// <param name="model">The model deployment name</param>
    /// <param name="sourceName">The source name for OpenTelemetry instrumentation</param>
    /// <returns>An AIAgent configured for the specified language</returns>
    private static AIAgent GetLanguageAgent(string targetLanguage, AIProjectClient client, string model, string sourceName) =>
        client.AsAIAgent(
            model: model,
            instructions: $"You're a helpful assistant who always responds in {targetLanguage}.",
            name: $"{targetLanguage}Agent",
            clientFactory: c => c.AsBuilder()
                .UseOpenTelemetry(sourceName: sourceName, configure: cfg => cfg.EnableSensitiveData = true)
                .Build()
        )
        .AsBuilder()
        .UseOpenTelemetry(sourceName, configure: (cfg) => cfg.EnableSensitiveData = true)   // enable telemetry at the agent level
        .Build();

    /// <summary>
    /// Executor that starts the concurrent processing by sending messages to the agents.
    /// </summary>
    [SendsMessage(typeof(List<ChatMessage>))]
    [SendsMessage(typeof(TurnToken))]
    private sealed partial class ConcurrentStartExecutor()
        : Executor("ConcurrentStartExecutor", declareCrossRunShareable: true), IResettableExecutor
    {
        [MessageHandler]
        internal ValueTask RouteMessages(IEnumerable<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken)
        {
            List<ChatMessage> payload = messages as List<ChatMessage> ?? messages.ToList();
            return context.SendMessageAsync(payload, cancellationToken: cancellationToken);
        }

        [MessageHandler]
        internal ValueTask RouteTurnTokenAsync(TurnToken token, IWorkflowContext context, CancellationToken cancellationToken)
        {
            return context.SendMessageAsync(token, cancellationToken: cancellationToken);
        }

        public ValueTask ResetAsync() => default;
    }

    /// <summary>
    /// Executor that aggregates the results from the concurrent agents.
    /// </summary>
    [YieldsOutput(typeof(string))]
    private sealed partial class ConcurrentAggregationExecutor() :
        Executor<List<ChatMessage>>("ConcurrentAggregationExecutor"), IResettableExecutor
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

        public ValueTask ResetAsync()
        {
            this._messages.Clear();
            return default;
        }
    }
}
