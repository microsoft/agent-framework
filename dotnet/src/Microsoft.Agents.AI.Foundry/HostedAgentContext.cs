// Copyright (c) Microsoft. All rights reserved.

using System.Threading;

namespace Microsoft.Agents.AI;

/// <summary>
/// Async-local context that enables the hosted-agent runtime to signal supplemental
/// User-Agent information to the outgoing <see cref="System.ClientModel.Primitives.PipelinePolicy"/>
/// without requiring direct coupling between the policy and the hosting layer.
/// </summary>
/// <remarks>
/// <para>
/// When an agent is running inside a Foundry Hosted Agent, the hosting layer sets
/// <see cref="UserAgentSupplement"/> to a string like <c>"foundry-hosting/agent-framework-dotnet/1.0.0"</c>.
/// The MEAI pipeline policy reads this value on each outgoing request and appends it to
/// the <c>User-Agent</c> header.
/// </para>
/// <para>
/// Because <see cref="AsyncLocal{T}"/> flows with the <see cref="ExecutionContext"/>,
/// the value set in the hosting handler automatically propagates to all outgoing HTTP calls
/// made during that request, and is naturally scoped — concurrent requests do not interfere.
/// </para>
/// </remarks>
public static class HostedAgentContext
{
    private static readonly AsyncLocal<string?> s_userAgentSupplement = new();

    /// <summary>
    /// Gets or sets an optional supplemental User-Agent segment (e.g. <c>"foundry-hosting/agent-framework-dotnet/1.0.0"</c>)
    /// that will be appended to the base MEAI User-Agent header on outgoing requests.
    /// </summary>
    /// <value>
    /// The supplemental User-Agent string, or <see langword="null"/> when the agent is not
    /// running in a hosted context. This value flows with the async execution context.
    /// </value>
    public static string? UserAgentSupplement
    {
        get => s_userAgentSupplement.Value;
        set => s_userAgentSupplement.Value = value;
    }
}
