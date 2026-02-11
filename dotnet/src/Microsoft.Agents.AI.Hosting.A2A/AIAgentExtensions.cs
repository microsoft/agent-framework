// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
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
    /// <param name="responseMode">Controls whether the A2A response is an <c>AgentMessage</c>, an <c>AgentTask</c>, or determined automatically by the agent.</param>
    /// <param name="jsonSerializerOptions">Optional <see cref="JsonSerializerOptions"/> for serializing and deserializing continuation tokens. Use this when the agent's continuation token contains custom types not registered in the default options. Falls back to <see cref="A2AHostingJsonUtilities.DefaultOptions"/> if not provided.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static ITaskManager MapA2A(
        this AIAgent agent,
        ITaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null,
        AgentSessionStore? agentSessionStore = null,
        A2AResponseMode responseMode = A2AResponseMode.Auto,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentNullException.ThrowIfNull(agent.Name);

        var hostAgent = new AIHostAgent(
            innerAgent: agent,
            sessionStore: agentSessionStore ?? new NoopAgentSessionStore());

        taskManager ??= new TaskManager();

        // Resolve the JSON serializer options for continuation token serialization.
        // Falls back to A2AHostingJsonUtilities.DefaultOptions which chains
        // AgentAbstractionsJsonUtilities (for M.E.AI types) and A2A SDK resolvers.
        JsonSerializerOptions continuationTokenJsonOptions = jsonSerializerOptions ?? A2AHostingJsonUtilities.DefaultOptions;

        // Metadata key used to store continuation tokens for long-running background operations
        // in the AgentTask.Metadata dictionary, persisted by the task store.
        const string ContinuationTokenMetadataKey = "__a2a__continuationToken";

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

            // Only enable background responses when the mode allows task-based results.
            // In Message mode, background responses are never enabled so the agent always completes synchronously.
            bool allowBackground = responseMode != A2AResponseMode.Message;
            var options = messageSendParams.Metadata is not { Count: > 0 }
                ? new AgentRunOptions { AllowBackgroundResponses = allowBackground }
                : new AgentRunOptions { AllowBackgroundResponses = allowBackground, AdditionalProperties = messageSendParams.Metadata.ToAdditionalProperties() };

            var response = await hostAgent.RunAsync(
                messageSendParams.ToChatMessages(),
                session: session,
                options: options,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            await hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

            return responseMode switch
            {
                // Message mode: always return a lightweight AgentMessage.
                A2AResponseMode.Message => CreateMessageFromResponse(contextId, response),

                // Task mode: always create a task. If the agent returned a continuation token,
                // the task is in Working state for later polling. Otherwise it completes immediately.
                A2AResponseMode.Task => response.ContinuationToken is not null
                    ? await CreateWorkingTaskAsync(contextId, messageSendParams.Message, response, cancellationToken).ConfigureAwait(false)
                    : await CreateCompletedTaskAsync(contextId, messageSendParams.Message, response, cancellationToken).ConfigureAwait(false),

                // Auto mode: delegate the decision to the agent. If it returned a continuation
                // token, create a task for tracking. Otherwise return an AgentMessage.
                _ => response.ContinuationToken is not null
                    ? await CreateWorkingTaskAsync(contextId, messageSendParams.Message, response, cancellationToken).ConfigureAwait(false)
                    : CreateMessageFromResponse(contextId, response),
            };
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

        async Task<AgentTask> CreateWorkingTaskAsync(
            string contextId,
            AgentMessage originalMessage,
            AgentResponse initialResponse,
            CancellationToken cancellationToken)
        {
            AgentTask agentTask = await taskManager.CreateTaskAsync(contextId, cancellationToken: cancellationToken).ConfigureAwait(false);

            // Add the original user message to the task history.
            // The A2A SDK does this internally when it creates tasks via OnTaskCreated,
            // but since we use OnMessageReceived and create the task ourselves, we must
            // add the message manually to maintain a consistent history.
            agentTask.History ??= [];
            agentTask.History.Add(originalMessage);

            // Serialize the continuation token into the task's metadata so it survives
            // across requests and is cleaned up with the task itself.
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
            agentTask.Metadata ??= [];
            agentTask.Metadata[ContinuationTokenMetadataKey] = JsonSerializer.SerializeToElement(
                initialResponse.ContinuationToken,
                continuationTokenJsonOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
#pragma warning restore MEAI001

            // Include any intermediate messages from the initial response
            if (initialResponse.Messages.Count > 0)
            {
                var initialMessage = CreateMessageFromResponse(contextId, initialResponse);
                await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Working, message: initialMessage, cancellationToken: cancellationToken).ConfigureAwait(false);
            }
            else
            {
                await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Working, cancellationToken: cancellationToken).ConfigureAwait(false);
            }

            return agentTask;
        }

        async Task<AgentTask> CreateCompletedTaskAsync(
            string contextId,
            AgentMessage originalMessage,
            AgentResponse response,
            CancellationToken cancellationToken)
        {
            AgentTask agentTask = await taskManager.CreateTaskAsync(contextId, cancellationToken: cancellationToken).ConfigureAwait(false);

            // Add the original user message to the task history (see CreateWorkingTaskAsync).
            agentTask.History ??= [];
            agentTask.History.Add(originalMessage);

            var agentMessage = CreateMessageFromResponse(contextId, response);
            await taskManager.UpdateStatusAsync(
                agentTask.Id,
                TaskState.Completed,
                message: agentMessage,
                final: true,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            return agentTask;
        }

        async Task OnTaskUpdatedAsync(AgentTask agentTask, CancellationToken cancellationToken)
        {
            var contextId = agentTask.ContextId ?? Guid.NewGuid().ToString("N");
            var session = await hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);

            try
            {
                // If this task has a pending continuation token in its metadata, check on
                // the background operation instead of processing new messages from history.
                if (TryExtractContinuationToken(agentTask, continuationTokenJsonOptions, out var continuationToken))
                {
                    var pollOptions = new AgentRunOptions { ContinuationToken = continuationToken };
                    var response = await hostAgent.RunAsync(
                        session: session,
                        options: pollOptions,
                        cancellationToken: cancellationToken).ConfigureAwait(false);

                    await hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

                    if (response.ContinuationToken is not null)
                    {
                        // Still working — update the token in metadata and keep the task in Working state
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
                        agentTask.Metadata![ContinuationTokenMetadataKey] = JsonSerializer.SerializeToElement(
                            response.ContinuationToken,
                            continuationTokenJsonOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
#pragma warning restore MEAI001

                        if (response.Messages.Count > 0)
                        {
                            var progressMessage = CreateMessageFromResponse(contextId, response);
                            await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Working, message: progressMessage, cancellationToken: cancellationToken).ConfigureAwait(false);
                        }
                    }
                    else
                    {
                        // Background operation completed — remove the token from metadata
                        agentTask.Metadata!.Remove(ContinuationTokenMetadataKey);

                        var agentMessage = CreateMessageFromResponse(contextId, response);
                        await taskManager.UpdateStatusAsync(
                            agentTask.Id,
                            TaskState.Completed,
                            message: agentMessage,
                            final: true,
                            cancellationToken: cancellationToken).ConfigureAwait(false);
                    }

                    return;
                }

                // No pending continuation — process new user messages from task history
                var chatMessages = ExtractChatMessagesFromTaskHistory(agentTask);

                await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Working, cancellationToken: cancellationToken).ConfigureAwait(false);

                var newResponse = await hostAgent.RunAsync(
                    chatMessages,
                    session: session,
                    cancellationToken: cancellationToken).ConfigureAwait(false);

                await hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

                var completedMessage = CreateMessageFromResponse(contextId, newResponse);
                await taskManager.UpdateStatusAsync(
                    agentTask.Id,
                    TaskState.Completed,
                    message: completedMessage,
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
            // Remove the continuation token from metadata if present.
            // The task has already been marked as cancelled by the TaskManager.
            agentTask.Metadata?.Remove(ContinuationTokenMetadataKey);
            return Task.CompletedTask;
        }

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        static bool TryExtractContinuationToken(AgentTask agentTask, JsonSerializerOptions jsonOptions, out ResponseContinuationToken? continuationToken)
        {
            if (agentTask.Metadata is not null &&
                agentTask.Metadata.TryGetValue(ContinuationTokenMetadataKey, out var tokenElement))
            {
                continuationToken = (ResponseContinuationToken?)JsonSerializer.Deserialize(tokenElement, jsonOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
                return continuationToken is not null;
            }

            continuationToken = null;
            return false;
        }
#pragma warning restore MEAI001
    }

    private static List<ChatMessage> ExtractChatMessagesFromTaskHistory(AgentTask agentTask)
    {
        var chatMessages = new List<ChatMessage>();

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
    /// <param name="responseMode">Controls whether the A2A response is an <c>AgentMessage</c>, an <c>AgentTask</c>, or determined automatically by the agent.</param>
    /// <param name="jsonSerializerOptions">Optional <see cref="JsonSerializerOptions"/> for serializing and deserializing continuation tokens. Use this when the agent's continuation token contains custom types not registered in the default options. Falls back to <see cref="A2AHostingJsonUtilities.DefaultOptions"/> if not provided.</param>
    /// <returns>The configured <see cref="TaskManager"/>.</returns>
    public static ITaskManager MapA2A(
        this AIAgent agent,
        AgentCard agentCard,
        ITaskManager? taskManager = null,
        ILoggerFactory? loggerFactory = null,
        AgentSessionStore? agentSessionStore = null,
        A2AResponseMode responseMode = A2AResponseMode.Auto,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        taskManager = agent.MapA2A(taskManager, loggerFactory, agentSessionStore, responseMode, jsonSerializerOptions);

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
