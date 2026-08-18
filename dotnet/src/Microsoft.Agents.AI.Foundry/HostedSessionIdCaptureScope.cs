// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Threading;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// AsyncLocal carrier for the mutable hosted-agent session id box shared by
/// <see cref="FoundryHostedRequestAgent"/> (request body injection) and
/// <see cref="HostedSessionIdCapturePolicy"/> (response header capture).
/// </summary>
/// <remarks>
/// Uses <see cref="StrongBox{T}"/> so writes inside the transport pipeline remain visible to the
/// agent decorator after the inner call returns (and on later service calls in a function loop).
/// </remarks>
internal static class HostedSessionIdCaptureScope
{
    private static readonly AsyncLocal<StrongBox<string?>?> s_current = new();

    /// <summary>Gets or sets the per-async-flow hosted session id box.</summary>
    public static StrongBox<string?>? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }
}
