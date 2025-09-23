// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Agents.Core.Models;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.CopilotStudio;

/// <summary>
/// Represents a Copilot Studio agent in the cloud.
/// </summary>
public class CopilotStudioAgent : AIAgent
{
    private readonly ILogger _logger;

    /// <summary>
    /// The client used to interact with the Copilot Agent service.
    /// </summary>
    public CopilotClient Client { get; }

    private static readonly AIAgentMetadata s_agentMetadata = new("copilot-studio");

    /// <summary>
    /// Initializes a new instance of the <see cref="CopilotStudioAgent"/> class.
    /// </summary>
    /// <param name="client">A client used to interact with the Copilot Agent service.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public CopilotStudioAgent(CopilotClient client, ILoggerFactory? loggerFactory = null)
    {
        this.Client = client;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<CopilotStudioAgent>();
    }

    /// <inheritdoc/>
    public override sealed AgentThread GetNewThread()
        => new CopilotStudioAgentThread();

    /// <summary>
    /// Get a new <see cref="AgentThread"/> instance using an existing conversation id, to continue that conversation.
    /// </summary>
    /// <param name="conversationId">The conversation id to continue.</param>
    /// <returns>A new <see cref="AgentThread"/> instance.</returns>
    public AgentThread GetNewThread(string conversationId)
        => new CopilotStudioAgentThread() { ConversationId = conversationId };

    /// <inheritdoc/>
    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => new CopilotStudioAgentThread(serializedThread, jsonSerializerOptions);

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        // Ensure that we have a valid thread to work with.
        // If the thread ID is null, we need to start a new conversation and set the thread ID accordingly.
        thread ??= this.GetNewThread();
        if (thread is not CopilotStudioAgentThread typedThread)
        {
            throw new InvalidOperationException("The provided thread is not compatible with the agent. Only threads created by the agent can be used.");
        }

        typedThread.ConversationId ??= await this.StartNewConversationAsync(cancellationToken).ConfigureAwait(false);

        // Invoke the Copilot Studio agent with the provided messages.
        string question = string.Join("\n", messages.Select(m => m.Text));
        var responseMessages = ActivityProcessor.ProcessActivityAsync(this.Client.AskQuestionAsync(question, typedThread.ConversationId, cancellationToken), streaming: false, this._logger);
        var responseMessagesList = new List<ChatMessage>();
        await foreach (var message in responseMessages.ConfigureAwait(false))
        {
            responseMessagesList.Add(message);
        }

        // TODO: Review list of ChatResponse properties to ensure we set all availble values.
        // Setting ResponseId and MessageId end up being particularly important for streaming consumers
        // so that they can tell things like response boundaries.
        return new AgentRunResponse(responseMessagesList)
        {
            AgentId = this.Id,
            ResponseId = responseMessagesList.LastOrDefault()?.MessageId,
        };
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        // Ensure that we have a valid thread to work with.
        // If the thread ID is null, we need to start a new conversation and set the thread ID accordingly.
        thread ??= this.GetNewThread();
        if (thread is not CopilotStudioAgentThread typedThread)
        {
            throw new InvalidOperationException("The provided thread is not compatible with the agent. Only threads created by the agent can be used.");
        }

        typedThread.ConversationId ??= await this.StartNewConversationAsync(cancellationToken).ConfigureAwait(false);

        // Invoke the Copilot Studio agent with the provided messages.
        string question = string.Join("\n", messages.Select(m => m.Text));
        var responseMessages = ActivityProcessor.ProcessActivityAsync(this.Client.AskQuestionAsync(question, typedThread.ConversationId, cancellationToken), streaming: true, this._logger);

        // Enumerate the response messages
        await foreach (ChatMessage message in responseMessages.ConfigureAwait(false))
        {
            // TODO: Review list of ChatResponse properties to ensure we set all availble values.
            // Setting ResponseId and MessageId end up being particularly important for streaming consumers
            // so that they can tell things like response boundaries.
            yield return new AgentRunResponseUpdate(message.Role, message.Contents)
            {
                AgentId = this.Id,
                AdditionalProperties = message.AdditionalProperties,
                AuthorName = message.AuthorName,
                RawRepresentation = message.RawRepresentation,
                ResponseId = message.MessageId,
                MessageId = message.MessageId,
            };
        }
    }

    private async Task<string> StartNewConversationAsync(CancellationToken cancellationToken)
    {
        string? conversationId = null;
        await foreach (IActivity activity in this.Client.StartConversationAsync(emitStartConversationEvent: true, cancellationToken).ConfigureAwait(false))
        {
            if (activity.Conversation is not null)
            {
                conversationId = activity.Conversation.Id;
            }
        }

        if (string.IsNullOrEmpty(conversationId))
        {
            throw new InvalidOperationException("Failed to start a new conversation.");
        }

        return conversationId!;
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
        => base.GetService(serviceType, serviceKey)
           ?? (serviceType == typeof(CopilotClient) ? this.Client
            : serviceType == typeof(AIAgentMetadata) ? s_agentMetadata
            : null);
}
