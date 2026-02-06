// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Extensions.AI;
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
    /// <param name="agentSessionStore">The store to store session contents and metadata.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static ITaskManager MapA2A(
        this AIAgent agent,
        ITaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null,
        AgentSessionStore? agentSessionStore = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentNullException.ThrowIfNull(agent.Name);

        var hostAgent = new AIHostAgent(
            innerAgent: agent,
            sessionStore: agentSessionStore ?? new NoopAgentSessionStore());

        taskManager ??= new TaskManager();

        // OnMessageReceived handles both message-only and task-based flows.
        // The A2A SDK prioritizes OnMessageReceived over OnTaskCreated when both are set,
        // so we consolidate all initial message handling here and return either
        // an AgentMessage or AgentTask depending on the agent response.
        // When the agent returns a ContinuationToken (long-running operation), a task is
        // created for stateful tracking. Otherwise a lightweight AgentMessage is returned.
        // See https://github.com/a2aproject/a2a-dotnet/issues/275
        taskManager.OnMessageReceived += OnMessageReceivedAsync;

        // task flow for subsequent updates and cancellations
        taskManager.OnTaskUpdated += OnTaskUpdatedAsync;
        taskManager.OnTaskCancelled += OnTaskCancelledAsync;

        return taskManager;

        async Task<A2AResponse> OnMessageReceivedAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
        {
            var contextId = messageSendParams.Message.ContextId ?? Guid.NewGuid().ToString("N");
            var session = await hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);
            var options = messageSendParams.Metadata is not { Count: > 0 }
                ? null
                : new AgentRunOptions { AdditionalProperties = messageSendParams.Metadata.ToAdditionalProperties() };

            var response = await hostAgent.RunAsync(
                messageSendParams.ToChatMessages(),
                session: session,
                options: options,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            await hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

            // If the agent returned a continuation token, this is a long-running operation
            // that requires task-based tracking. Otherwise return a lightweight message.
            if (response.ContinuationToken is not null)
            {
                return await CreateTaskFromResponseAsync(contextId, response, cancellationToken).ConfigureAwait(false);
            }

            return CreateMessageFromResponse(contextId, response);
        }

        AgentMessage CreateMessageFromResponse(string contextId, AgentResponse response)
        {
            var parts = response.Messages.ToParts();
            return new AgentMessage
            {
                MessageId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
                ContextId = contextId,
                Role = MessageRole.Agent,
                Parts = parts,
                Metadata = response.AdditionalProperties?.ToA2AMetadata()
            };
        }

        async Task<A2AResponse> CreateTaskFromResponseAsync(
            string contextId,
            AgentResponse response,
            CancellationToken cancellationToken)
        {
            AgentTask agentTask = await taskManager.CreateTaskAsync(contextId, cancellationToken: cancellationToken).ConfigureAwait(false);
            await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Working, cancellationToken: cancellationToken).ConfigureAwait(false);

            try
            {
                var parts = response.Messages.ToParts();
                var agentMessage = new AgentMessage
                {
                    MessageId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
                    ContextId = contextId,
                    Role = MessageRole.Agent,
                    Parts = parts,
                    Metadata = response.AdditionalProperties?.ToA2AMetadata()
                };

                await taskManager.UpdateStatusAsync(
                    agentTask.Id,
                    TaskState.Completed,
                    message: agentMessage,
                    final: true,
                    cancellationToken: cancellationToken).ConfigureAwait(false);

                return (await taskManager.GetTaskAsync(
                    new TaskQueryParams { Id = agentTask.Id },
                    cancellationToken).ConfigureAwait(false))!;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception)
            {
                await taskManager.UpdateStatusAsync(
                    agentTask.Id,
                    TaskState.Failed,
                    final: true,
                    cancellationToken: cancellationToken).ConfigureAwait(false);
                throw;
            }
        }

        async Task OnTaskUpdatedAsync(AgentTask agentTask, CancellationToken cancellationToken)
        {
            var contextId = agentTask.ContextId ?? Guid.NewGuid().ToString("N");
            var session = await hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);

            // Extract the latest user message from task history
            var chatMessages = ExtractChatMessagesFromTaskHistory(agentTask);

            // Update task status to working
            await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Working, cancellationToken: cancellationToken).ConfigureAwait(false);

            try
            {
                var response = await hostAgent.RunAsync(
                    chatMessages,
                    session: session,
                    cancellationToken: cancellationToken).ConfigureAwait(false);

                await hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

                var parts = response.Messages.ToParts();
                var agentMessage = new AgentMessage
                {
                    MessageId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
                    ContextId = contextId,
                    Role = MessageRole.Agent,
                    Parts = parts,
                    Metadata = response.AdditionalProperties?.ToA2AMetadata()
                };

                // Update task status to completed with the response message
                await taskManager.UpdateStatusAsync(
                    agentTask.Id,
                    TaskState.Completed,
                    message: agentMessage,
                    final: true,
                    cancellationToken: cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception)
            {
                await taskManager.UpdateStatusAsync(
                    agentTask.Id,
                    TaskState.Failed,
                    final: true,
                    cancellationToken: cancellationToken).ConfigureAwait(false);
                throw;
            }
        }

        Task OnTaskCancelledAsync(AgentTask agentTask, CancellationToken cancellationToken)
        {
            // The task has already been marked as cancelled by the TaskManager.
            // This callback is for any cleanup or notification logic needed.
            // Currently, no additional action is required.
            return Task.CompletedTask;
        }
    }

    private static System.Collections.Generic.List<ChatMessage> ExtractChatMessagesFromTaskHistory(AgentTask agentTask)
    {
        var chatMessages = new System.Collections.Generic.List<ChatMessage>();

        if (agentTask.History is null || agentTask.History.Count == 0)
        {
            return chatMessages;
        }

        foreach (var message in agentTask.History)
        {
            chatMessages.Add(message.ToChatMessage());
        }

        return chatMessages;
    }

    /// <summary>
    /// Attaches A2A (Agent2Agent) messaging capabilities via Message processing to the specified <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">Agent to attach A2A messaging processing capabilities to.</param>
    /// <param name="agentCard">The agent card to return on query.</param>
    /// <param name="taskManager">Instance of <see cref="TaskManager"/> to configure for A2A messaging. New instance will be created if not passed.</param>
    /// <param name="loggerFactory">The logger factory to use for creating <see cref="ILogger"/> instances.</param>
    /// <param name="agentSessionStore">The store to store session contents and metadata.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static ITaskManager MapA2A(
        this AIAgent agent,
        AgentCard agentCard,
        ITaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null,
        AgentSessionStore? agentSessionStore = null)
    {
        taskManager = agent.MapA2A(taskManager, loggerFactory, agentSessionStore);

        taskManager.OnAgentCardQuery += (context, query) =>
        {
            // A2A SDK assigns the url on its own
            // we can help user if they did not set Url explicitly.
            if (string.IsNullOrEmpty(agentCard.Url))
            {
                agentCard.Url = context.TrimEnd('/');
            }

            return Task.FromResult(agentCard);
        };
        return taskManager;
    }
}
