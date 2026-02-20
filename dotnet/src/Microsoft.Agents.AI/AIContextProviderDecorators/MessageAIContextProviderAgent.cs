// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating AI agent that enriches input messages by invoking a pipeline of <see cref="MessageAIContextProvider"/> instances
/// before delegating to the inner agent, and notifies those providers after the inner agent completes.
/// </summary>
internal sealed class MessageAIContextProviderAgent : DelegatingAIAgent
{
    private readonly IReadOnlyList<MessageAIContextProvider> _providers;

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageAIContextProviderAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent instance that will handle the core operations.</param>
    /// <param name="providers">The message AI context providers to invoke before and after the inner agent.</param>
    public MessageAIContextProviderAgent(AIAgent innerAgent, IReadOnlyList<MessageAIContextProvider> providers)
        : base(innerAgent)
    {
        Throw.IfNull(providers);
        Throw.IfLessThanOrEqual(providers.Count, 0, nameof(providers));

        this._providers = providers;
    }

    /// <inheritdoc/>
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var enrichedMessages = await this.InvokeProvidersAsync(messages, session, cancellationToken).ConfigureAwait(false);

        AgentResponse response;
        try
        {
            response = await this.InnerAgent.RunAsync(enrichedMessages, session, options, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await this.NotifyProvidersOfFailureAsync(session, enrichedMessages, ex, cancellationToken).ConfigureAwait(false);
            throw;
        }

        await this.NotifyProvidersOfSuccessAsync(session, enrichedMessages, response.Messages, cancellationToken).ConfigureAwait(false);

        return response;
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var enrichedMessages = await this.InvokeProvidersAsync(messages, session, cancellationToken).ConfigureAwait(false);

        List<AgentResponseUpdate> responseUpdates = [];

        IAsyncEnumerator<AgentResponseUpdate> enumerator;
        try
        {
            enumerator = this.InnerAgent.RunStreamingAsync(enrichedMessages, session, options, cancellationToken).GetAsyncEnumerator(cancellationToken);
        }
        catch (Exception ex)
        {
            await this.NotifyProvidersOfFailureAsync(session, enrichedMessages, ex, cancellationToken).ConfigureAwait(false);
            throw;
        }

        bool hasUpdates;
        try
        {
            hasUpdates = await enumerator.MoveNextAsync().ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await this.NotifyProvidersOfFailureAsync(session, enrichedMessages, ex, cancellationToken).ConfigureAwait(false);
            throw;
        }

        while (hasUpdates)
        {
            var update = enumerator.Current;
            responseUpdates.Add(update);
            yield return update;

            try
            {
                hasUpdates = await enumerator.MoveNextAsync().ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                await this.NotifyProvidersOfFailureAsync(session, enrichedMessages, ex, cancellationToken).ConfigureAwait(false);
                throw;
            }
        }

        var agentResponse = responseUpdates.ToAgentResponse();
        await this.NotifyProvidersOfSuccessAsync(session, enrichedMessages, agentResponse.Messages, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Invokes each provider's <see cref="MessageAIContextProvider.InvokingAsync"/> in sequence,
    /// passing the output of each as input to the next.
    /// </summary>
    private async Task<IEnumerable<ChatMessage>> InvokeProvidersAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session,
        CancellationToken cancellationToken)
    {
        var currentMessages = messages;

        foreach (var provider in this._providers)
        {
            var context = new MessageAIContextProvider.InvokingContext(this, session, currentMessages);
            currentMessages = await provider.InvokingAsync(context, cancellationToken).ConfigureAwait(false);
        }

        return currentMessages;
    }

    /// <summary>
    /// Notifies each provider of a successful invocation.
    /// </summary>
    private async Task NotifyProvidersOfSuccessAsync(
        AgentSession? session,
        IEnumerable<ChatMessage> requestMessages,
        IEnumerable<ChatMessage> responseMessages,
        CancellationToken cancellationToken)
    {
        var invokedContext = new AIContextProvider.InvokedContext(this, session, requestMessages, responseMessages);

        foreach (var provider in this._providers)
        {
            await provider.InvokedAsync(invokedContext, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Notifies each provider of a failed invocation.
    /// </summary>
    private async Task NotifyProvidersOfFailureAsync(
        AgentSession? session,
        IEnumerable<ChatMessage> requestMessages,
        Exception exception,
        CancellationToken cancellationToken)
    {
        var invokedContext = new AIContextProvider.InvokedContext(this, session, requestMessages, exception);

        foreach (var provider in this._providers)
        {
            await provider.InvokedAsync(invokedContext, cancellationToken).ConfigureAwait(false);
        }
    }
}
