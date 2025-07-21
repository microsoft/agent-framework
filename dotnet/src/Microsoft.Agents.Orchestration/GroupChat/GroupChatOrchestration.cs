// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// An orchestration that coordinates a group-chat.
/// </summary>
public class GroupChatOrchestration<TInput, TOutput> :
    AgentOrchestration<TInput, TOutput>
{
    internal const string DefaultAgentDescription = "A helpful agent.";

    private readonly GroupChatManager _manager;

    /// <summary>
    /// Initializes a new instance of the <see cref="GroupChatOrchestration{TInput, TOutput}"/> class.
    /// </summary>
    /// <param name="manager">The manages the flow of the group-chat.</param>
    /// <param name="agents">The agents participating in the orchestration.</param>
    public GroupChatOrchestration(GroupChatManager manager, params AIAgent[] agents)
        : base(agents)
    {
        Throw.IfNull(manager, nameof(manager));

        this._manager = manager;
    }

    /// <inheritdoc />
    protected override ValueTask StartAsync(IAgentRuntime runtime, TopicId topic, IEnumerable<ChatMessage> input, ActorType? entryAgent)
    {
        if (!entryAgent.HasValue)
        {
            Throw.ArgumentException(nameof(entryAgent), "Entry agent is not defined.");
        }

        return runtime.PublishMessageAsync(new GroupChatMessages.InputTask(input), entryAgent.Value);
    }

    /// <inheritdoc />
    protected override async ValueTask<ActorType?> RegisterOrchestrationAsync(IAgentRuntime runtime, OrchestrationContext context, RegistrationContext registrar, ILogger logger)
    {
        ActorType outputType = await registrar.RegisterResultTypeAsync<GroupChatMessages.Result>(response => [response.Message]).ConfigureAwait(false);

        int agentCount = 0;
        GroupChatTeam team = [];
        foreach (AIAgent agent in this.Members)
        {
            ++agentCount;
            ActorType agentType = await RegisterAgentAsync(agent, agentCount).ConfigureAwait(false);
            string name = agent.Name ?? agent.Id ?? agentType.Name;
            string? description = agent.Description;

            team[name] = (agentType.Name, description ?? DefaultAgentDescription);

            logger.LogRegisterActor(this.OrchestrationLabel, agentType, "MEMBER", agentCount);

            await runtime.SubscribeAsync(agentType, context.Topic).ConfigureAwait(false);
        }

        ActorType managerType =
            await runtime.RegisterOrchestrationAgentAsync(
                this.FormatAgentType(context.Topic, "Manager"),
                (agentId, runtime) =>
                {
                    GroupChatManagerActor actor = new(agentId, runtime, context, this._manager, team, outputType, context.LoggerFactory.CreateLogger<GroupChatManagerActor>());
                    return new ValueTask<IRuntimeActor>(actor);
                }).ConfigureAwait(false);
        logger.LogRegisterActor(this.OrchestrationLabel, managerType, "MANAGER");

        await runtime.SubscribeAsync(managerType, context.Topic).ConfigureAwait(false);

        return managerType;

        ValueTask<ActorType> RegisterAgentAsync(AIAgent agent, int agentCount) =>
            runtime.RegisterOrchestrationAgentAsync(
                this.FormatAgentType(context.Topic, $"Agent_{agentCount}"),
                (agentId, runtime) =>
                {
                    GroupChatAgentActor actor = new(agentId, runtime, context, agent, context.LoggerFactory.CreateLogger<GroupChatAgentActor>());
                    return new ValueTask<IRuntimeActor>(actor);
                });
    }
}
