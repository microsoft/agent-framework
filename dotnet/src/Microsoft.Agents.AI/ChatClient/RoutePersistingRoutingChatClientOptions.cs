// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options that control the behavior of a <see cref="RoutePersistingRoutingChatClient"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class RoutePersistingRoutingChatClientOptions
{
    /// <summary>
    /// Gets or sets the route that a new session is initialized with.
    /// </summary>
    /// <value>
    /// When <see langword="null"/> (the default), the first entry in the routes dictionary supplied to the
    /// <see cref="RoutePersistingRoutingChatClient"/> is used when one exists. The route is validated only when it is
    /// selected, so it does not need to be registered at construction time.
    /// </value>
    public string? DefaultRoute { get; set; }

    /// <summary>
    /// Gets or sets the key used to store the routing state in the <see cref="AgentSession.StateBag"/>.
    /// </summary>
    /// <value>
    /// Defaults to the name of the <see cref="RoutePersistingRoutingChatClient"/> type. Override this when multiple
    /// <see cref="RoutePersistingRoutingChatClient"/> instances need separate state within the same session.
    /// </value>
    public string? StateKey { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the <see cref="RoutePersistingRoutingChatClient"/> owns the registered
    /// route clients and disposes them when it is disposed.
    /// </summary>
    /// <value>
    /// <see langword="false"/> by default, meaning the lifetime of the registered route clients is managed by the
    /// caller. Set to <see langword="true"/> to dispose them together with the
    /// <see cref="RoutePersistingRoutingChatClient"/>.
    /// </value>
    /// <remarks>
    /// When enabled, each distinct client still present in
    /// <see cref="RoutePersistingRoutingChatClient.Routes"/> is disposed once when the routing client is disposed.
    /// Removing or replacing a route transfers responsibility for the removed client's lifetime back to the caller.
    /// </remarks>
    public bool OwnsInnerClients { get; set; }
}
