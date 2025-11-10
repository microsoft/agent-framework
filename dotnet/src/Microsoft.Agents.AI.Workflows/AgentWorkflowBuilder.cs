// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides utility methods for constructing common patterns of workflows composed of agents.
/// </summary>
public static partial class AgentWorkflowBuilder
{
    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of a pipeline of agents where the output of one agent is the input to the next.
    /// </summary>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The built workflow composed of the supplied <paramref name="agents"/>, in the order in which they were yielded from the source.</returns>
    public static Workflow BuildSequential(params IEnumerable<AIAgent> agents)
        => BuildSequentialCore(workflowName: null, agents);

    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of a pipeline of agents where the output of one agent is the input to the next.
    /// </summary>
    /// <param name="workflowName">The name of workflow.</param>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The built workflow composed of the supplied <paramref name="agents"/>, in the order in which they were yielded from the source.</returns>
    public static Workflow BuildSequential(string workflowName, params IEnumerable<AIAgent> agents)
        => BuildSequentialCore(workflowName, agents);

    private static Workflow BuildSequentialCore(string? workflowName, params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);

        // Create a builder that chains the agents together in sequence. The workflow simply begins
        // with the first agent in the sequence.
        WorkflowBuilder? builder = null;
        ExecutorBinding? previous = null;
        foreach (var agent in agents)
        {
            AgentRunStreamingExecutor agentExecutor = new(agent, includeInputInOutput: true);

            if (builder is null)
            {
                builder = new WorkflowBuilder(agentExecutor);
            }
            else
            {
                Debug.Assert(previous is not null);
                builder.AddEdge(previous, agentExecutor);
            }

            previous = agentExecutor;
        }

        if (previous is null)
        {
            Throw.ArgumentException(nameof(agents), "At least one agent must be provided to build a sequential workflow.");
        }

        // Add an ending executor that batches up all messages from the last agent
        // so that it's published as a single list result.
        Debug.Assert(builder is not null);

