// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Represents an <see cref="AIAgent"/> that can interact with remote agents that are exposed via the A2A protocol
/// </summary>
/// <remarks>
/// This agent supports only messages as a response from A2A agents.
/// Support for tasks will be added later as part of the long-running
/// executions work.
/// </remarks>
public sealed class A2AAgent : AIAgent
{
    private static readonly AIAgentMetadata s_agentMetadata = new("a2a");

    private readonly IA2AClient _a2aClient;
    private readonly string? _id;
    private readonly string? _name;
    private readonly string? _description;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="A2AAgent"/> class.
    /// </summary>
    /// <param name="a2aClient">The A2A client to use for interacting with A2A agents.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The the name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public A2AAgent(IA2AClient a2aClient, string? id = null, string? name = null, string? description = null, ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(a2aClient);

        this._a2aClient = a2aClient;
        this._id = id;
        this._name = name;
        this._description = description;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<A2AAgent>();
    }

    /// <inheritdoc/>
    protected sealed override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new A2AAgentSession());

    /// <summary>
    /// Get a new <see cref="AgentSession"/> instance using an existing context id, to continue that conversation.
    /// </summary>
    /// <param name="contextId">The context id to continue.</param>
    /// <returns>A value task representing the asynchronous operation. The task result contains a new <see cref="AgentSession"/> instance.</returns>
    public ValueTask<AgentSession> CreateSessionAsync(string contextId)
        => new(new A2AAgentSession() { ContextId = Throw.IfNullOrWhitespace(contextId) });

    /// <summary>
    /// Get a new <see cref="AgentSession"/> instance using an existing context id and task id, to resume that conversation from a specific task.
    /// </summary>
    /// <param name="contextId">The context id to continue.</param>
    /// <param name="taskId">The task id to resume from.</param>
    /// <returns>A value task representing the asynchronous operation. The task result contains a new <see cref="AgentSession"/> instance.</returns>
    public ValueTask<AgentSession> CreateSessionAsync(string contextId, string taskId)
        => new(new A2AAgentSession() { ContextId = Throw.IfNullOrWhitespace(contextId), TaskId = Throw.IfNullOrWhitespace(taskId) });

    /// <inheritdoc/>
    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(session);

        if (session is not A2AAgentSession typedSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(A2AAgentSession)}' can be serialized by this agent.");
        }

        return new(typedSession.Serialize(jsonSerializerOptions));
    }

    /// <inheritdoc/>
    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => new(A2AAgentSession.Deserialize(serializedState, jsonSerializerOptions));

    /// <inheritdoc/>
    protected override async Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        A2AAgentSession typedSession = await this.GetA2ASessionAsync(session, options, cancellationToken).ConfigureAwait(false);

        this._logger.LogA2AAgentInvokingAgent(nameof(RunAsync), this.Id, this.Name);

        if (GetContinuationToken(messages, options) is { } token)
        {
            AgentTask agentTask = await this._a2aClient.GetTaskAsync(new GetTaskRequest { Id = token.TaskId }, cancellationToken).ConfigureAwait(false);

            this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, this.Name);

            UpdateSession(typedSession, agentTask.ContextId, agentTask.Id);

            return this.ConvertToAgentResponse(agentTask);
        }

        SendMessageRequest sendParams = new()
        {
            Message = CreateA2AMessage(typedSession, messages),
            Metadata = options?.AdditionalProperties?.ToA2AMetadata(),
            Configuration = new SendMessageConfiguration { ReturnImmediately = options?.AllowBackgroundResponses is true }
        };

        SendMessageResponse a2aResponse = await this._a2aClient.SendMessageAsync(sendParams, cancellationToken).ConfigureAwait(false);

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, this.Name);

        if (a2aResponse.PayloadCase == SendMessageResponseCase.Message)
        {
            var message = a2aResponse.Message!;

            UpdateSession(typedSession, message.ContextId);

            return this.ConvertToAgentResponse(message);
        }

        if (a2aResponse.PayloadCase == SendMessageResponseCase.Task)
        {
            var agentTask = a2aResponse.Task!;

            UpdateSession(typedSession, agentTask.ContextId, agentTask.Id);

            return this.ConvertToAgentResponse(agentTask);
        }

        throw new NotSupportedException($"Only Message and AgentTask responses are supported from A2A agents. Received: {a2aResponse.PayloadCase}");
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        A2AAgentSession typedSession = await this.GetA2ASessionAsync(session, options, cancellationToken).ConfigureAwait(false);

        this._logger.LogA2AAgentInvokingAgent(nameof(RunStreamingAsync), this.Id, this.Name);

        ConfiguredCancelableAsyncEnumerable<StreamResponse> streamEvents;

        if (GetContinuationToken(messages, options) is { } token)
        {
            streamEvents = this.SubscribeToTaskWithFallbackAsync(token.TaskId, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            SendMessageRequest sendParams = new()
            {
                Message = CreateA2AMessage(typedSession, messages),
                Metadata = options?.AdditionalProperties?.ToA2AMetadata()
            };

            streamEvents = this._a2aClient.SendStreamingMessageAsync(sendParams, cancellationToken).ConfigureAwait(false);
        }

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunStreamingAsync), this.Id, this.Name);

        string? contextId = null;
        string? taskId = null;

        await foreach (var streamResponse in streamEvents)
        {
            switch (streamResponse.PayloadCase)
            {
                case StreamResponseCase.Message:
                    var message = streamResponse.Message!;
                    contextId = message.ContextId;
                    yield return this.ConvertToAgentResponseUpdate(message);
                    break;

                case StreamResponseCase.Task:
                    var task = streamResponse.Task!;
                    contextId = task.ContextId;
                    taskId = task.Id;
                    yield return this.ConvertToAgentResponseUpdate(task);
                    break;

                case StreamResponseCase.StatusUpdate:
                    var statusUpdate = streamResponse.StatusUpdate!;
                    contextId = statusUpdate.ContextId;
                    taskId = statusUpdate.TaskId;
                    yield return this.ConvertToAgentResponseUpdate(statusUpdate);
                    break;

                case StreamResponseCase.ArtifactUpdate:
                    var artifactUpdate = streamResponse.ArtifactUpdate!;
                    contextId = artifactUpdate.ContextId;
                    taskId = artifactUpdate.TaskId;
                    yield return this.ConvertToAgentResponseUpdate(artifactUpdate);
                    break;

                default:
                    throw new NotSupportedException($"Only message, task, task update events are supported from A2A agents. Received: {streamResponse.PayloadCase}");
            }
        }

        UpdateSession(typedSession, contextId, taskId);
    }

    /// <inheritdoc/>
    protected override string? IdCore => this._id;

    /// <inheritdoc/>
    public override string? Name => this._name;

    /// <inheritdoc/>
    public override string? Description => this._description;

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
        => base.GetService(serviceType, serviceKey)
           ?? (serviceType == typeof(IA2AClient) ? this._a2aClient
            : serviceType == typeof(AIAgentMetadata) ? s_agentMetadata
            : null);

    private async ValueTask<A2AAgentSession> GetA2ASessionAsync(AgentSession? session, AgentRunOptions? options, CancellationToken cancellationToken)
    {
        // Aligning with other agent implementations that support background responses, where
        // a session is required for background responses to prevent inconsistent experience
        // for callers if they forget to provide the session for initial or follow-up runs.
        if (options?.AllowBackgroundResponses is true && session is null)
        {
            throw new InvalidOperationException("A session must be provided when AllowBackgroundResponses is enabled.");
        }

        session ??= await this.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        if (session is not A2AAgentSession typedSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(A2AAgentSession)}' can be used by this agent.");
        }

        return typedSession;
    }

    /// <summary>
    /// Subscribes to task updates, falling back to <see cref="A2AClient.GetTaskAsync"/>
    /// when the task has already reached a terminal state and the server responds with
    /// <see cref="A2AErrorCode.UnsupportedOperation"/>.
    /// </summary>
    /// <remarks>
    /// Per A2A spec §3.1.6, subscribing to a task in a terminal state (completed, failed,
    /// canceled, or rejected) results in an <c>UnsupportedOperationError</c>.
    /// See: <see href="https://a2a-protocol.org/latest/specification/#332-error-handling"/>.
    /// </remarks>
    private async IAsyncEnumerable<StreamResponse> SubscribeToTaskWithFallbackAsync(
        string taskId,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var subscribeStream = this._a2aClient.SubscribeToTaskAsync(new SubscribeToTaskRequest { Id = taskId }, cancellationToken);

        var enumerator = subscribeStream.GetAsyncEnumerator(cancellationToken);

        // yield return cannot appear inside a try block that has catch clauses,
        // so we manually advance the enumerator within try/catch and yield outside it.
        // The outer try/finally (no catch) is allowed to contain yield return in C#.
        StreamResponse? fallbackResponse = null;
        bool disposed = false;

        try
        {
            while (true)
            {
                bool hasNext;
                try
                {
                    hasNext = await enumerator.MoveNextAsync().ConfigureAwait(false);
                }
                catch (A2AException ex) when (ex.ErrorCode == A2AErrorCode.UnsupportedOperation)
                {
                    this._logger.LogA2ASubscribeToTaskFallback(this.Id, this.Name, taskId, ex.Message);

                    // Dispose the enumerator before the fallback call to release the HTTP/SSE connection.
                    await enumerator.DisposeAsync().ConfigureAwait(false);
                    disposed = true;

                    AgentTask agentTask = await this._a2aClient.GetTaskAsync(new GetTaskRequest { Id = taskId }, cancellationToken).ConfigureAwait(false);

                    fallbackResponse = new StreamResponse { Task = agentTask };
                    break;
                }

                if (!hasNext)
                {
                    break;
                }

                yield return enumerator.Current;
            }

            if (fallbackResponse is not null)
            {
                yield return fallbackResponse;
            }
        }
        finally
        {
            if (!disposed)
            {
                await enumerator.DisposeAsync().ConfigureAwait(false);
            }
        }
    }

    private static void UpdateSession(A2AAgentSession? session, string? contextId, string? taskId = null)
    {
        if (session is null)
        {
            return;
        }

        // Surface cases where the A2A agent responds with a response that
        // has a different context Id than the session's conversation Id.
        if (session.ContextId is not null && contextId is not null && session.ContextId != contextId)
        {
            throw new InvalidOperationException(
                $"The {nameof(contextId)} returned from the A2A agent is different from the conversation Id of the provided {nameof(AgentSession)}.");
        }

        // Assign a server-generated context Id to the session if it's not already set.
        session.ContextId ??= contextId;
        session.TaskId = taskId;
    }

    private static Message CreateA2AMessage(A2AAgentSession typedSession, IEnumerable<ChatMessage> messages)
    {
        var a2aMessage = messages.ToA2AMessage();

        // Linking the message to the existing conversation, if any.
        // See: https://github.com/a2aproject/A2A/blob/main/docs/topics/life-of-a-task.md#group-related-interactions
        a2aMessage.ContextId = typedSession.ContextId;

        // Link the message as a follow-up to an existing task, if any.
        // See: https://github.com/a2aproject/A2A/blob/main/docs/topics/life-of-a-task.md#task-refinements
        a2aMessage.ReferenceTaskIds = typedSession.TaskId is null ? null : [typedSession.TaskId];

        return a2aMessage;
    }

    private static A2AContinuationToken? GetContinuationToken(IEnumerable<ChatMessage> messages, AgentRunOptions? options = null)
    {
        if (options?.ContinuationToken is ResponseContinuationToken token)
        {
            if (messages.Any())
            {
                throw new InvalidOperationException("Messages are not allowed when continuing a background response using a continuation token.");
            }

            return A2AContinuationToken.FromToken(token);
        }

        return null;
    }

    private static A2AContinuationToken? CreateContinuationToken(string taskId, TaskState state)
    {
        if (state is TaskState.Submitted or TaskState.Working)
        {
            return new A2AContinuationToken(taskId);
        }

        return null;
    }

    private AgentResponse ConvertToAgentResponse(Message message)
    {
        return new AgentResponse
        {
            AgentId = this.Id,
            ResponseId = message.MessageId,
            FinishReason = ChatFinishReason.Stop,
            RawRepresentation = message,
            Messages = [message.ToChatMessage()],
            AdditionalProperties = message.Metadata?.ToAdditionalProperties(),
        };
    }

    private AgentResponse ConvertToAgentResponse(AgentTask task)
    {
        return new AgentResponse
        {
            AgentId = this.Id,
            ResponseId = task.Id,
            FinishReason = MapTaskStateToFinishReason(task.Status.State),
            RawRepresentation = task,
            Messages = task.ToChatMessages() ?? [],
            ContinuationToken = CreateContinuationToken(task.Id, task.Status.State),
            AdditionalProperties = task.Metadata?.ToAdditionalProperties(),
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(Message message)
    {
        return new AgentResponseUpdate
        {
            AgentId = this.Id,
            ResponseId = message.MessageId,
            FinishReason = ChatFinishReason.Stop,
            RawRepresentation = message,
            Role = ChatRole.Assistant,
            MessageId = message.MessageId,
            Contents = message.Parts.ConvertAll(part => part.ToAIContent()),
            AdditionalProperties = message.Metadata?.ToAdditionalProperties(),
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(AgentTask task)
    {
        return new AgentResponseUpdate
        {
            AgentId = this.Id,
            ResponseId = task.Id,
            FinishReason = MapTaskStateToFinishReason(task.Status.State),
            RawRepresentation = task,
            Role = ChatRole.Assistant,
            Contents = task.ToAIContents(),
            ContinuationToken = CreateContinuationToken(task.Id, task.Status.State),
            AdditionalProperties = task.Metadata?.ToAdditionalProperties(),
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(TaskStatusUpdateEvent statusUpdateEvent)
    {
        return new AgentResponseUpdate
        {
            AgentId = this.Id,
            ResponseId = statusUpdateEvent.TaskId,
            RawRepresentation = statusUpdateEvent,
            Role = ChatRole.Assistant,
            FinishReason = MapTaskStateToFinishReason(statusUpdateEvent.Status.State),
            AdditionalProperties = statusUpdateEvent.Metadata?.ToAdditionalProperties() ?? [],
        };
    }

    private AgentResponseUpdate ConvertToAgentResponseUpdate(TaskArtifactUpdateEvent artifactUpdateEvent)
    {
        return new AgentResponseUpdate
        {
            AgentId = this.Id,
            ResponseId = artifactUpdateEvent.TaskId,
            RawRepresentation = artifactUpdateEvent,
            Role = ChatRole.Assistant,
            Contents = artifactUpdateEvent.Artifact.ToAIContents(),
            AdditionalProperties = artifactUpdateEvent.Metadata?.ToAdditionalProperties() ?? [],
        };
    }

    private static ChatFinishReason? MapTaskStateToFinishReason(TaskState state)
    {
        return state == TaskState.Completed ? ChatFinishReason.Stop : null;
    }
}
