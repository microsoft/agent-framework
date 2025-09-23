// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
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
    public override sealed AgentThread GetNewThread()
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
        ValidateInputMessages(messages);

        var a2aMessage = messages.ToA2AMessage();

        thread ??= this.GetNewThread();
        if (thread is not A2AAgentThread typedThread)
        {
            throw new InvalidOperationException("The provided thread is not compatible with the agent. Only threads created by the agent can be used.");
        }

        // Linking the message to the existing conversation, if any.
        a2aMessage.ContextId = typedThread.ContextId;

        this._logger.LogA2AAgentInvokingAgent(nameof(RunAsync), this.Id, this.Name);

        var a2aResponse = await this._a2aClient.SendMessageAsync(new MessageSendParams { Message = a2aMessage }, cancellationToken).ConfigureAwait(false);

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, this.Name);

        if (a2aResponse is Message message)
        {
            UpdateThreadConversationId(typedThread, message.ContextId);

            return new AgentRunResponse
            {
                AgentId = this.Id,
                ResponseId = message.MessageId,
                RawRepresentation = message,
                Messages = [message.ToChatMessage()],
                AdditionalProperties = message.Metadata.ToAdditionalProperties(),
            };
        }
        if (a2aResponse is AgentTask agentTask)
        {
            UpdateThreadConversationId(typedThread, agentTask.ContextId);

            return new AgentRunResponse
            {
                AgentId = this.Id,
                ResponseId = agentTask.Id,
                RawRepresentation = agentTask,
                Messages = agentTask.ToChatMessages(),
                AdditionalProperties = agentTask.Metadata.ToAdditionalProperties(),
            };
        }

        throw new NotSupportedException($"Only Message and AgentTask responses are supported from A2A agents. Received: {a2aResponse.GetType().FullName ?? "null"}");
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ValidateInputMessages(messages);

        var a2aMessage = messages.ToA2AMessage();

        thread ??= this.GetNewThread();
        if (thread is not A2AAgentThread typedThread)
        {
            throw new InvalidOperationException("The provided thread is not compatible with the agent. Only threads created by the agent can be used.");
        }

        // Linking the message to the existing conversation, if any.
        a2aMessage.ContextId = typedThread.ContextId;

        this._logger.LogA2AAgentInvokingAgent(nameof(RunStreamingAsync), this.Id, this.Name);

        var a2aSseEvents = this._a2aClient.SendMessageStreamAsync(new MessageSendParams { Message = a2aMessage }, cancellationToken).ConfigureAwait(false);

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunStreamingAsync), this.Id, this.Name);

        await foreach (var sseEvent in a2aSseEvents)
        {
            if (sseEvent.Data is not Message message)
            {
                throw new NotSupportedException($"Only message responses are supported from A2A agents. Received: {sseEvent.Data?.GetType().FullName ?? "null"}");
            }

            UpdateThreadConversationId(typedThread, message.ContextId);

            yield return new AgentRunResponseUpdate
            {
                AgentId = this.Id,
                ResponseId = message.MessageId,
                RawRepresentation = message,
                Role = ChatRole.Assistant,
                MessageId = message.MessageId,
                Contents = [.. message.Parts.Select(part => part.ToAIContent())],
                AdditionalProperties = message.Metadata.ToAdditionalProperties(),
            };
        }
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

    private static void UpdateThreadConversationId(A2AAgentThread? thread, string? contextId)
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
    }
}
