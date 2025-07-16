// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An orchestration that provides the input message to the first agent
/// and sequentially passes each agent result to the next agent.
/// </summary>
public class HandoffOrchestration<TInput, TOutput> : AgentOrchestration<TInput, TOutput>
{
    private readonly OrchestrationHandoffs _handoffs;

    /// <summary>
    /// Initializes a new instance of the <see cref="HandoffOrchestration{TInput, TOutput}"/> class.
    /// </summary>
    /// <param name="handoffs">Defines the handoff connections for each agent.</param>
    /// <param name="agents">Additional agents participating in the orchestration that weren't passed to <paramref name="handoffs"/>.</param>
    public HandoffOrchestration(OrchestrationHandoffs handoffs, params AIAgent[] agents) : base(
            agents is { Length: 0 } ? handoffs.Agents.ToArray() :
            handoffs.Agents is { Count: 0 } ? agents :
            handoffs.Agents.Concat(agents).Distinct().ToArray())
    {
        // Create list of distinct agent names
        HashSet<string> agentNames = new(base.Members.Select(a => a.Name ?? a.Id), StringComparer.Ordinal)
        {
            handoffs.FirstAgentName
        };

        // Extract names from handoffs that don't align with a member agent.
        string[] badNames = [.. handoffs.Keys.Concat(handoffs.Values.SelectMany(h => h.Keys)).Where(name => !agentNames.Contains(name))];

        // Fail fast if invalid names are present.
        if (badNames.Length > 0)
        {
            Throw.ArgumentException(nameof(handoffs), $"The following agents are not defined in the orchestration: {string.Join(", ", badNames)}");
        }

        this._handoffs = handoffs;
    }

    /// <summary>
    /// Gets or sets the callback to be invoked for interactive input.
    /// </summary>
    public Func<ValueTask<ChatMessage>>? InteractiveCallback { get; init; }

    /// <inheritdoc />
    protected override async ValueTask StartAsync(IAgentRuntime runtime, TopicId topic, IEnumerable<ChatMessage> input, ActorType? entryAgent)
    {
        Throw.IfNull(entryAgent);

        await runtime.PublishMessageAsync(new HandoffMessages.InputTask([.. input]), topic).ConfigureAwait(false);
        await runtime.PublishMessageAsync(new HandoffMessages.Request(), entryAgent.Value).ConfigureAwait(false);
    }

    /// <inheritdoc />
    protected override async ValueTask<ActorType?> RegisterOrchestrationAsync(IAgentRuntime runtime, OrchestrationContext context, RegistrationContext registrar, ILogger logger)
    {
        ActorType outputType = await registrar.RegisterResultTypeAsync<HandoffMessages.Result>(response => [response.Message]).ConfigureAwait(false);

        // Each agent handsoff its result to the next agent.
        Dictionary<string, ActorType> agentMap = [];
        Dictionary<string, HandoffLookup> handoffMap = [];
        ActorType agentType = outputType;
        for (int index = this.Members.Count - 1; index >= 0; --index)
        {
            AIAgent agent = this.Members[index];
            HandoffLookup map = [];
            handoffMap[agent.Name ?? agent.Id] = map;
            agentType =
                await runtime.RegisterOrchestrationAgentAsync(
                    this.GetAgentType(context.Topic, index),
                    (agentId, runtime) =>
                    {
                        HandoffActor actor =
                            new(agentId, runtime, context, (ChatClientAgent)agent, map, outputType, context.LoggerFactory.CreateLogger<HandoffActor>())
                            {
                                InteractiveCallback = this.InteractiveCallback
                            };
                        return new ValueTask<IRuntimeActor>(actor);
                    }).ConfigureAwait(false);
            agentMap[agent.Name ?? agent.Id] = agentType;

            await runtime.SubscribeAsync(agentType, context.Topic).ConfigureAwait(false);

            logger.LogRegisterActor(this.OrchestrationLabel, agentType, "MEMBER", index + 1);
        }

        // Complete the handoff model
        foreach (KeyValuePair<string, AgentHandoffs> handoffs in this._handoffs)
        {
            // Retrieve the map for the agent (every agent had an empty map created)
            HandoffLookup agentHandoffs = handoffMap[handoffs.Key];
            foreach (KeyValuePair<string, string> handoff in handoffs.Value)
            {
                // name = (type,description)
                agentHandoffs[handoff.Key] = (agentMap[handoff.Key], handoff.Value);
            }
        }

        return agentMap[this._handoffs.FirstAgentName];
    }

    private ActorType GetAgentType(TopicId topic, int index) => this.FormatAgentType(topic, $"Agent_{index + 1}");
}
