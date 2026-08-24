// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Captures the per-session identity values produced by a <see cref="HostedSessionIsolationKeyProvider"/>
/// when a Foundry hosted agent processes a request.
/// </summary>
/// <remarks>
/// <para>
/// The <see cref="UserId"/> partitions data that belongs to the individual who initiated the request
/// (e.g., personal memory, per-user preferences). It is an opaque string whose meaning is determined
/// by the active <see cref="HostedSessionIsolationKeyProvider"/>.
/// </para>
/// <para>
/// Instances are constructed by the hosting layer from the platform-provided
/// <c>PlatformContext</c> and stored on the session via
/// <see cref="HostedSessionContextExtensions.SetHostedContext"/>. Consumers (typically
/// <see cref="AIContextProvider"/> implementations) read the value through
/// <see cref="HostedSessionContextExtensions.GetHostedContext"/>.
/// </para>
/// <para>
/// On container protocol version <c>2.0.0</c> there is no per-chat partition header; chat-level
/// isolation is handled by the platform, so the container partitions per user only.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class HostedSessionContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="HostedSessionContext"/> class.
    /// </summary>
    /// <param name="userId">The opaque user identity for this hosted session. Must not be null or whitespace.</param>
    /// <exception cref="System.ArgumentException">Thrown when <paramref name="userId"/> is null or whitespace.</exception>
    public HostedSessionContext(string userId)
    {
        this.UserId = Throw.IfNullOrWhitespace(userId);
    }

    /// <summary>
    /// Gets the opaque user identity for this hosted session.
    /// </summary>
    /// <remarks>
    /// Stable for a given user across sessions. In production this is sourced from the
    /// <c>x-agent-user-id</c> platform header.
    /// </remarks>
    public string UserId { get; }
}
