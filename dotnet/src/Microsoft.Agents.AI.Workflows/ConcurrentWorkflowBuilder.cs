// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Fluent builder for concurrent agent workflows: a fan-out start that broadcasts the
/// incoming messages to every participating agent, a per-agent accumulator that batches
/// each agent's outgoing messages, and a fan-in aggregator that reduces them into a
/// single output list.
/// </summary>
/// <remarks>
/// When no explicit output designations are made, the default is the Python-aligned
/// shape: the terminal aggregator is the workflow output, and every participating agent
/// (plus its per-agent accumulator) is designated as an intermediate output source.
/// Calling <see cref="OrchestrationBuilderBase{TBuilder}.WithOutputFrom(IEnumerable{AIAgent})"/>
/// or <see cref="OrchestrationBuilderBase{TBuilder}.WithIntermediateOutputFrom(IEnumerable{AIAgent})"/>
/// at all suppresses these defaults.
/// </remarks>
public sealed class ConcurrentWorkflowBuilder : OrchestrationBuilderBase<ConcurrentWorkflowBuilder>
{
    private readonly List<AIAgent> _agents = [];
    private Func<IList<List<ChatMessage>>, List<ChatMessage>>? _aggregator;

    /// <summary>
    /// Initializes a new <see cref="ConcurrentWorkflowBuilder"/> with the given participating
    /// <paramref name="agents"/>.
    /// </summary>
    public ConcurrentWorkflowBuilder(params IEnumerable<AIAgent> agents)
    {
        Throw.IfNull(agents);
        foreach (AIAgent agent in agents)
        {
            Throw.IfNull(agent, nameof(agents));
            this._agents.Add(agent);
        }
    }

    /// <summary>
    /// Sets the aggregator function. If not called, defaults to returning the last message
    /// from each agent that produced at least one message.
    /// </summary>
    public ConcurrentWorkflowBuilder WithAggregator(Func<IList<List<ChatMessage>>, List<ChatMessage>> aggregator)
    {
        this._aggregator = Throw.IfNull(aggregator);
        return this;
    }

    /// <summary>Builds the configured concurrent workflow.</summary>
    public Workflow Build()
    {
        if (this._agents.Count == 0)
        {
            throw new ArgumentException("At least one agent must be provided to the ConcurrentWorkflowBuilder.", "agents");
        }

        ChatForwardingExecutor start = new("Start");
        WorkflowBuilder builder = new(start);

        Dictionary<AIAgent, ExecutorBinding> agentMap = new(AIAgentIDEqualityComparer.Instance);
        ExecutorBinding[] agentExecutors = new ExecutorBinding[this._agents.Count];
        ExecutorBinding[] accumulators = new ExecutorBinding[this._agents.Count];
        AIAgentHostOptions options = new() { ReassignOtherAgentsAsUsers = true };
        for (int i = 0; i < this._agents.Count; i++)
        {
            AIAgent agent = this._agents[i];
            ExecutorBinding binding = agent.BindAsExecutor(options);
            agentExecutors[i] = binding;
            agentMap[agent] = binding;
            accumulators[i] = new AggregateTurnMessagesExecutor($"Batcher/{binding.Id}");
        }

        builder.AddFanOutEdge(start, agentExecutors);
        for (int i = 0; i < agentExecutors.Length; i++)
        {
            builder.AddEdge(agentExecutors[i], accumulators[i]);
        }

        Func<IList<List<ChatMessage>>, List<ChatMessage>> aggregator =
            this._aggregator ?? (static lists => (from list in lists where list.Count > 0 select list.Last()).ToList());

        Func<string, string, ValueTask<ConcurrentEndExecutor>> endFactory =
            (_, __) => new(new ConcurrentEndExecutor(agentExecutors.Length, aggregator));

        ExecutorBinding end = endFactory.BindExecutor(ConcurrentEndExecutor.ExecutorId);
        builder.AddFanInBarrierEdge(accumulators, end);

        this.ApplyMetadata(builder);
        this.ApplyOutputDesignations(builder, agentMap, "concurrent", () =>
        {
            builder.WithOutputFrom(end);
            builder.WithIntermediateOutputFrom([.. agentExecutors, .. accumulators]);
        });

        return builder.Build();
    }
}
