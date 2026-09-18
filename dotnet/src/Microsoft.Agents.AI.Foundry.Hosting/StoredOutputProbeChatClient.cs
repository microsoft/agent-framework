// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI.Chat;
using OpenAI.Responses;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// A chat client that answers without calling anything, and records whether the request it was handed
/// asks for the response to be stored.
/// </summary>
/// <remarks>
/// <para>
/// Used by <see cref="HostedStoredOutputHealthCheck"/> to run an agent for real, through
/// <c>ChatClientAgentRunOptions.ChatClientFactory</c>, and see the request that agent builds on its own.
/// Nothing hosting would add later is applied here, so what this observes is the container's own
/// configuration. Nothing leaves the process either.
/// </para>
/// <para>
/// The reply carries no conversation id, so the agent is not led to believe a service kept the
/// conversation.
/// </para>
/// </remarks>
internal sealed class StoredOutputProbeChatClient : IChatClient
{
    /// <summary>
    /// Whether the observed request asked for the response to be stored, or <see langword="null"/> when
    /// the run never reached the client or the request carries no such setting.
    /// </summary>
    public bool? StoredOutputEnabled { get; private set; }

    /// <inheritdoc />
    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        this.Observe(options);
        return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, string.Empty)));
    }

    /// <inheritdoc />
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await Task.CompletedTask.ConfigureAwait(false);
        this.Observe(options);
        yield return new ChatResponseUpdate(ChatRole.Assistant, string.Empty);
    }

    /// <inheritdoc />
    public object? GetService(Type serviceType, object? serviceKey = null) =>
        serviceKey is null && serviceType?.IsInstanceOfType(this) is true ? this : null;

    /// <inheritdoc />
    public void Dispose()
    {
    }

    private void Observe(ChatOptions? options)
    {
        // Building the request is what the agent's chat client would do next, so running the factory
        // here shows the very setting that would have gone out.
        var rawRepresentation = options?.RawRepresentationFactory?.Invoke(this);
        this.StoredOutputEnabled = MapStoreSettingFromRawRepresentation(rawRepresentation);
    }

    /// <summary>
    /// Reads whether a request the agent's chat client would send asks for the response to be stored.
    /// Returns <see langword="null"/> when the request shape could not be inferred, which is a request
    /// type this package has nothing to say about.
    /// </summary>
    private static bool? MapStoreSettingFromRawRepresentation(object? rawRepresentation) => rawRepresentation switch
    {
        // by default when the stored output setting is not set, the service stores the response, and we need to make the distinction from null (different request type)
        // so we can throw the right error in the health check
        CreateResponseOptions responseOptions => responseOptions.StoredOutputEnabled ?? true,
        ChatCompletionOptions completionOptions => completionOptions.StoredOutputEnabled ?? true,
        _ => null,
    };
}
