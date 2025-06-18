// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Agents.Core.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.CopilotStudio;

/// <summary>
/// Represents a Copilot Studio agent in the cloud.
/// </summary>
public class CopilotStudioAgent : Agent
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
    public override async Task<ChatResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        if (messages is not { Count: > 0 })
        {
            return new([new ChatMessage(ChatRole.Assistant, string.Empty)]);
        }

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

        // Enumerate the response messages
        var responseMessagesList = new List<ChatMessage>();
        await foreach (ChatMessage message in responseMessages.ConfigureAwait(false))
        {
            // Add the message to the list
            responseMessagesList.Add(message);
        }

        return new ChatResponse(responseMessagesList);
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (messages is not { Count: > 0 })
        {
            yield return new(ChatRole.Assistant, string.Empty);
            yield break;
        }

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
            yield return new ChatResponseUpdate(message.Role, message.Contents);
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

        return conversationId;
    }
}
