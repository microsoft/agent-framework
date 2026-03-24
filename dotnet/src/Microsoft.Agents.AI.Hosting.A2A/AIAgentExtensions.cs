// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides extension methods for attaching A2A (Agent2Agent) messaging capabilities to an <see cref="AIAgent"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public static class AIAgentExtensions
{
    // Metadata key used to store continuation tokens for long-running background operations
    // in the AgentTask.Metadata dictionary, persisted by the task store.
    private const string ContinuationTokenMetadataKey = "__a2a__continuationToken";

    /// <summary>
    /// Attaches A2A (Agent2Agent) messaging capabilities via Message processing to the specified <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="agent">Agent to attach A2A messaging processing capabilities to.</param>
    /// <param name="taskStore">Instance of <see cref="ITaskStore"/> for task persistence. A new <see cref="InMemoryTaskStore"/> will be created if not passed.</param>
    /// <param name="loggerFactory">The logger factory to use for creating <see cref="ILogger"/> instances.</param>
    /// <param name="agentSessionStore">The store to store session contents and metadata.</param>
    /// <param name="runMode">Controls the response behavior of the agent run.</param>
    /// <param name="jsonSerializerOptions">Optional <see cref="JsonSerializerOptions"/> for serializing and deserializing continuation tokens. Use this when the agent's continuation token contains custom types not registered in the default options. Falls back to <see cref="A2AHostingJsonUtilities.DefaultOptions"/> if not provided.</param>
    /// <returns>The configured <see cref="IA2ARequestHandler"/>.</returns>
    public static IA2ARequestHandler MapA2A(
        this AIAgent agent,
        ITaskStore? taskStore = null,
        ILoggerFactory? loggerFactory = null,
        AgentSessionStore? agentSessionStore = null,
        AgentRunMode? runMode = null,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentNullException.ThrowIfNull(agent.Name);

        runMode ??= AgentRunMode.DisallowBackground;
        taskStore ??= new InMemoryTaskStore();

        var hostAgent = new AIHostAgent(
            innerAgent: agent,
            sessionStore: agentSessionStore ?? new NoopAgentSessionStore());

        // Resolve the JSON serializer options for continuation token serialization. May be custom for the user's agent.
        JsonSerializerOptions continuationTokenJsonOptions = jsonSerializerOptions ?? A2AHostingJsonUtilities.DefaultOptions;

        // Wrap the task store to inject pending metadata (continuation tokens, history) during task
        // materialization. The A2AServer runs the handler concurrently with event materialization,
        // so the handler cannot directly access/modify tasks via the store during execution.
        var wrappedTaskStore = new MetadataInjectingTaskStore(taskStore);

        var handler = new AIAgentA2AHandler(hostAgent, runMode, wrappedTaskStore, continuationTokenJsonOptions);
        var logger = loggerFactory?.CreateLogger<A2AServer>() ?? NullLogger<A2AServer>.Instance;
        return new A2AServer(handler, wrappedTaskStore, new ChannelEventNotifier(), logger, null);
    }

    private static Message CreateMessageFromResponse(string contextId, AgentResponse response) =>
        new()
        {
            MessageId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
            ContextId = contextId,
            Role = Role.Agent,
            Parts = response.Messages.ToParts(),
            Metadata = response.AdditionalProperties?.ToA2AMetadata()
        };

    // Task outputs should be returned as artifacts rather than messages:
    // https://a2a-protocol.org/latest/specification/#37-messages-and-artifacts
    private static Artifact CreateArtifactFromResponse(AgentResponse response) =>
        new()
        {
            ArtifactId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
            Parts = response.Messages.ToParts(),
            Metadata = response.AdditionalProperties?.ToA2AMetadata()
        };

    private static void StoreContinuationToken(
        AgentTask agentTask,
        ResponseContinuationToken token,
        JsonSerializerOptions continuationTokenJsonOptions)
    {
        agentTask.Metadata ??= [];
        agentTask.Metadata[ContinuationTokenMetadataKey] = JsonSerializer.SerializeToElement(
            token,
            continuationTokenJsonOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
    }

    private static List<ChatMessage> ExtractChatMessagesFromTaskHistory(AgentTask? agentTask)
    {
        if (agentTask?.History is not { Count: > 0 })
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
    /// Wraps an <see cref="ITaskStore"/> to apply pending modifications (continuation tokens,
    /// message history) when the A2AServer materializes task events. This is needed because
    /// the A2AServer runs handler execution concurrently with event materialization, so the
    /// handler cannot directly modify tasks in the store during execution.
    /// </summary>
    private sealed class MetadataInjectingTaskStore : ITaskStore
    {
        private readonly ITaskStore _inner;
        private readonly ConcurrentDictionary<string, Action<AgentTask>> _pendingModifications = new();

        internal MetadataInjectingTaskStore(ITaskStore inner) => _inner = inner;

        internal void RegisterModification(string taskId, Action<AgentTask> modification)
            => _pendingModifications.AddOrUpdate(taskId, modification, (_, existing) => task =>
            {
                existing(task);
                modification(task);
            });

        internal void ClearModification(string taskId)
            => _pendingModifications.TryRemove(taskId, out _);

        public async Task SaveTaskAsync(string taskId, AgentTask task, CancellationToken cancellationToken)
        {
            if (_pendingModifications.TryRemove(taskId, out var modification))
            {
                modification(task);
            }

            await _inner.SaveTaskAsync(taskId, task, cancellationToken).ConfigureAwait(false);
        }

        public Task<AgentTask?> GetTaskAsync(string taskId, CancellationToken cancellationToken)
            => _inner.GetTaskAsync(taskId, cancellationToken);

        public Task DeleteTaskAsync(string taskId, CancellationToken cancellationToken)
        {
            _pendingModifications.TryRemove(taskId, out _);
            return _inner.DeleteTaskAsync(taskId, cancellationToken);
        }

        public Task<ListTasksResponse> ListTasksAsync(ListTasksRequest request, CancellationToken cancellationToken)
            => _inner.ListTasksAsync(request, cancellationToken);
    }

    /// <summary>
    /// Private handler implementation that bridges AIAgent to the A2A v1 IAgentHandler interface.
    /// </summary>
    private sealed class AIAgentA2AHandler : IAgentHandler
    {
        private readonly AIHostAgent _hostAgent;
        private readonly AgentRunMode _runMode;
        private readonly MetadataInjectingTaskStore _taskStore;
        private readonly JsonSerializerOptions _continuationTokenJsonOptions;

        internal AIAgentA2AHandler(
            AIHostAgent hostAgent,
            AgentRunMode runMode,
            MetadataInjectingTaskStore taskStore,
            JsonSerializerOptions continuationTokenJsonOptions)
        {
            _hostAgent = hostAgent;
            _runMode = runMode;
            _taskStore = taskStore;
            _continuationTokenJsonOptions = continuationTokenJsonOptions;
        }

        public async Task ExecuteAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
        {
            if (context.IsContinuation)
            {
                await HandleTaskUpdateAsync(context, eventQueue, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                await HandleNewMessageAsync(context, eventQueue, cancellationToken).ConfigureAwait(false);
            }
        }

        public Task CancelAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
        {
            // Remove the continuation token from metadata if present.
            // The task has already been marked as cancelled by the A2AServer.
            context.Task?.Metadata?.Remove(ContinuationTokenMetadataKey);
            return Task.CompletedTask;
        }

        private async Task HandleNewMessageAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
        {
            // AIAgent does not support resuming from arbitrary prior tasks.
            // Follow-ups on the *same* task are handled via IsContinuation instead.
            if (context.Message?.ReferenceTaskIds is { Count: > 0 })
            {
                throw new NotSupportedException("ReferenceTaskIds is not supported. AIAgent cannot resume from arbitrary prior task context.");
            }

            var contextId = context.ContextId;
            var session = await _hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);

            var sendRequest = new SendMessageRequest { Message = context.Message!, Metadata = context.Metadata };
            var decisionContext = new A2ARunDecisionContext(sendRequest);
            var allowBackgroundResponses = await _runMode.ShouldRunInBackgroundAsync(decisionContext, cancellationToken).ConfigureAwait(false);

            var options = context.Metadata is not { Count: > 0 }
                ? new AgentRunOptions { AllowBackgroundResponses = allowBackgroundResponses }
                : new AgentRunOptions { AllowBackgroundResponses = allowBackgroundResponses, AdditionalProperties = context.Metadata.ToAdditionalProperties() };

            var chatMessages = new List<ChatMessage>();
            if (context.Message?.Parts is not null)
            {
                chatMessages.Add(context.Message.ToChatMessage());
            }

            var response = await _hostAgent.RunAsync(
                chatMessages,
                session: session,
                options: options,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            await _hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

            if (response.ContinuationToken is null)
            {
                // Simple message response — enqueue a full Message with metadata.
                var replyMessage = CreateMessageFromResponse(contextId, response);
                await eventQueue.EnqueueMessageAsync(replyMessage, cancellationToken).ConfigureAwait(false);
                eventQueue.Complete(null);
            }
            else
            {
                // Long-running task — use TaskUpdater for stateful tracking.
                // Register a pending modification so that when A2AServer materializes
                // the task, the continuation token and original message are injected.
                var continuationToken = response.ContinuationToken;
                var continuationJsonOptions = _continuationTokenJsonOptions;
                var originalMessage = context.Message;
                _taskStore.RegisterModification(context.TaskId, task =>
                {
                    StoreContinuationToken(task, continuationToken, continuationJsonOptions);
                    task.History ??= [];
                    task.History.Add(originalMessage!);
                });

                var taskUpdater = new TaskUpdater(eventQueue, context.TaskId, contextId);
                await taskUpdater.SubmitAsync(cancellationToken).ConfigureAwait(false);

                Message? progressMessage = response.Messages.Count > 0 ? CreateMessageFromResponse(contextId, response) : null;
                await taskUpdater.StartWorkAsync(progressMessage, cancellationToken).ConfigureAwait(false);
            }
        }

        private async Task HandleTaskUpdateAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
        {
            var contextId = context.ContextId;
            var session = await _hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);
            var taskUpdater = new TaskUpdater(eventQueue, context.TaskId, contextId);

            try
            {
                // Discard any stale continuation token — the incoming user message supersedes
                // any previous background operation.
                var agentTask = context.Task;
                agentTask?.Metadata?.Remove(ContinuationTokenMetadataKey);

                // Emit the existing task so the materializer has a non-null response.
                // TaskUpdater status/artifact events alone use EnqueueStatusUpdateAsync
                // and EnqueueArtifactUpdateAsync, which set StreamResponse.StatusUpdate
                // and StreamResponse.ArtifactUpdate respectively. The materializer only
                // initializes the response from events with StreamResponse.Task or
                // StreamResponse.Message set. EnqueueTaskAsync sets StreamResponse.Task.
                await eventQueue.EnqueueTaskAsync(agentTask!, cancellationToken).ConfigureAwait(false);

                await taskUpdater.StartWorkAsync(null, cancellationToken).ConfigureAwait(false);

                var response = await _hostAgent.RunAsync(
                    ExtractChatMessagesFromTaskHistory(agentTask),
                    session: session,
                    options: new AgentRunOptions { AllowBackgroundResponses = true },
                    cancellationToken: cancellationToken).ConfigureAwait(false);

                await _hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

                if (response.ContinuationToken is not null)
                {
                    // Register continuation token injection for the next task save.
                    var continuationToken = response.ContinuationToken;
                    var continuationJsonOptions = _continuationTokenJsonOptions;
                    _taskStore.RegisterModification(context.TaskId, task =>
                        StoreContinuationToken(task, continuationToken, continuationJsonOptions));

                    Message? progressMessage = response.Messages.Count > 0 ? CreateMessageFromResponse(contextId, response) : null;
                    await taskUpdater.StartWorkAsync(progressMessage, cancellationToken).ConfigureAwait(false);
                }
                else
                {
                    var artifact = CreateArtifactFromResponse(response);
                    await taskUpdater.AddArtifactAsync(artifact.Parts ?? [], artifact.ArtifactId, artifact.Name, artifact.Description, true, false, cancellationToken).ConfigureAwait(false);
                    await taskUpdater.CompleteAsync(null, cancellationToken).ConfigureAwait(false);
                }
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception)
            {
                await taskUpdater.FailAsync(null, cancellationToken).ConfigureAwait(false);
                throw;
            }
        }
    }
}
