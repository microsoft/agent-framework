// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a process-wide context that enables the hosted-agent runtime to signal supplemental
/// User-Agent information to the outgoing <see cref="System.ClientModel.Primitives.PipelinePolicy"/>
/// without requiring direct coupling between the policy and the hosting layer.
/// </summary>
/// <remarks>
/// When an agent is running inside a Foundry Hosted Agent, the hosting layer sets
/// <see cref="UserAgentSupplement"/> at startup to a string like
/// <c>"foundry-hosting/agent-framework-dotnet/1.0.0"</c>. The MEAI pipeline policy reads
/// this value on each outgoing request and appends it to the <c>User-Agent</c> header.
/// </remarks>
public static class HostedAgentContext
{
    private static volatile string? s_userAgentSupplement;

    /// <summary>
    /// Gets or sets an optional supplemental User-Agent segment (e.g. <c>"foundry-hosting/agent-framework-dotnet/1.0.0"</c>)
    /// that will be appended to the base MEAI User-Agent header on outgoing requests.
    /// </summary>
    /// <value>
    /// The supplemental User-Agent string, or <see langword="null"/> when the agent is not
    /// running in a hosted context. This value is process-wide and typically set once at startup.
    /// </value>
    public static string? UserAgentSupplement
    {
        get => s_userAgentSupplement;
        set => s_userAgentSupplement = value;
    }
}
