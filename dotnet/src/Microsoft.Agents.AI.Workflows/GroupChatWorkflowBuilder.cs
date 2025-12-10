// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Provides a builder for specifying group chat relationships between agents and building the resulting workflow.
/// </summary>
public sealed class GroupChatWorkflowBuilder
{
    private readonly Func<IReadOnlyList<AIAgent>, GroupChatManager> _managerFactory;
    private readonly HashSet<AIAgent> _participants = new(AIAgentIDEqualityComparer.Instance);

    internal GroupChatWorkflowBuilder(Func<IReadOnlyList<AIAgent>, GroupChatManager> managerFactory) =>
        this._managerFactory = managerFactory;

    /// <summary>
    /// Adds the specified <paramref name="agents"/> as participants to the group chat workflow.
    /// </summary>
    /// <param name="agents">The agents to add as participants.</param>
    /// <returns>This instance of the <see cref="GroupChatWorkflowBuilder"/>.</returns>
    public GroupChatWorkflowBuilder AddParticipants(params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);

        foreach (var agent in agents)
        {
            if (agent is null)
            {
                Throw.ArgumentNullException(nameof(agents), "One or more target agents are null.");
            }

            this._participants.Add(agent);
        }

        return this;
    }

    /// <summary>
    /// Builds a <see cref="Workflow"/> composed of agents that operate via group chat, with the next
    /// agent to process messages selected by the group chat manager.
    /// </summary>
    /// <returns>The workflow built based on the group chat in the builder.</returns>
    public Workflow Build()
    {
        AIAgent[] agents = this._participants.ToArray();
        Dictionary<AIAgent, ExecutorBinding> agentMap = agents.ToDictionary(a => a, a => (ExecutorBinding)new AgentRunStreamingExecutor(a, includeInputInOutput: true));

        Func<string, string, ValueTask<Executor>> groupChatHostFactory =
            (id, runId) => new(new GroupChatHost(id, agents, agentMap, this._managerFactory));

        ExecutorBinding host = groupChatHostFactory.BindExecutor(nameof(GroupChatHost));
        WorkflowBuilder builder = new(host);

        foreach (var participant in agentMap.Values)
        {
            builder
                .AddEdge(host, participant)
                .AddEdge(participant, host);
        }

        return builder.WithOutputFrom(host).Build();
    }
}
