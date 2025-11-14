// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides extension methods for attaching A2A (Agent2Agent) messaging capabilities to an <see cref="AIAgent"/>.
/// </summary>
public static class AIAgentExtensions
{
    /// <summary>
    /// Attaches A2A (Agent2Agent) messaging capabilities via Message processing to the specified <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">Agent to attach A2A messaging processing capabilities to.</param>
    /// <param name="taskManager">Instance of <see cref="TaskManager"/> to configure for A2A messaging. New instance will be created if not passed.</param>
    /// <param name="loggerFactory">The logger factory to use for creating <see cref="ILogger"/> instances.</param>
    /// <param name="agentThreadStore">The store to store thread contents and metadata.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static ITaskManager MapA2A(
        this AIAgent agent,
        ITaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null,
        AgentThreadStore? agentThreadStore = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentNullException.ThrowIfNull(agent.Name);

        var hostAgent = new AIHostAgent(
            innerAgent: agent,
            threadStore: agentThreadStore ?? new NoopAgentThreadStore());

        taskManager ??= new TaskManager();
        taskManager.OnMessageReceived += OnMessageReceivedAsync;
        return taskManager;

        async Task<A2AResponse> OnMessageReceivedAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
        {
            var contextId = messageSendParams.Message.ContextId ?? Guid.NewGuid().ToString("N");
            var thread = await hostAgent.GetOrCreateThreadAsync(contextId, cancellationToken).ConfigureAwait(false);

            var response = await hostAgent.RunAsync(
                messageSendParams.ToChatMessages(),
                thread: thread,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            await hostAgent.SaveThreadAsync(contextId, thread, cancellationToken).ConfigureAwait(false);
            var parts = response.Messages.ToParts();
            return new AgentMessage
            {
                MessageId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
                ContextId = contextId,
                Role = MessageRole.Agent,
                Parts = parts
            };
        }
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) messaging capabilities via Message processing to the specified <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">Agent to attach A2A messaging processing capabilities to.</param>
    /// <param name="agentCard">The agent card to return on query.</param>
    /// <param name="taskManager">Instance of <see cref="TaskManager"/> to configure for A2A messaging. New instance will be created if not passed.</param>
    /// <param name="loggerFactory">The logger factory to use for creating <see cref="ILogger"/> instances.</param>
    /// <param name="agentThreadStore">The store to store thread contents and metadata.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static ITaskManager MapA2A(
        this AIAgent agent,
        AgentCard agentCard,
        ITaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null,
        AgentThreadStore? agentThreadStore = null)
    {
        taskManager = agent.MapA2A(taskManager, loggerFactory, agentThreadStore);

        taskManager.OnAgentCardQuery += (context, query) =>
        {
            // A2A SDK assigns the url on its own
            // we can help user if they did not set Url explicitly.
            if (string.IsNullOrEmpty(agentCard.Url))
            {
                var agentCardUrl = context.TrimEnd('/');
                if (!context.EndsWith("/v1/card", StringComparison.Ordinal))
                {
                    agentCardUrl += "/v1/card";
                }

                agentCard.Url = agentCardUrl;
            }

            return Task.FromResult(agentCard);
        };
        return taskManager;
    }
}