        OutputMessagesExecutor end = new();
        builder = builder.AddEdge(previous, end).WithOutputFrom(end);
        if (workflowName is not null)
        {
            builder = builder.WithName(workflowName);
        }
        return builder.Build();
    }

    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of agents that operate concurrently on the same input,
    /// aggregating their outputs into a single collection.
    /// </summary>
    /// <param name="agents">The set of agents to compose into a concurrent workflow.</param>
    /// <param name="aggregator">
    /// The aggregation function that accepts a list of the output messages from each <paramref name="agents"/> and produces
    /// a single result list. If <see langword="null"/>, the default behavior is to return a list containing the last message
    /// from each agent that produced at least one message.
    /// </param>
    /// <returns>The built workflow composed of the supplied concurrent <paramref name="agents"/>.</returns>
    public static Workflow BuildConcurrent(
        IEnumerable<AIAgent> agents,
        Func<IList<List<ChatMessage>>, List<ChatMessage>>? aggregator = null)
        => BuildConcurrentCore(workflowName: null, agents, aggregator);

    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of agents that operate concurrently on the same input,
    /// aggregating their outputs into a single collection.
    /// </summary>
    /// <param name="workflowName">The name of the workflow.</param>
    /// <param name="agents">The set of agents to compose into a concurrent workflow.</param>
    /// <param name="aggregator">
    /// The aggregation function that accepts a list of the output messages from each <paramref name="agents"/> and produces
    /// a single result list. If <see langword="null"/>, the default behavior is to return a list containing the last message
    /// from each agent that produced at least one message.
    /// </param>
    /// <returns>The built workflow composed of the supplied concurrent <paramref name="agents"/>.</returns>
    public static Workflow BuildConcurrent(
        string workflowName,
        IEnumerable<AIAgent> agents,
        Func<IList<List<ChatMessage>>, List<ChatMessage>>? aggregator = null)
        => BuildConcurrentCore(workflowName, agents, aggregator);

    private static Workflow BuildConcurrentCore(
        string? workflowName,
        IEnumerable<AIAgent> agents,
        Func<IList<List<ChatMessage>>, List<ChatMessage>>? aggregator = null)
    {
        Throw.IfNull(agents);

        // A workflow needs a starting executor, so we create one that forwards everything to each agent.
        ChatForwardingExecutor start = new("Start");
        WorkflowBuilder builder = new(start);

        // For each agent, we create an executor to host it and an accumulator to batch up its output messages,
        // so that the final accumulator receives a single list of messages from each agent. Otherwise, the
        // accumulator would not be able to determine what came from what agent, as there's currently no
        // provenance tracking exposed in the workflow context passed to a handler.
        ExecutorBinding[] agentExecutors = (from agent in agents select (ExecutorBinding)new AgentRunStreamingExecutor(agent, includeInputInOutput: false)).ToArray();
        ExecutorBinding[] accumulators = [.. from agent in agentExecutors select (ExecutorBinding)new CollectChatMessagesExecutor($"Batcher/{agent.Id}")];
        builder.AddFanOutEdge(start, agentExecutors);
        for (int i = 0; i < agentExecutors.Length; i++)
        {
            builder.AddEdge(agentExecutors[i], accumulators[i]);
        }

        // Create the accumulating executor that will gather the results from each agent, and connect
        // each agent's accumulator to it. If no aggregation function was provided, we default to returning
        // the last message from each agent
        aggregator ??= static lists => (from list in lists where list.Count > 0 select list.Last()).ToList();

        Func<string, string, ValueTask<ConcurrentEndExecutor>> endFactory =
            (string _, string __) => new(new ConcurrentEndExecutor(agentExecutors.Length, aggregator));

        ExecutorBinding end = endFactory.BindExecutor(ConcurrentEndExecutor.ExecutorId);

        builder.AddFanInEdge(accumulators, end);

        builder = builder.WithOutputFrom(end);
        if (workflowName is not null)
        {
            builder = builder.WithName(workflowName);
        }
        return builder.Build();
    }

    /// <summary>Creates a new <see cref="HandoffsWorkflowBuilder"/> using <paramref name="initialAgent"/> as the starting agent in the workflow.</summary>
    /// <param name="initialAgent">The agent that will receive inputs provided to the workflow.</param>
    /// <returns>The builder for creating a workflow based on handoffs.</returns>
    /// <remarks>
    /// Handoffs between agents are achieved by the current agent invoking an <see cref="AITool"/> provided to an agent
    /// via <see cref="ChatClientAgentOptions"/>'s <see cref="ChatClientAgentOptions.ChatOptions"/>.<see cref="ChatOptions.Tools"/>.
    /// The <see cref="AIAgent"/> must be capable of understanding those <see cref="AgentRunOptions"/> provided. If the agent
    /// ignores the tools or is otherwise unable to advertize them to the underlying provider, handoffs will not occur.
    /// </remarks>
    public static HandoffsWorkflowBuilder CreateHandoffBuilderWith(AIAgent initialAgent)
    {
        Throw.IfNull(initialAgent);
        return new(initialAgent);
    }

    /// <summary>Creates a new <see cref="GroupChatWorkflowBuilder"/> with <paramref name="managerFactory"/>.</summary>
    /// <param name="managerFactory">
    /// Function that will create the <see cref="GroupChatManager"/> for the workflow instance. The manager will be
    /// provided with the set of agents that will participate in the group chat.
    /// </param>
    /// <returns>The builder for creating a workflow based on handoffs.</returns>
    /// <remarks>
    /// Handoffs between agents are achieved by the current agent invoking an <see cref="AITool"/> provided to an agent
    /// via <see cref="ChatClientAgentOptions"/>'s <see cref="ChatClientAgentOptions.ChatOptions"/>.<see cref="ChatOptions.Tools"/>.
    /// The <see cref="AIAgent"/> must be capable of understanding those <see cref="AgentRunOptions"/> provided. If the agent
    /// ignores the tools or is otherwise unable to advertize them to the underlying provider, handoffs will not occur.
    /// </remarks>
    public static GroupChatWorkflowBuilder CreateGroupChatBuilderWith(Func<IReadOnlyList<AIAgent>, GroupChatManager> managerFactory)
    {
        Throw.IfNull(managerFactory);
        return new GroupChatWorkflowBuilder(managerFactory);
    }
}
