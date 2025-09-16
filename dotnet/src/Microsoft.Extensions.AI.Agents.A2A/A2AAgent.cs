// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Represents an <see cref="AIAgent"/> that can interact with remote agents that are exposed via the A2A protocol
/// </summary>
/// <remarks>
/// This agent supports only messages as a response from A2A agents.
/// Support for tasks will be added later as part of the long-running
/// executions work.
/// </remarks>
internal sealed class A2AAgent : AIAgent
{
    private readonly A2AClient _a2aClient;
    private readonly string? _id;
    private readonly string? _name;
    private readonly string? _description;
    private readonly string? _displayName;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="A2AAgent"/> class.
    /// </summary>
    /// <param name="a2aClient">The A2A client to use for interacting with A2A agents.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The the name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="displayName">The display name of the agent.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public A2AAgent(A2AClient a2aClient, string? id = null, string? name = null, string? description = null, string? displayName = null, ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(a2aClient);

        this._a2aClient = a2aClient;
        this._id = id;
        this._name = name;
        this._description = description;
        this._displayName = displayName;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<A2AAgent>();
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        ValidateInputMessages(messages);

        var a2aMessage = messages.ToA2AMessage();

        // Linking the message to the existing conversation, if any.
        a2aMessage.ContextId = thread?.ConversationId;

        this._logger.LogA2AAgentInvokingAgent(nameof(RunAsync), this.Id, this.Name);

        A2AResponse? a2aResponse;

        // The continuation token, provided by a caller, indicates that the caller is interested in the status/result of the task.
        if (options is { ContinuationToken: { } token } && LongRunContinuationToken.FromToken(token) is { } longRunToken)
        {
            a2aResponse = await this._a2aClient.GetTaskAsync(longRunToken.TaskId, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            a2aResponse = await this._a2aClient.SendMessageAsync(new MessageSendParams { Message = a2aMessage }, cancellationToken).ConfigureAwait(false);
        }

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, this.Name);

        if (a2aResponse is Message message)
        {
            UpdateThreadConversationId(thread, message.ContextId);

            return this.ConvertToAgentResponse(message);
        }

        if (a2aResponse is AgentTask task)
        {
            UpdateThreadConversationId(thread, task.ContextId);

            return this.ConvertToAgentResponse(task);
        }

        throw new NotSupportedException($"Only message and task responses are supported from A2A agents. Received: {a2aResponse.GetType().FullName ?? "null"}");
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ValidateInputMessages(messages);

        var a2aMessage = messages.ToA2AMessage();

        // Linking the message to the existing conversation, if any.
        a2aMessage.ContextId = thread?.ConversationId;

        this._logger.LogA2AAgentInvokingAgent(nameof(RunStreamingAsync), this.Id, this.Name);

