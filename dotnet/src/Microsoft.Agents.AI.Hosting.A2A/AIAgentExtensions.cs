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

            // Determine whether to return a task or a message based on the response mode
            // and whether the agent signaled a long-running operation via ContinuationToken.
            bool createTask = responseMode == A2AResponseMode.Task || response.ContinuationToken is not null;
            if (responseMode == A2AResponseMode.Message)
            {
                createTask = false;
            }

            if (!createTask)
            {
                return CreateMessageFromResponse(contextId, response);
            }

            var agentTask = await InitializeTaskAsync(contextId, messageSendParams.Message, cancellationToken).ConfigureAwait(false);

            if (response.ContinuationToken is not null)
            {
                StoreContinuationToken(agentTask, response.ContinuationToken);
                await TransitionToWorkingAsync(agentTask.Id, contextId, response, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                await CompleteWithArtifactAsync(agentTask.Id, response, cancellationToken).ConfigureAwait(false);
            }

            return agentTask;
        }

        AgentMessage CreateMessageFromResponse(string contextId, AgentResponse response)
        {
            return new AgentMessage
            {
                MessageId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
                ContextId = contextId,
                Role = MessageRole.Agent,
                Parts = response.Messages.ToParts(),
                Metadata = response.AdditionalProperties?.ToA2AMetadata()
            };
        }

        Artifact CreateArtifactFromResponse(AgentResponse response)
        {
            // Per the A2A spec (§3.7), task outputs SHOULD be returned as artifacts
            // rather than messages. Messages are for communication; artifacts are for
            // data output produced by the agent.
            return new Artifact
            {
                ArtifactId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
                Parts = response.Messages.ToParts(),
                Metadata = response.AdditionalProperties?.ToA2AMetadata()
            };
        }

        async Task<AgentTask> InitializeTaskAsync(
            string contextId,
            AgentMessage originalMessage,
            CancellationToken cancellationToken)
        {
            AgentTask agentTask = await taskManager.CreateTaskAsync(contextId, cancellationToken: cancellationToken).ConfigureAwait(false);

            // Add the original user message to the task history.
            // The A2A SDK does this internally when it creates tasks via OnTaskCreated,
            // but since we use OnMessageReceived and create the task ourselves, we must
            // add the message manually to maintain a consistent history.
            agentTask.History ??= [];
            agentTask.History.Add(originalMessage);

            // Notify subscribers of the Submitted state per the A2A spec (§4.1.3).
            // CreateTaskAsync persists the task with Submitted status but does not emit
            // an event, so we call UpdateStatusAsync to ensure SSE subscribers see the
            // full Submitted → Working state transition.
            await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Submitted, cancellationToken: cancellationToken).ConfigureAwait(false);

            return agentTask;
        }

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
        void StoreContinuationToken(AgentTask agentTask, ResponseContinuationToken token)
        {
            // Serialize the continuation token into the task's metadata so it survives
            // across requests and is cleaned up with the task itself.
            agentTask.Metadata ??= [];
            agentTask.Metadata[ContinuationTokenMetadataKey] = JsonSerializer.SerializeToElement(
                token,
                continuationTokenJsonOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
        }
#pragma warning restore MEAI001

        async Task TransitionToWorkingAsync(string taskId, string contextId, AgentResponse response, CancellationToken cancellationToken)
        {
            // Include any intermediate progress messages from the response as a status message.
            AgentMessage? progressMessage = response.Messages.Count > 0
                ? CreateMessageFromResponse(contextId, response)
                : null;

            await taskManager.UpdateStatusAsync(taskId, TaskState.Working, message: progressMessage, cancellationToken: cancellationToken).ConfigureAwait(false);
        }

        async Task CompleteWithArtifactAsync(string taskId, AgentResponse response, CancellationToken cancellationToken)
        {
            // Return the output as an artifact per the A2A spec (§3.7).
            var artifact = CreateArtifactFromResponse(response);
            await taskManager.ReturnArtifactAsync(taskId, artifact, cancellationToken).ConfigureAwait(false);

            await taskManager.UpdateStatusAsync(
                taskId,
                TaskState.Completed,
                final: true,
                cancellationToken: cancellationToken).ConfigureAwait(false);
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
                    var response = await hostAgent.RunAsync(
                        session: session,
                        options: new AgentRunOptions { ContinuationToken = continuationToken },
                        cancellationToken: cancellationToken).ConfigureAwait(false);

                    await hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

                    if (response.ContinuationToken is not null)
                    {
                        StoreContinuationToken(agentTask, response.ContinuationToken);
                        await TransitionToWorkingAsync(agentTask.Id, contextId, response, cancellationToken).ConfigureAwait(false);
                    }
                    else
                    {
                        agentTask.Metadata!.Remove(ContinuationTokenMetadataKey);
                        await CompleteWithArtifactAsync(agentTask.Id, response, cancellationToken).ConfigureAwait(false);
                    }

                    return;
                }

                // No pending continuation — process new user messages from task history
                await taskManager.UpdateStatusAsync(agentTask.Id, TaskState.Working, cancellationToken: cancellationToken).ConfigureAwait(false);

                var newResponse = await hostAgent.RunAsync(
                    ExtractChatMessagesFromTaskHistory(agentTask),
                    session: session,
                    cancellationToken: cancellationToken).ConfigureAwait(false);

                await hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);
                await CompleteWithArtifactAsync(agentTask.Id, newResponse, cancellationToken).ConfigureAwait(false);
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
        if (agentTask.History is not { Count: > 0 })
        {
            return [];
        }

        var chatMessages = new List<ChatMessage>(agentTask.History.Count);
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
