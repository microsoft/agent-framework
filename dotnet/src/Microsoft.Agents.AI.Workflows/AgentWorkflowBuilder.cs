// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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
    /// <param name="chainOnlyAgentResponses">
    /// <see langword="true"/> to pass only each agent's output messages to the next agent in the sequence;
    /// <see langword="false"/> to pass the full accumulated conversation.
    /// When enabled, the workflow output also reflects only the final agent's messages,
    /// because the sequential builder stops forwarding the incoming messages to the
    /// terminal output executor.
    /// </param>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The built workflow composed of the supplied <paramref name="agents"/>, in the order in which they were yielded from the source.</returns>
    public static Workflow BuildSequential(bool chainOnlyAgentResponses, params IEnumerable<AIAgent> agents)
        => BuildSequentialCore(workflowName: null, chainOnlyAgentResponses, agents);

    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of a pipeline of agents where the output of one agent is the input to the next.
    /// </summary>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The built workflow composed of the supplied <paramref name="agents"/>, in the order in which they were yielded from the source.</returns>
    public static Workflow BuildSequential(params IEnumerable<AIAgent> agents)
        => BuildSequentialCore(workflowName: null, chainOnlyAgentResponses: false, agents);

    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of a pipeline of agents where the output of one agent is the input to the next.
    /// </summary>
    /// <param name="workflowName">The name of workflow.</param>
    /// <param name="chainOnlyAgentResponses">
    /// <see langword="true"/> to pass only each agent's output messages to the next agent in the sequence;
    /// <see langword="false"/> to pass the full accumulated conversation.
    /// When enabled, the workflow output also reflects only the final agent's messages,
    /// because the sequential builder stops forwarding the incoming messages to the
    /// terminal output executor.
    /// </param>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The built workflow composed of the supplied <paramref name="agents"/>, in the order in which they were yielded from the source.</returns>
    public static Workflow BuildSequential(string workflowName, bool chainOnlyAgentResponses, params IEnumerable<AIAgent> agents)
        => BuildSequentialCore(workflowName, chainOnlyAgentResponses, agents);

    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of a pipeline of agents where the output of one agent is the input to the next.
    /// </summary>
    /// <param name="workflowName">The name of workflow.</param>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The built workflow composed of the supplied <paramref name="agents"/>, in the order in which they were yielded from the source.</returns>
    public static Workflow BuildSequential(string workflowName, params IEnumerable<AIAgent> agents)
        => BuildSequentialCore(workflowName, chainOnlyAgentResponses: false, agents);

    private static Workflow BuildSequentialCore(string? workflowName, bool chainOnlyAgentResponses, params IEnumerable<AIAgent> agents)
    {
        Throw.IfNullOrEmpty(agents);

        SequentialWorkflowBuilder builder = new SequentialWorkflowBuilder(agents)
            .WithChainOnlyAgentResponses(chainOnlyAgentResponses);
        if (workflowName is not null)
        {
            builder.WithName(workflowName);
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

        ConcurrentWorkflowBuilder builder = new(agents);
        if (workflowName is not null)
        {
            builder.WithName(workflowName);
        }
        if (aggregator is not null)
        {
            builder.WithAggregator(aggregator);
        }
        return builder.Build();
    }

    /// <summary>Creates a new <see cref="HandoffWorkflowBuilder"/> using <paramref name="initialAgent"/> as the starting agent in the workflow.</summary>
    /// <param name="initialAgent">The agent that will receive inputs provided to the workflow.</param>
    /// <returns>The builder for creating a workflow based on handoffs.</returns>
    /// <remarks>
    /// Handoffs between agents are achieved by the current agent invoking an <see cref="AITool"/> provided to an agent
    /// via <see cref="ChatClientAgentOptions"/>'s <see cref="ChatClientAgentOptions.ChatOptions"/>.<see cref="ChatOptions.Tools"/>.
    /// The <see cref="AIAgent"/> must be capable of understanding those <see cref="AgentRunOptions"/> provided. If the agent
    /// ignores the tools or is otherwise unable to advertize them to the underlying provider, handoffs will not occur.
    /// </remarks>
    public static HandoffWorkflowBuilder CreateHandoffBuilderWith(AIAgent initialAgent)
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

    /// <summary>Creates a new <see cref="SequentialWorkflowBuilder"/> with the given pipeline of <paramref name="agents"/>.</summary>
    /// <param name="agents">The sequence of agents to compose into a sequential workflow.</param>
    /// <returns>The builder for creating a sequential workflow.</returns>
    public static SequentialWorkflowBuilder CreateSequentialBuilderWith(params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);
        return new SequentialWorkflowBuilder(agents);
    }

    /// <summary>Creates a new <see cref="ConcurrentWorkflowBuilder"/> with the given participating <paramref name="agents"/>.</summary>
    /// <param name="agents">The set of agents to compose into a concurrent workflow.</param>
    /// <returns>The builder for creating a concurrent workflow.</returns>
    public static ConcurrentWorkflowBuilder CreateConcurrentBuilderWith(params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);
        return new ConcurrentWorkflowBuilder(agents);
    }

    /// <summary>Creates a new <see cref="MagenticWorkflowBuilder"/> with the given <paramref name="managerAgent"/>.</summary>
    /// <param name="managerAgent">The LLM-powered manager agent that coordinates the team.</param>
    /// <returns>The builder for creating a Magentic workflow.</returns>
    public static MagenticWorkflowBuilder CreateMagenticBuilderWith(AIAgent managerAgent)
    {
        Throw.IfNull(managerAgent);
        return new MagenticWorkflowBuilder(managerAgent);
    }
}
