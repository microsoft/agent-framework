// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// AsyncLocal carrier that bridges per-call client-header values from the
/// <see cref="ClientHeadersAgent"/> decorator down to the
/// <see cref="ClientHeadersPolicy"/> running inside the SCM transport pipeline.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="AsyncLocal{T}"/> propagates the value forward into every <c>await</c> on the same
/// async flow, but mutations made inside an awaited <c>async</c> method do <em>not</em> leak back
/// to the caller after the method returns. This means a method that assigns
/// <see cref="Current"/> at the top and then awaits inner work does not need any explicit
/// restoration step: the runtime restores the caller's view of the AsyncLocal automatically when
/// the method's task completes.
/// </para>
/// <para>
/// Setting <see cref="Current"/> from synchronous code, however, will leak to the caller because
/// no async-method boundary is crossed. All Agent Framework call sites of this carrier are
/// inside <c>async</c> methods (<see cref="ClientHeadersAgent"/>), so the natural restoration
/// suffices for our needs.
/// </para>
/// </remarks>
internal static class ClientHeadersScope
{
    private static readonly AsyncLocal<IReadOnlyDictionary<string, string>?> s_current = new();

    /// <summary>
    /// Gets or sets the per-async-flow client-header snapshot read by <see cref="ClientHeadersPolicy"/>.
    /// </summary>
    public static IReadOnlyDictionary<string, string>? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }
}
