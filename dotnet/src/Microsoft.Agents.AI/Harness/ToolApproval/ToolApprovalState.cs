// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the persisted state of standing tool approval rules,
/// stored in the session's <see cref="AgentSessionStateBag"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class ToolApprovalState
{
    /// <summary>
    /// Gets or sets the list of standing approval rules.
    /// </summary>
    [JsonPropertyName("rules")]
    public List<ToolApprovalRule> Rules { get; set; } = new();

    /// <summary>
    /// Gets or sets the list of collected approval responses (both auto-approved and user-approved)
    /// that are pending injection into the next inbound call to the inner agent.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Responses are collected during a queue cycle: when the inner agent returns multiple tool approval
    /// requests, auto-approved ones and user-approved ones are accumulated here. Once all queued requests
    /// are resolved, the collected responses are injected alongside the caller's messages so the inner
    /// agent receives all tool responses together.
    /// </para>
    /// </remarks>
    [JsonPropertyName("collectedApprovalResponses")]
    public List<ToolApprovalResponseContent> CollectedApprovalResponses { get; set; } = new();

    /// <summary>
    /// Gets or sets the list of queued tool approval requests that have not yet been
    /// presented to the caller.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When the inner agent returns multiple unapproved tool approval requests, only the first
    /// is returned to the caller. The remaining requests are stored here and presented one at a
    /// time on subsequent calls, allowing the caller's "always approve" rules to take effect on
    /// later items in the same batch.
    /// </para>
    /// </remarks>
    [JsonPropertyName("queuedApprovalRequests")]
    public List<ToolApprovalRequestContent> QueuedApprovalRequests { get; set; } = new();
}