        var a2aSseEvents = this._a2aClient.SendMessageStreamAsync(new MessageSendParams { Message = a2aMessage }, cancellationToken).ConfigureAwait(false);

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunStreamingAsync), this.Id, this.Name);

        string? contextId = null;

        await foreach (var sseEvent in a2aSseEvents)
        {
            if (sseEvent.Data is Message message)
            {
                contextId = message.ContextId;

                foreach (var update in this.ConvertToAgentResponse(message).ToAgentRunResponseUpdates())
                {
                    yield return update;
                }
            }
            else if (sseEvent.Data is AgentTask task)
            {
                contextId = task.ContextId;

                foreach (var update in this.ConvertToAgentResponse(task).ToAgentRunResponseUpdates())
                {
                    yield return update;
                }
            }
            else if (sseEvent.Data is TaskUpdateEvent taskUpdateEvent)
            {
                contextId = taskUpdateEvent.ContextId;

                yield return this.ConvertToAgentResponseUpdate(taskUpdateEvent, options);
            }
            else
            {
                throw new NotSupportedException($"Only message, task, task update events are supported from A2A agents. Received: {sseEvent.Data.GetType().FullName ?? "null"}");
            }
        }

        UpdateThreadConversationId(thread, contextId);
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse?> CancelRunAsync(string id, AgentCancelRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(id);

        var agentTask = await this._a2aClient.CancelTaskAsync(new TaskIdParams { Id = id }, cancellationToken).ConfigureAwait(false);

        return this.ConvertToAgentResponse(agentTask, throwIfOperationCancelled: false);
    }

    /// <inheritdoc/>
    public override string Id => this._id ?? base.Id;

    /// <inheritdoc/>
    public override string? Name => this._name ?? base.Name;

    /// <inheritdoc/>
    public override string DisplayName => this._displayName ?? base.DisplayName;

    /// <inheritdoc/>
    public override string? Description => this._description ?? base.Description;

    private static void ValidateInputMessages(IEnumerable<ChatMessage> messages)
    {
        _ = Throw.IfNull(messages);

        foreach (var message in messages)
        {
            if (message.Role != ChatRole.User)
            {
                throw new ArgumentException($"All input messages for A2A agents must have the role '{ChatRole.User}'. Found '{message.Role}'.", nameof(messages));
            }
        }
    }

    private static void UpdateThreadConversationId(AgentThread? thread, string? contextId)
    {
        if (thread is null)
        {
            return;
        }

        // Surface cases where the A2A agent responds with a message or a task that
        // has a different context Id than the thread's conversation Id.
        if (thread.ConversationId is not null && contextId is not null && thread.ConversationId != contextId)
        {
            throw new InvalidOperationException(
                $"The {nameof(contextId)} returned from the A2A agent is different from the conversation Id of the provided {nameof(AgentThread)}.");
        }

        // Assign a server-generated context Id to the thread if it's not already set.
        thread.ConversationId ??= contextId;
    }

    private AgentRunResponse ConvertToAgentResponse(AgentTask task, bool throwIfOperationCancelled = true)
    {
        AgentRunResponse response = new()
        {
            AgentId = this.Id,
            ResponseId = task.Id,
            RawRepresentation = task,
            Messages = task.History?.ToChatMessages(this.Name, task.Artifacts) ?? [],
            ContinuationToken = GetContinuationToken(task.Id, task.Status.State, throwIfOperationCancelled),
            AdditionalProperties = task.Metadata.ToAdditionalProperties() ?? [],
        };

        response.AdditionalProperties["Status.Timestamp"] = task.Status.Timestamp;

        if (task.Status.Message is { } statusMessage)
        {
            response.AdditionalProperties["Status.Message"] = statusMessage.ToChatMessage();
        }

        return response;
    }

    private AgentRunResponse ConvertToAgentResponse(Message message)
    {
        AgentRunResponse response = new()
        {
            AgentId = this.Id,
            ResponseId = message.MessageId,
            RawRepresentation = message,
            Messages = [message.ToChatMessage(this.Name)],
            AdditionalProperties = message.Metadata.ToAdditionalProperties() ?? [],
        };

        if (message.ReferenceTaskIds is { } referenceTaskIds)
        {
            response.AdditionalProperties[nameof(Message.ReferenceTaskIds)] = referenceTaskIds;
        }

        if (message.TaskId is { } taskId)
        {
            response.AdditionalProperties[nameof(Message.TaskId)] = taskId;
        }

        if (message.Extensions is { } extensions)
        {
            response.AdditionalProperties[nameof(Message.Extensions)] = extensions;
        }

        return response;
    }

    private AgentRunResponseUpdate ConvertToAgentResponseUpdate(TaskUpdateEvent taskUpdateEvent, AgentRunOptions? options)
    {
        AgentRunResponseUpdate responseUpdate = new()
        {
            AgentId = this.Id,
            ResponseId = taskUpdateEvent.TaskId,
            RawRepresentation = taskUpdateEvent,
            Role = ChatRole.Assistant,
            AdditionalProperties = taskUpdateEvent.Metadata.ToAdditionalProperties() ?? [],
        };

        if (taskUpdateEvent is TaskStatusUpdateEvent statusUpdateEvent)
        {
            responseUpdate.ContinuationToken = GetContinuationToken(statusUpdateEvent.TaskId, statusUpdateEvent.Status.State);
            responseUpdate.AdditionalProperties[nameof(TaskStatusUpdateEvent.Status)] = statusUpdateEvent.Status;
            responseUpdate.AdditionalProperties[nameof(TaskStatusUpdateEvent.Final)] = statusUpdateEvent.Final;
            return responseUpdate;
        }

        if (taskUpdateEvent is TaskArtifactUpdateEvent artifactUpdateEvent)
        {
            responseUpdate.ContinuationToken = GetContinuationToken(artifactUpdateEvent.TaskId, TaskState.Working);
            responseUpdate.Contents = artifactUpdateEvent.Artifact.ToAIContents();

            if (artifactUpdateEvent.Append is { } append)
            {
                responseUpdate.AdditionalProperties[nameof(TaskArtifactUpdateEvent.Append)] = append;
            }

            if (artifactUpdateEvent.LastChunk is { } lastChunk)
            {
                responseUpdate.AdditionalProperties[nameof(TaskArtifactUpdateEvent.LastChunk)] = lastChunk;
            }

            return responseUpdate;
        }

        return responseUpdate;
    }

    private static LongRunContinuationToken? GetContinuationToken(string taskId, TaskState state, bool? throwIfOperationCancelled = true)
    {
        if (state == TaskState.Failed)
        {
            throw new InvalidOperationException("The task execution failed.");
        }

        if (state == TaskState.Canceled && throwIfOperationCancelled is true)
        {
            throw new TaskCanceledException("The task execution is canceled.");
        }

        if (state == TaskState.Rejected)
        {
            throw new TaskCanceledException("The task is rejected.");
        }

        if (state != TaskState.Completed)
        {
            return new LongRunContinuationToken(taskId);
        }

        return null;
    }
}
