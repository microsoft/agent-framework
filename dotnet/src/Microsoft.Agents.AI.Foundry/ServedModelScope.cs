// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Threading;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// AsyncLocal carrier that bridges the <c>x-ms-served-model</c> response header value from the
/// <see cref="ServedModelPolicy"/> running inside the SCM transport pipeline up to the
/// <see cref="FoundryChatClient"/> decorator.
/// </summary>
/// <remarks>
/// <para>
/// Because <see cref="AsyncLocal{T}"/> mutations inside a child <c>async</c> method do not propagate
/// back to the caller (copy-on-write semantics), this scope uses <see cref="StrongBox{T}"/> as an
/// indirection layer. The <see cref="FoundryChatClient"/> pushes a fresh box onto the scope
/// before calling the inner client; the <see cref="ServedModelPolicy"/> writes into the box's
/// <see cref="StrongBox{T}.Value"/> (a reference-type mutation visible to anyone holding the same box).
/// After the inner call returns, the client reads the box's value.
/// </para>
/// </remarks>
internal static class ServedModelScope
{
    private static readonly AsyncLocal<StrongBox<string?>?> s_current = new();

    /// <summary>
    /// Gets or sets the per-async-flow served model box.
    /// </summary>
    public static StrongBox<string?>? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }
}
