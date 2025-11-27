// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.ServerSentEvents;
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
    public sealed override AgentThread GetNewThread()
        => new A2AAgentThread();

    /// <summary>
    /// Get a new <see cref="AgentThread"/> instance using an existing context id, to continue that conversation.
    /// </summary>
    /// <param name="contextId">The context id to continue.</param>
    /// <returns>A new <see cref="AgentThread"/> instance.</returns>
    public AgentThread GetNewThread(string contextId)
        => new A2AAgentThread() { ContextId = contextId };

    /// <inheritdoc/>
    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => new A2AAgentThread(serializedThread, jsonSerializerOptions);

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        A2AAgentThread typedThread = this.GetA2AThread(thread, options);

        this._logger.LogA2AAgentInvokingAgent(nameof(RunAsync), this.Id, this.Name);

        A2AResponse? a2aResponse = null;

        if (GetContinuationToken(messages, options) is { } token)
        {
            a2aResponse = await this._a2aClient.GetTaskAsync(token.TaskId, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            var a2aMessage = CreateA2AMessage(typedThread, messages);

            a2aResponse = await this._a2aClient.SendMessageAsync(new MessageSendParams { Message = a2aMessage }, cancellationToken).ConfigureAwait(false);
        }

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, this.Name);

        if (a2aResponse is AgentMessage message)
        {
            UpdateThread(typedThread, message.ContextId);

            return new AgentRunResponse
            {
                AgentId = this.Id,
                ResponseId = message.MessageId,
                RawRepresentation = message,
                Messages = [message.ToChatMessage()],
                AdditionalProperties = message.Metadata?.ToAdditionalProperties(),
            };
        }

        if (a2aResponse is AgentTask agentTask)
        {
            UpdateThread(typedThread, agentTask.ContextId, agentTask.Id);

            var response = new AgentRunResponse
            {
                AgentId = this.Id,
                ResponseId = agentTask.Id,
                RawRepresentation = agentTask,
                Messages = agentTask.ToChatMessages() ?? [],
                ContinuationToken = CreateContinuationToken(agentTask.Id, agentTask.Status.State),
                AdditionalProperties = agentTask.Metadata?.ToAdditionalProperties(),
            };

            if (agentTask.ToChatMessages() is { Count: > 0 } taskMessages)
            {
                response.Messages = taskMessages;
            }

            return response;
        }

        throw new NotSupportedException($"Only Message and AgentTask responses are supported from A2A agents. Received: {a2aResponse.GetType().FullName ?? "null"}");
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        A2AAgentThread typedThread = this.GetA2AThread(thread, options);

        this._logger.LogA2AAgentInvokingAgent(nameof(RunStreamingAsync), this.Id, this.Name);

        ConfiguredCancelableAsyncEnumerable<SseItem<A2AEvent>> a2aSseEvents;

        if (options?.ContinuationToken is not null)
        {
            // Task stream resumption is not well defined in the A2A v2.* specification, leaving it to the agent implementations.  
            // The v3.0 specification improves this by defining task stream reconnection that allows obtaining the same stream  
            // from the beginning, but it does not define stream resumption from a specific point in the stream.  
            // Therefore, the code should be updated once the A2A .NET library supports the A2A v3.0 specification,  
            // and AF has the necessary model to allow consumers to know whether they need to resume the stream and add new updates to  
            // the existing ones or reconnect the stream and obtain all updates again.  
            // For more details, see the following issue: https://github.com/microsoft/agent-framework/issues/1764  
            throw new InvalidOperationException("Reconnecting to task streams using continuation tokens is not supported yet.");
            // a2aSseEvents = this._a2aClient.SubscribeToTaskAsync(token.TaskId, cancellationToken).ConfigureAwait(false);  
        }

        var a2aMessage = CreateA2AMessage(typedThread, messages);

        a2aSseEvents = this._a2aClient.SendMessageStreamingAsync(new MessageSendParams { Message = a2aMessage }, cancellationToken).ConfigureAwait(false);

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunStreamingAsync), this.Id, this.Name);

        string? contextId = null;
        string? taskId = null;

        await foreach (var sseEvent in a2aSseEvents)
        {
            if (sseEvent.Data is AgentMessage message)
            {
                contextId = message.ContextId;

                yield return this.ConvertToAgentResponseUpdate(message);
            }
            else if (sseEvent.Data is AgentTask task)
            {
                contextId = task.ContextId;
                taskId = task.Id;

                yield return this.ConvertToAgentResponseUpdate(task);
            }
            else if (sseEvent.Data is TaskUpdateEvent taskUpdateEvent)
            {
                contextId = taskUpdateEvent.ContextId;
                taskId = taskUpdateEvent.TaskId;

                yield return this.ConvertToAgentResponseUpdate(taskUpdateEvent);
            }
            else
            {
                throw new NotSupportedException($"Only message, task, task update events are supported from A2A agents. Received: {sseEvent.Data.GetType().FullName ?? "null"}");
            }
        }

        UpdateThread(typedThread, contextId, taskId);
    }

    /// <inheritdoc/>
    public override string Id => this._id ?? base.Id;

    /// <inheritdoc/>
    public override string? Name => this._name ?? base.Name;

    /// <inheritdoc/>
    public override string DisplayName => this._displayName ?? base.DisplayName;

    /// <inheritdoc/>
    public override string? Description => this._description ?? base.Description;

    private A2AAgentThread GetA2AThread(AgentThread? thread, AgentRunOptions? options)
    {
        // Aligning with other agent implementations that support background responses, where
        // a thread is required for background responses to prevent inconsistent experience
        // for callers if they forget to provide the thread for initial or follow-up runs.
        if (options?.AllowBackgroundResponses is true && thread is null)
        {
            throw new InvalidOperationException("A thread must be provided when AllowBackgroundResponses is enabled.");
        }

        thread ??= this.GetNewThread();

        if (thread is not A2AAgentThread typedThread)
        {
            throw new InvalidOperationException($"The provided thread type {thread.GetType()} is not compatible with the agent. Only A2A agent created threads are supported.");
        }

        return typedThread;
    }

    private static void UpdateThread(A2AAgentThread? thread, string? contextId, string? taskId = null)
    {
        if (thread is null)
        {
            return;
        }

        // Surface cases where the A2A agent responds with a response that
        // has a different context Id than the thread's conversation Id.
        if (thread.ContextId is not null && contextId is not null && thread.ContextId != contextId)
        {
            throw new InvalidOperationException(
                $"The {nameof(contextId)} returned from the A2A agent is different from the conversation Id of the provided {nameof(AgentThread)}.");
        }

        // Assign a server-generated context Id to the thread if it's not already set.
        thread.ContextId ??= contextId;
        thread.TaskId = taskId;
    }

    private static AgentMessage CreateA2AMessage(A2AAgentThread typedThread, IEnumerable<ChatMessage> messages)
    {
        var a2aMessage = messages.ToA2AMessage();

        // Linking the message to the existing conversation, if any.
        // See: https://github.com/a2aproject/A2A/blob/main/docs/topics/life-of-a-task.md#group-related-interactions
        a2aMessage.ContextId = typedThread.ContextId;

        // Link the message as a follow-up to an existing task, if any.
        // See: https://github.com/a2aproject/A2A/blob/main/docs/topics/life-of-a-task.md#task-refinements
        a2aMessage.ReferenceTaskIds = typedThread.TaskId is null ? null : [typedThread.TaskId];

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
        if (state == TaskState.Submitted || state == TaskState.Working)
        {
            return new A2AContinuationToken(taskId);
        }

        return null;
    }

    private AgentRunResponseUpdate ConvertToAgentResponseUpdate(AgentMessage message)
    {
        return new AgentRunResponseUpdate
        {
            AgentId = this.Id,
            ResponseId = message.MessageId,
            RawRepresentation = message,
            Role = ChatRole.Assistant,
            MessageId = message.MessageId,
            Contents = message.Parts.ConvertAll(part => part.ToAIContent()),
            AdditionalProperties = message.Metadata?.ToAdditionalProperties(),
        };
    }

    private AgentRunResponseUpdate ConvertToAgentResponseUpdate(AgentTask task)
    {
        return new AgentRunResponseUpdate
        {
            AgentId = this.Id,
            ResponseId = task.Id,
            RawRepresentation = task,
            Role = ChatRole.Assistant,
            Contents = task.ToAIContents(),
            AdditionalProperties = task.Metadata?.ToAdditionalProperties(),
        };
    }

    private AgentRunResponseUpdate ConvertToAgentResponseUpdate(TaskUpdateEvent taskUpdateEvent)
    {
        AgentRunResponseUpdate responseUpdate = new()
        {
            AgentId = this.Id,
            ResponseId = taskUpdateEvent.TaskId,
            RawRepresentation = taskUpdateEvent,
            Role = ChatRole.Assistant,
            AdditionalProperties = taskUpdateEvent.Metadata?.ToAdditionalProperties() ?? [],
        };

        if (taskUpdateEvent is TaskArtifactUpdateEvent artifactUpdateEvent)
        {
            responseUpdate.Contents = artifactUpdateEvent.Artifact.ToAIContents();
            responseUpdate.RawRepresentation = artifactUpdateEvent;
        }

        return responseUpdate;
    }
}
