// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Fluent builder for sequential agent workflows: a pipeline where the output of one
/// agent is the input to the next, terminating in an aggregator that yields the
/// accumulated <see cref="Extensions.AI.ChatMessage"/>s as the workflow output.
/// </summary>
/// <remarks>
/// When no explicit output designations are made, the default is the Python-aligned
/// shape: the terminal aggregator is the workflow output, and every participating agent
/// is designated as an intermediate output source. Calling
/// <see cref="OrchestrationBuilderBase{TBuilder}.WithOutputFrom(IEnumerable{AIAgent})"/>
/// or <see cref="OrchestrationBuilderBase{TBuilder}.WithIntermediateOutputFrom(IEnumerable{AIAgent})"/>
/// at all suppresses these defaults.
/// </remarks>
public sealed class SequentialWorkflowBuilder : OrchestrationBuilderBase<SequentialWorkflowBuilder>
{
    private readonly List<AIAgent> _agents = [];

    /// <summary>
    /// Initializes a new <see cref="SequentialWorkflowBuilder"/> with the given pipeline
    /// of <paramref name="agents"/>.
    /// </summary>
    public SequentialWorkflowBuilder(params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);
        foreach (AIAgent agent in agents)
        {
            Throw.IfNull(agent, nameof(agents));
            this._agents.Add(agent);
        }
    }

    /// <summary>Builds the configured sequential workflow.</summary>
    public Workflow Build()
    {
        if (this._agents.Count == 0)
        {
            throw new ArgumentException("At least one agent must be provided to the SequentialWorkflowBuilder.", "agents");
        }

        AIAgentHostOptions options = new()
        {
            ReassignOtherAgentsAsUsers = true,
            ForwardIncomingMessages = true,
        };

        Dictionary<AIAgent, ExecutorBinding> agentMap = new(AIAgentIDEqualityComparer.Instance);
        List<ExecutorBinding> agentExecutors = new(this._agents.Count);
        foreach (AIAgent agent in this._agents)
        {
            ExecutorBinding binding = agent.BindAsExecutor(options);
            agentExecutors.Add(binding);
            agentMap[agent] = binding;
        }

        ExecutorBinding previous = agentExecutors[0];
        WorkflowBuilder builder = new(previous);
        foreach (ExecutorBinding next in agentExecutors.Skip(1))
        {
            builder.AddEdge(previous, next);
            previous = next;
        }

        OutputMessagesExecutor end = new();
        builder.AddEdge(previous, end).BindExecutor(end);

        this.ApplyMetadata(builder);
        this.ApplyOutputDesignations(builder, agentMap, "sequential", () =>
        {
            builder.WithOutputFrom(end);
            builder.WithIntermediateOutputFrom(agentExecutors);
        });

        return builder.Build();
    }
}
