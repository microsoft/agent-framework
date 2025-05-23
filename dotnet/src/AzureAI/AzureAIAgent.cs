// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Microsoft.Extensions.AI;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;

namespace Microsoft.Agents.AzureAI;

/// <summary>
/// Provides a specialized <see cref="Agent"/> based on an Azure AI agent.
/// </summary>
public sealed partial class AzureAIAgent : Agent
{
    /// <summary>
    /// Provides tool definitions used when associating a file attachment to an input message.
    /// </summary>
    internal static class Tools
    {
        /// <summary>
        /// The code-interpreter tool.
        /// </summary>
        public static string CodeInterpreter = "code_interpreter";

        /// <summary>
        /// The file-search tool.
        /// </summary>
        public const string FileSearch = "file_search";
    }

    /// <summary>
    /// The metadata key that identifies code-interpreter content.
    /// </summary>
    public const string CodeInterpreterMetadataKey = "code";

    /// <summary>
    /// Gets the assistant definition.
    /// </summary>
    public PersistentAgent Definition { get; private init; }

    /// <summary>
    /// Gets the polling behavior for run processing.
    /// </summary>
    public RunPollingOptions PollingOptions { get; } = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="AzureAIAgent"/> class.
    /// </summary>
    /// <param name="model">The agent model definition.</param>
    /// <param name="client">An <see cref="PersistentAgentsClient"/> instance.</param>
    public AzureAIAgent(
        PersistentAgent model,
        PersistentAgentsClient client)
    {
        this.Client = client;
        this.Definition = model;
        this.Description = this.Definition.Description;
        this.Id = this.Definition.Id;
        this.Name = this.Definition.Name;
        this.Instructions = this.Definition.Instructions;
    }

    /// <summary>
    /// The associated client.
    /// </summary>
    public PersistentAgentsClient Client { get; }

    /// <inheritdoc/>
    public override IAsyncEnumerable<AgentResponseItem<ChatMessage>> InvokeAsync(
        ICollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return this.InvokeAsync(
            messages,
            thread,
            options is null ?
                null :
                options is AzureAIAgentInvokeOptions azureAIAgentInvokeOptions ? azureAIAgentInvokeOptions : new AzureAIAgentInvokeOptions(options),
            cancellationToken);
    }

    /// <summary>
    /// Invoke the agent with the provided message and arguments.
    /// </summary>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An async list of response items that each contain a <see cref="ChatMessage"/> and an <see cref="AgentThread"/>.</returns>
    /// <remarks>
    /// To continue this thread in the future, use an <see cref="AgentThread"/> returned in one of the response items.
    /// </remarks>
    public async IAsyncEnumerable<AgentResponseItem<ChatMessage>> InvokeAsync(
        ICollection<ChatMessage> messages,
        AgentThread? thread = null,
        AzureAIAgentInvokeOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Verify.NotNull(messages);

        var azureAIAgentThread = await this.EnsureThreadExistsWithMessagesAsync(
            messages,
            thread,
            () => new AzureAIAgentThread(this.Client),
            cancellationToken).ConfigureAwait(false);

        /*
        await foreach ((bool isVisible, ChatMessage message) in AgentThreadActions.InvokeAsync(
            this,
            this.Client,
            azureAIAgentThread.Id!,
            options?.ToAzureAIInvocationOptions(),
            this.Logger,
            cancellationToken).ConfigureAwait(false))
        {
            // The thread and the caller should be notified of all messages regardless of visibility.
            await this.NotifyThreadOfNewMessage(azureAIAgentThread, message, cancellationToken).ConfigureAwait(false);
            if (options?.OnIntermediateMessage is not null)
            {
                await options.OnIntermediateMessage(message).ConfigureAwait(false);
            }

            if (isVisible)
            {
                yield return new(message, azureAIAgentThread);
            }
        }

        // Notify the thread of new messages and return them to the caller.
        await foreach (var result in invokeResults.ConfigureAwait(false))
        {
            yield return new(result, azureAIAgentThread);
        }
        */
        yield break; // Placeholder to avoid compilation error. Replace with actual implementation.
    }

    /// <inheritdoc/>
    public async override IAsyncEnumerable<AgentResponseItem<ChatResponseUpdate>> InvokeStreamingAsync(
        ICollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Verify.NotNull(messages);

        // options is AzureAIAgentInvokeOptions azureAIAgentInvokeOptions ? azureAIAgentInvokeOptions : new AzureAIAgentInvokeOptions(options)

        var azureAIAgentThread = await this.EnsureThreadExistsWithMessagesAsync(
            messages,
            thread,
            () => new AzureAIAgentThread(this.Client),
            cancellationToken).ConfigureAwait(false);

        /*
#pragma warning disable CS0618 // Type or member is obsolete
        // Invoke the Agent with the thread that we already added our message to.
        var newMessagesReceiver = new List<ChatMessage>();
        var invokeResults = this.InvokeStreamingAsync(
            azureAIAgentThread.Id!,
            options?.ToAzureAIInvocationOptions(),
            newMessagesReceiver,
            cancellationToken);
#pragma warning restore CS0618 // Type or member is obsolete

        // Return the chunks to the caller.
        await foreach (var result in invokeResults.ConfigureAwait(false))
        {
            yield return new(result, azureAIAgentThread);
        }

        // Notify the thread of any new messages that were assembled from the streaming response.
        foreach (var newMessage in newMessagesReceiver)
        {
            await this.NotifyThreadOfNewMessage(azureAIAgentThread, newMessage, cancellationToken).ConfigureAwait(false);

            if (options?.OnIntermediateMessage is not null)
            {
                await options.OnIntermediateMessage(newMessage).ConfigureAwait(false);
            }
        }
        */
        yield break; // Placeholder to avoid compilation error. Replace with actual implementation.
    }
}
