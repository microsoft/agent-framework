// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating chat client that enriches input messages, tools, and instructions by invoking a pipeline of
/// <see cref="AIContextProvider"/> instances before delegating to the inner chat client, and notifies those
/// providers after the inner client completes.
/// </summary>
/// <remarks>
/// <para>
/// This chat client must be used within the context of a running <see cref="AIAgent"/>. It retrieves the current
/// agent and session from <see cref="AIAgent.CurrentRunContext"/>, which is set automatically when an agent's
/// <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/> or
/// <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/> method is called.
/// An <see cref="InvalidOperationException"/> is thrown if no run context is available.
/// </para>
/// </remarks>
internal sealed class AIContextProviderChatClient : DelegatingChatClient
{
    private readonly IReadOnlyList<AIContextProvider> _providers;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIContextProviderChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying chat client that will handle the core operations.</param>
    /// <param name="providers">The AI context providers to invoke before and after the inner chat client.</param>
    public AIContextProviderChatClient(IChatClient innerClient, IReadOnlyList<AIContextProvider> providers)
        : base(innerClient)
    {
        Throw.IfNull(providers);

        if (providers.Count == 0)
        {
            Throw.ArgumentException(nameof(providers), "At least one AIContextProvider must be provided.");
        }

        this._providers = providers;
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var runContext = GetRequiredRunContext();
        var (enrichedMessages, enrichedOptions) = await this.InvokeProvidersAsync(runContext, messages, options, cancellationToken).ConfigureAwait(false);

        ChatResponse response;
        try
        {
            response = await base.GetResponseAsync(enrichedMessages, enrichedOptions, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await this.NotifyProvidersOfFailureAsync(runContext, enrichedMessages, ex, cancellationToken).ConfigureAwait(false);
            throw;
        }

        await this.NotifyProvidersOfSuccessAsync(runContext, enrichedMessages, response.Messages, cancellationToken).ConfigureAwait(false);

        return response;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var runContext = GetRequiredRunContext();
        var (enrichedMessages, enrichedOptions) = await this.InvokeProvidersAsync(runContext, messages, options, cancellationToken).ConfigureAwait(false);

        List<ChatResponseUpdate> responseUpdates = [];

        IAsyncEnumerator<ChatResponseUpdate> enumerator;
        try
        {
            enumerator = base.GetStreamingResponseAsync(enrichedMessages, enrichedOptions, cancellationToken).GetAsyncEnumerator(cancellationToken);
        }
        catch (Exception ex)
        {
            await this.NotifyProvidersOfFailureAsync(runContext, enrichedMessages, ex, cancellationToken).ConfigureAwait(false);
            throw;
        }

        bool hasUpdates;
        try
        {
            hasUpdates = await enumerator.MoveNextAsync().ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await this.NotifyProvidersOfFailureAsync(runContext, enrichedMessages, ex, cancellationToken).ConfigureAwait(false);
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
                await this.NotifyProvidersOfFailureAsync(runContext, enrichedMessages, ex, cancellationToken).ConfigureAwait(false);
                throw;
            }
        }

        var chatResponse = responseUpdates.ToChatResponse();
        await this.NotifyProvidersOfSuccessAsync(runContext, enrichedMessages, chatResponse.Messages, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Gets the current <see cref="AgentRunContext"/>, throwing if not available.
    /// </summary>
    private static AgentRunContext GetRequiredRunContext()
    {
        return AIAgent.CurrentRunContext
            ?? throw new InvalidOperationException(
                $"{nameof(AIContextProviderChatClient)} can only be used within the context of a running AIAgent. " +
                "Ensure that the chat client is being invoked as part of an AIAgent.RunAsync or AIAgent.RunStreamingAsync call.");
    }

    /// <summary>
    /// Invokes each provider's <see cref="AIContextProvider.InvokingAsync"/> in sequence,
    /// accumulating context (messages, tools, instructions) from each.
    /// </summary>
    private async Task<(IEnumerable<ChatMessage> Messages, ChatOptions? Options)> InvokeProvidersAsync(
        AgentRunContext runContext,
        IEnumerable<ChatMessage> messages,
        ChatOptions? options,
        CancellationToken cancellationToken)
    {
        var aiContext = new AIContext
        {
            Instructions = options?.Instructions,
            Messages = messages,
            Tools = options?.Tools
        };

        foreach (var provider in this._providers)
        {
            var invokingContext = new AIContextProvider.InvokingContext(runContext.Agent, runContext.Session, aiContext);
            aiContext = await provider.InvokingAsync(invokingContext, cancellationToken).ConfigureAwait(false);
        }

        // Materialize the accumulated context back into messages and options.
        var enrichedMessages = aiContext.Messages ?? [];

        var tools = aiContext.Tools as IList<AITool> ?? aiContext.Tools?.ToList();
        if (options?.Tools is { Count: > 0 } || tools is { Count: > 0 })
        {
            options ??= new();
            options.Tools = tools;
        }

        if (options?.Instructions is not null || aiContext.Instructions is not null)
        {
            options ??= new();
            options.Instructions = aiContext.Instructions;
        }

        return (enrichedMessages, options);
    }

    /// <summary>
    /// Notifies each provider of a successful invocation.
    /// </summary>
    private async Task NotifyProvidersOfSuccessAsync(
        AgentRunContext runContext,
        IEnumerable<ChatMessage> requestMessages,
        IEnumerable<ChatMessage> responseMessages,
        CancellationToken cancellationToken)
    {
        var invokedContext = new AIContextProvider.InvokedContext(runContext.Agent, runContext.Session, requestMessages, responseMessages);

        foreach (var provider in this._providers)
        {
            await provider.InvokedAsync(invokedContext, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Notifies each provider of a failed invocation.
    /// </summary>
    private async Task NotifyProvidersOfFailureAsync(
        AgentRunContext runContext,
        IEnumerable<ChatMessage> requestMessages,
        Exception exception,
        CancellationToken cancellationToken)
    {
        var invokedContext = new AIContextProvider.InvokedContext(runContext.Agent, runContext.Session, requestMessages, exception);

        foreach (var provider in this._providers)
        {
            await provider.InvokedAsync(invokedContext, cancellationToken).ConfigureAwait(false);
        }
    }
}
