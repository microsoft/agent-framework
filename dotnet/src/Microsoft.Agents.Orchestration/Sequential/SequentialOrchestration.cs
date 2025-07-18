// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An orchestration that provides the input message to the first agent
/// and sequentially passes each agent result to the next agent.
/// </summary>
public class SequentialOrchestration<TInput, TOutput> : AgentOrchestration<TInput, TOutput>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="SequentialOrchestration{TInput, TOutput}"/> class.
    /// </summary>
    /// <param name="agents">The agents participating in the orchestration.</param>
    public SequentialOrchestration(params AIAgent[] agents)
        : base(agents)
    {
    }

    /// <inheritdoc />
    protected override async ValueTask StartAsync(IAgentRuntime runtime, TopicId topic, IEnumerable<ChatMessage> input, ActorType? entryAgent)
    {
        if (!entryAgent.HasValue)
        {
            throw new ArgumentException("Entry agent is not defined.", nameof(entryAgent));
        }
        await runtime.PublishMessageAsync(new SequentialMessages.Request([.. input]), entryAgent.Value).ConfigureAwait(false);
    }

    /// <inheritdoc />
    protected override async ValueTask<ActorType?> RegisterOrchestrationAsync(IAgentRuntime runtime, OrchestrationContext context, RegistrationContext registrar, ILogger logger)
    {
        ActorType outputType = await registrar.RegisterResultTypeAsync<SequentialMessages.Response>(response => [response.Message]).ConfigureAwait(false);

        // Each agent handsoff its result to the next agent.
        ActorType nextAgent = outputType;
        for (int index = this.Members.Count - 1; index >= 0; --index)
        {
            AIAgent agent = this.Members[index];
            nextAgent = await RegisterAgentAsync(agent, index, nextAgent).ConfigureAwait(false);

            logger.LogRegisterActor(this.OrchestrationLabel, nextAgent, "MEMBER", index + 1);
        }

        return nextAgent;

        ValueTask<ActorType> RegisterAgentAsync(AIAgent agent, int index, ActorType nextAgent) =>
            runtime.RegisterOrchestrationAgentAsync(
                this.GetAgentType(context.Topic, index),
                (agentId, runtime) =>
                {
                    SequentialActor actor = new(agentId, runtime, context, agent, nextAgent, context.LoggerFactory.CreateLogger<SequentialActor>());
                    return new ValueTask<IRuntimeActor>(actor);
                });
    }

    private ActorType GetAgentType(TopicId topic, int index) => this.FormatAgentType(topic, $"Agent_{index + 1}");
}
