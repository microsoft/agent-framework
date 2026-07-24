// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options that control the behavior of a <see cref="RoutingChatClient"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class RoutingChatClientOptions
{
    /// <summary>
    /// Gets or sets a custom asynchronous routing heuristic that selects the destination key for a request.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The function receives a <see cref="RoutingContext"/> and a <see cref="CancellationToken"/> and returns
    /// the key of the destination that should handle the request, or <see langword="null"/> to route the request
    /// directly to the fallback factory (invoked with a <see langword="null"/> key). It is asynchronous so callers
    /// can perform I/O (for example, an inference call) to decide the best destination. When <see langword="null"/>
    /// (the default), the currently active destination for the session is used (see
    /// <see cref="RoutingContext.ActiveDestination"/>).
    /// </para>
    /// <para>
    /// The returned key is used only for the current request; it does not change the session's active
    /// destination. Use <see cref="RoutingChatClient.SetActiveDestinationKey"/> to switch the active destination.
    /// </para>
    /// </remarks>
    public Func<RoutingContext, CancellationToken, ValueTask<string?>>? Router { get; set; }

    /// <summary>
    /// Gets or sets the key used to store the routing state in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    /// <value>
    /// Defaults to the client's type name. Override this if you need multiple <see cref="RoutingChatClient"/>
    /// instances with separate state in the same session.
    /// </value>
    public string? StateKey { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether disposal of chat clients created by the fallback factory is
    /// disabled.
    /// </summary>
    /// <value>
    /// <see langword="false"/> by default, meaning a client created by the fallback factory is disposed after the
    /// request that created it completes. Set to <see langword="true"/> to keep such clients alive after use — for
    /// example, when the factory caches or returns shared clients whose lifetime it manages itself.
    /// </value>
    public bool DisableFallbackChatClientDisposal { get; set; }
}
