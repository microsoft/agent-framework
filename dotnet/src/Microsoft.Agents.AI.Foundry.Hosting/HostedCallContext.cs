// Copyright (c) Microsoft. All rights reserved.

using System.Threading;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Ambient holder for the platform-injected per-request call identifier
/// (<c>x-agent-foundry-call-id</c>, available only on container protocol version <c>2.0.0</c>).
/// </summary>
/// <remarks>
/// The call id is opaque and per-request, so it is not stored on the session. The hosting layer
/// sets it for the duration of a request and outbound delegating handlers (e.g. the toolbox bearer
/// handler) forward it verbatim on calls to Foundry first-party services so those services can
/// resolve the server-side-stored caller context.
/// </remarks>
internal static class HostedCallContext
{
    private static readonly AsyncLocal<string?> s_callId = new();

    /// <summary>Gets or sets the current request's call id, or <see langword="null"/> when absent.</summary>
    public static string? CallId
    {
        get => s_callId.Value;
        set => s_callId.Value = value;
    }
}
