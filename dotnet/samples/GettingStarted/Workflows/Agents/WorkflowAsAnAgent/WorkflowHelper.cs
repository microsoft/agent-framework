// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Reflection;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace WorkflowAsAnAgentsSample;

internal static class WorkflowHelper
{
    /// <summary>
    /// Creates a workflow that uses two language agents to process input concurrently.
    /// </summary>
    /// <param name="chatClient">The chat client to use for the agents</param>
    /// <returns>A workflow that processes input using two language agents</returns>
    internal static Workflow<List<ChatMessage>> GetWorkflow(IChatClient chatClient)
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
            .Build<List<ChatMessage>>();
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
        ReflectingExecutor<ConcurrentStartExecutor>("ConcurrentStartExecutor"),
        IMessageHandler<List<ChatMessage>>
    {
        /// <summary>
        /// Starts the concurrent processing by sending messages to the agents.
        /// </summary>
        /// <param name="message">The user message to process</param>
        /// <param name="context">Workflow context for accessing workflow services and adding events</param>
        public async ValueTask HandleAsync(List<ChatMessage> message, IWorkflowContext context)
        {
            // Broadcast the message to all connected agents. Receiving agents will queue
            // the message but will not start processing until they receive a turn token.
            await context.SendMessageAsync(message);
            // Broadcast the turn token to kick off the agents.
            await context.SendMessageAsync(new TurnToken(emitEvents: true));
        }
    }

    /// <summary>
    /// Executor that aggregates the results from the concurrent agents.
    /// </summary>
    private sealed class ConcurrentAggregationExecutor() :
        ReflectingExecutor<ConcurrentAggregationExecutor>("ConcurrentAggregationExecutor"),
        IMessageHandler<ChatMessage>
    {
        private readonly List<ChatMessage> _messages = [];

        /// <summary>
        /// Handles incoming messages from the agents and aggregates their responses.
        /// </summary>
        /// <param name="message">The message from the agent</param>
        /// <param name="context">Workflow context for accessing workflow services and adding events</param>
        public async ValueTask HandleAsync(ChatMessage message, IWorkflowContext context)
        {
            this._messages.Add(message);

            if (this._messages.Count == 2)
            {
                var formattedMessages = string.Join(Environment.NewLine, this._messages.Select(m => $"{m.Text}"));
                await context.AddEventAsync(new WorkflowCompletedEvent(formattedMessages));
            }
        }
    }
}
