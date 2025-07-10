﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Orchestration.Extensions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration.GroupChat;

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
    public GroupChatOrchestration(GroupChatManager manager, params Agent[] agents)
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
            throw new ArgumentException("Entry agent is not defined.", nameof(entryAgent));
        }
        return runtime.PublishMessageAsync(input.AsInputTaskMessage(), entryAgent.Value);
    }

    /// <inheritdoc />
    protected override async ValueTask<ActorType?> RegisterOrchestrationAsync(IAgentRuntime runtime, OrchestrationContext context, RegistrationContext registrar, ILogger logger)
    {
        ActorType outputType = await registrar.RegisterResultTypeAsync<GroupChatMessages.Result>(response => [response.Message]).ConfigureAwait(false);

        int agentCount = 0;
        GroupChatTeam team = [];
        foreach (Agent agent in this.Members)
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

        ValueTask<ActorType> RegisterAgentAsync(Agent agent, int agentCount) =>
            runtime.RegisterOrchestrationAgentAsync(
                this.FormatAgentType(context.Topic, $"Agent_{agentCount}"),
                (agentId, runtime) =>
                {
                    GroupChatAgentActor actor = new(agentId, runtime, context, agent, context.LoggerFactory.CreateLogger<GroupChatAgentActor>());
                    return new ValueTask<IRuntimeActor>(actor);
                });
    }
}
