// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the serializable routing state of a <see cref="RoutePersistingRoutingChatClient"/>, stored in the
/// session's <see cref="AgentSessionStateBag"/>.
/// </summary>
/// <remarks>
/// This state tracks the route that is currently active for a session, so that the selection survives for the
/// lifetime of the session and across session serialization.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class AgentSessionRoutingState
{
    /// <summary>
    /// Gets or sets the key of the route that is currently active for this session.
    /// </summary>
    /// <remarks>
    /// The value corresponds to a key in the routes dictionary supplied to the
    /// <see cref="RoutePersistingRoutingChatClient"/>. A new session is initialized with the configured default route.
    /// </remarks>
    [JsonPropertyName("activeRoute")]
    public string? ActiveRoute { get; set; }
}
