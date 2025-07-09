// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Orchestration.Extensions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration.Concurrent;

/// <summary>
/// An orchestration that broadcasts the input message to each agent.
/// </summary>
/// <remarks>
/// <c>TOutput</c> must be an array type for <see cref="ConcurrentOrchestration"/>.
/// </remarks>
public class ConcurrentOrchestration<TInput, TOutput>
    : AgentOrchestration<TInput, TOutput>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ConcurrentOrchestration{TInput, TOutput}"/> class.
    /// </summary>
    /// <param name="agents">The agents participating in the orchestration.</param>
    public ConcurrentOrchestration(params Agent[] agents)
        : base(agents)
    {
    }

    /// <inheritdoc />
    protected override ValueTask StartAsync(IAgentRuntime runtime, TopicId topic, IEnumerable<ChatMessage> input, AgentType? entryAgent)
    {
        return runtime.PublishMessageAsync(input.AsInputMessage(), topic);
    }

    /// <inheritdoc />
    protected override async ValueTask<AgentType?> RegisterOrchestrationAsync(IAgentRuntime runtime, OrchestrationContext context, RegistrationContext registrar, ILogger logger)
    {
        AgentType outputType = await registrar.RegisterResultTypeAsync<ConcurrentMessages.Result[]>(response => [.. response.Select(r => r.Message)]).ConfigureAwait(false);

        // Register result actor
        AgentType resultType = this.FormatAgentType(context.Topic, "Results");
        await runtime.RegisterOrchestrationAgentAsync(
            resultType,
            async (agentId, runtime) =>
            {
                ConcurrentResultActor actor = new(agentId, runtime, context, outputType, this.Members.Count, context.LoggerFactory.CreateLogger<ConcurrentResultActor>());
                return actor;
            }).ConfigureAwait(false);
        logger.LogRegisterActor(this.OrchestrationLabel, resultType, "RESULTS");

        // Register member actors - All agents respond to the same message.
        int agentCount = 0;
        foreach (Agent agent in this.Members)
        {
            ++agentCount;

            AgentType agentType =
                await runtime.RegisterAgentFactoryAsync(
                    this.FormatAgentType(context.Topic, $"Agent_{agentCount}"),
                    (agentId, runtime) =>
                    {
                        ConcurrentActor actor = new(agentId, runtime, context, agent, resultType, context.LoggerFactory.CreateLogger<ConcurrentActor>());
#if !NETCOREAPP
                        return new ValueTask<IHostableAgent>(actor);
#else
                        return ValueTask.FromResult<IHostableAgent>(actor);
#endif
                    }).ConfigureAwait(false);

            logger.LogRegisterActor(this.OrchestrationLabel, agentType, "MEMBER", agentCount);

            await runtime.SubscribeAsync(agentType, context.Topic).ConfigureAwait(false);
        }

        return null;
    }
}
