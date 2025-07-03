// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Microsoft.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.AzureAIAgentsPersistent;

/// <summary>
/// Represents a Foundry agent that interacts with the persistent agents service to manage and execute tasks.
/// </summary>
public class FoundryAgent : Agent
{
    private readonly PersistentAgentsClient _persistentAgentsClient;
    private readonly PersistentAgent _persistentAgent;
    private string? _agentId;
    private ChatClientAgent? _chatClientAgent;

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgent"/> class with an existing agent.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> used to interact with the persistent agents service.</param>
    /// <param name="persistentAgent">The <see cref="PersistentAgent"/> containing metadata describing the existing agent.</param>
    public FoundryAgent(PersistentAgentsClient persistentAgentsClient, PersistentAgent persistentAgent)
    {
        this._persistentAgentsClient = persistentAgentsClient;
        this._persistentAgent = persistentAgent;
        this._agentId = persistentAgent.Id;
        this._chatClientAgent = persistentAgentsClient.GetChatClientAgent(
            persistentAgent.Id,
            null,
            persistentAgent.Name,
            persistentAgent.Description,
            persistentAgent.Instructions);
    }

    /// <summary>
    /// Gets the <see cref="PersistentAgentsClient"/> used by this agent.
    /// </summary>
    public PersistentAgentsClient PersistentAgentsClient => this._persistentAgentsClient;

    /// <inheritdoc/>
    public override string Id => this._agentId ?? string.Empty;

    /// <summary>
    /// Creates a new instance of <see cref="FoundryAgent"/> with a new server side agent asynchronously using the specified client and creation
    /// options.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> used to interact with the persistent agents service.</param>
    /// <param name="createOptions">The options specifying the configuration and metadata for the agent to be created.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests. Defaults to <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the created <see cref="FoundryAgent"/>.</returns>
    public static async Task<FoundryAgent> CreateAsync(
        PersistentAgentsClient persistentAgentsClient,
        FoundryAgentCreateOptions createOptions,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(persistentAgentsClient);
        Throw.IfNull(createOptions);

        var persistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
                createOptions.Model,
                createOptions.Name,
                createOptions.Description,
                createOptions.Instructions,
                createOptions.Tools,
                createOptions.ToolResources,
                createOptions.Temperature,
                createOptions.TopP,
                createOptions.ResponseFormat,
                createOptions.Metadata,
                cancellationToken).ConfigureAwait(false);

        return new FoundryAgent(persistentAgentsClient, persistentAgentResponse.Value);
    }

    /// <summary>
    /// Retrieves an existing <see cref="FoundryAgent"/> instance by its agent ID asynchronously using the specified client.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> used to interact with the persistent agents service.</param>
    /// <param name="agentId">The ID of the agent to retrieve.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests. Defaults to <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains the retrieved <see cref="FoundryAgent"/>.</returns>
    public static async Task<FoundryAgent> GetAsync(
        PersistentAgentsClient persistentAgentsClient,
        string agentId,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(persistentAgentsClient);
        Throw.IfNullOrWhitespace(agentId);

        var persistentAgent = await persistentAgentsClient.Administration.GetAgentAsync(agentId, cancellationToken).ConfigureAwait(false);
        return new FoundryAgent(persistentAgentsClient, persistentAgent);
    }

    /// <inheritdoc/>
    public override AgentThread GetNewThread()
    {
        if (this._chatClientAgent == null)
        {
            throw new InvalidOperationException("The agent has been deleted.");
        }

        return this._chatClientAgent.GetNewThread();
    }

    /// <summary>
    /// Deletes the agent if it exists, otherwise does nothing.
    /// </summary>
    /// <returns>A task that represents the asynchronous operation.</returns>
    public async Task EnsureAgentDeletedAsync()
    {
        if (this._agentId != null)
        {
            await this._persistentAgentsClient.Administration.DeleteAgentAsync(this._agentId, CancellationToken.None).ConfigureAwait(false);
            this._chatClientAgent = null;
            this._agentId = null;
        }
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public async Task<ChatResponse> RunAsync(string message, AgentThread? thread = null, ThreadAndRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        if (this._chatClientAgent == null)
        {
            throw new InvalidOperationException("The agent has been deleted.");
        }

        return await this._chatClientAgent.RunAsync(message, thread, chatOptions: new() { RawRepresentationFactory = _ => options }, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> RunAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        if (this._chatClientAgent == null)
        {
            throw new InvalidOperationException("The agent has been deleted.");
        }

        return await this._chatClientAgent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="message">The message to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    public async IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(string message, AgentThread? thread = null, ThreadAndRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (this._chatClientAgent == null)
        {
            throw new InvalidOperationException("The agent has been deleted.");
        }

        await foreach (var update in this._chatClientAgent.RunStreamingAsync(message, thread, chatOptions: new() { RawRepresentationFactory = _ => options }, cancellationToken: cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (this._chatClientAgent == null)
        {
            throw new InvalidOperationException("The agent has been deleted.");
        }

        await foreach (var update in this._chatClientAgent.RunStreamingAsync(messages, thread, options, cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }
}
