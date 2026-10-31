// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// An <see cref="A2AServer"/> that captures the caller's isolation key while the request is still active,
/// so that execution which outlives the request stays scoped to that caller.
/// </summary>
/// <remarks>
/// Message execution can detach from the request that started it, either because the client asked for an
/// immediate response or because a streaming client disconnected. Providers that read the caller from
/// IHttpContextAccessor return <see langword="null"/> once the request ends, so the key is resolved up front
/// and flowed to <see cref="IsolationKeyScopedTaskStore"/> and <see cref="A2AAgentHandler"/> through the
/// async call flow that the detached execution inherits.
/// </remarks>
internal sealed class IsolationKeyCapturingA2AServer : A2AServer
{
    private readonly AgentIsolationKeyProvider _keyProvider;

    public IsolationKeyCapturingA2AServer(
        IAgentHandler handler,
        ITaskStore taskStore,
        ChannelEventNotifier notifier,
        ILogger<A2AServer> logger,
        AgentIsolationKeyProvider keyProvider,
        A2AServerOptions? options = null)
        : base(handler, taskStore, notifier, logger, options)
    {
        ArgumentNullException.ThrowIfNull(keyProvider);

        this._keyProvider = keyProvider;
    }

    /// <inheritdoc />
    public override async Task<SendMessageResponse> SendMessageAsync(
        SendMessageRequest request, CancellationToken cancellationToken = default)
    {
        string? isolationKey = await this._keyProvider.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);
        using IDisposable? isolationScope = UseCapturedIsolationKey(isolationKey);
        return await base.SendMessageAsync(request, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public override async IAsyncEnumerable<StreamResponse> SendStreamingMessageAsync(
        SendMessageRequest request, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string? isolationKey = await this._keyProvider.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);

        // The base server starts execution on its first iteration, which runs inside this scope.
        using IDisposable? isolationScope = UseCapturedIsolationKey(isolationKey);
        await foreach (StreamResponse response in base.SendStreamingMessageAsync(request, cancellationToken).ConfigureAwait(false))
        {
            yield return response;
        }
    }

    // Keys that are missing or blank are left to the stores, which apply their own strict mode handling.
    private static IDisposable? UseCapturedIsolationKey(string? isolationKey) =>
        string.IsNullOrWhiteSpace(isolationKey) ? null : IsolationKeyScopedTaskStore.UseCapturedIsolationKey(isolationKey);
}
