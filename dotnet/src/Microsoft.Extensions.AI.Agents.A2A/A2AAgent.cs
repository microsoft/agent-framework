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
    private readonly bool? _awaitRunCompletion;

    /// <summary>
    /// Initializes a new instance of the <see cref="A2AAgent"/> class.
    /// </summary>
    /// <param name="a2aClient">The A2A client to use for interacting with A2A agents.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The the name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="displayName">The display name of the agent.</param>
    /// <param name="awaitRunCompletion">Specifies whether the agent should await task completions or not.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public A2AAgent(A2AClient a2aClient, string? id = null, string? name = null, string? description = null, string? displayName = null, bool? awaitRunCompletion = null, ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(a2aClient);

        this._a2aClient = a2aClient;
        this._id = id;
        this._name = name;
        this._description = description;
        this._displayName = displayName;
        this._awaitRunCompletion = awaitRunCompletion;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<A2AAgent>();
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        ValidateInputMessages(messages);

        var a2aMessage = messages.ToA2AMessage();

        // Linking the message to the existing conversation, if any.
        a2aMessage.ContextId = thread?.ConversationId;

        this._logger.LogA2AAgentInvokingAgent(nameof(RunAsync), this.Id, this.Name);

        A2AResponse? a2aResponse;

        // The response id, provided by a caller, indicates that the caller is interested in the status/result of the task.
        if (options is { ResponseId: { } taskId })
        {
            a2aResponse = await this._a2aClient.GetTaskAsync(taskId, cancellationToken).ConfigureAwait(false);
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
            // Await the task's completion if requested. This enables scenarios where a caller sends a message or requests a task by the task id,
            // obtains a task, and then asks the agent to wait for its completion rather than waiting themselves (via polling).
            if (this.ShouldAwaitTaskCompletions(options))
            {
                // Do polling
                while (task.Status.State is TaskState.Submitted or TaskState.Working)
                {
                    //TBD: Use polling settings
                    await Task.Delay(1000, cancellationToken).ConfigureAwait(false);
                    task = await this._a2aClient.GetTaskAsync(task.Id, cancellationToken).ConfigureAwait(false);
                }
            }

            UpdateThreadConversationId(thread, task.ContextId);

            return this.ConvertToAgentResponse(task, options);
        }

        throw new NotSupportedException($"Only message and task responses are supported from A2A agents. Received: {a2aResponse.GetType().FullName ?? "null"}");
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
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

                foreach (var update in this.ConvertToAgentResponse(task, options).ToAgentRunResponseUpdates())
                {
                    yield return update;

                    // If the task's completion awaiting is not requested, return the first update
                    // from the original response so the caller will receive the task id and status.
                    if (!this.ShouldAwaitTaskCompletions(options) && options?.ResponseId is null)
                    {
                        yield break;
                    }
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

        // Setting AwaitLongRunCompletion to false here only to get the `Status` property set in the response.
        return this.ConvertToAgentResponse(agentTask, new AgentRunOptions() { AwaitLongRunCompletion = false });
    }

    /// <inheritdoc/>
    public override string Id => this._id ?? base.Id;

    /// <inheritdoc/>
    public override string? Name => this._name ?? base.Name;

    /// <inheritdoc/>
    public override string DisplayName => this._displayName ?? base.DisplayName;

    /// <inheritdoc/>
    public override string? Description => this._description ?? base.Description;

    private static void ValidateInputMessages(IReadOnlyCollection<ChatMessage> messages)
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

    private AgentRunResponse ConvertToAgentResponse(AgentTask task, AgentRunOptions? options)
    {
        AgentRunResponse response = new()
        {
            AgentId = this.Id,
            ResponseId = task.Id,
            RawRepresentation = task,
            Messages = task.History?.ToChatMessages(this.Name, task.Artifacts) ?? [],
            Status = this.ToResponseStatus(task.Status, options),
            AdditionalProperties = task.Metadata.ToAdditionalProperties() ?? [],
        };

        response.AdditionalProperties["Status.Timestamp"] = task.Status.Timestamp;

        if (task.Status.Message is { } statusMessage)
        {
            response.AdditionalProperties["Status.Message"] = statusMessage.ToChatMessage();
        }

        return response;
    }

    private NewResponseStatus? ToResponseStatus(AgentTaskStatus status, AgentRunOptions? options)
    {
        if (this.ShouldAwaitTaskCompletions(options))
        {
            return null;
        }

        return status.ToResponseStatus();
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
            if (statusUpdateEvent is { Status: { } status })
            {
                responseUpdate.Status = this.ToResponseStatus(status, options);

                responseUpdate.AdditionalProperties["Status.Timestamp"] = status.Timestamp;

                if (status.Message is { } statusMessage)
                {
                    responseUpdate.AdditionalProperties["Status.Message"] = statusMessage.ToChatMessage();
                }
            }

            responseUpdate.AdditionalProperties[nameof(TaskStatusUpdateEvent.Final)] = statusUpdateEvent.Final;

            return responseUpdate;
        }

        if (taskUpdateEvent is TaskArtifactUpdateEvent artifactUpdateEvent)
        {
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

    /// <summary>Determines whether to await task completions or not.</summary>
    private bool ShouldAwaitTaskCompletions(AgentRunOptions? options)
    {
        // If specified in options, use that.
        if (options is { AwaitLongRunCompletion: { } awaitRunCompletion })
        {
            return awaitRunCompletion;
        }

        // Otherwise, use the value specified at initialization
        return this._awaitRunCompletion ?? true;
    }
}
