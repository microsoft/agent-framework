// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
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
    public override AgentThread GetNewThread()
    {
        return new CopilotStudioAgentThread();
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        // Ensure that we have a valid thread to work with.
        CopilotStudioAgentThread copilotStudioAgentThread = base.ValidateOrCreateThreadType(thread, () => new CopilotStudioAgentThread());
        if (copilotStudioAgentThread.Id is null)
        {
            // If the thread ID is null, we need to start a new conversation and set the thread ID accordingly.
            copilotStudioAgentThread.Id = await this.StartNewConversationAsync(cancellationToken).ConfigureAwait(false);
        }

        // Invoke the Copilot Studio agent with the provided messages.
        string question = string.Join("\n", messages.Select(m => m.Text));
        var responseMessages = ActivityProcessor.ProcessActivityAsync(this.Client.AskQuestionAsync(question, copilotStudioAgentThread.Id, cancellationToken), streaming: false, this._logger);
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
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        // Ensure that we have a valid thread to work with.
        CopilotStudioAgentThread copilotStudioAgentThread = base.ValidateOrCreateThreadType(thread, () => new CopilotStudioAgentThread());
        if (copilotStudioAgentThread.Id is null)
        {
            // If the thread ID is null, we need to start a new conversation and set the thread ID accordingly.
            copilotStudioAgentThread.Id = await this.StartNewConversationAsync(cancellationToken).ConfigureAwait(false);
        }

        // Invoke the Copilot Studio agent with the provided messages.
        string question = string.Join("\n", messages.Select(m => m.Text));
        var responseMessages = ActivityProcessor.ProcessActivityAsync(this.Client.AskQuestionAsync(question, copilotStudioAgentThread.Id, cancellationToken), streaming: true, this._logger);

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
            throw new System.InvalidOperationException("Failed to start a new conversation.");
        }

        return conversationId!;
    }
}
