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
/// Stack-style usage with <c>using</c> ensures LIFO restoration of any prior value.
/// </remarks>
internal static class ClientHeadersScope
{
    private static readonly AsyncLocal<IReadOnlyDictionary<string, string>?> s_current = new();

    /// <summary>Gets the dictionary captured by the most recent <see cref="Push(IReadOnlyDictionary{string, string}?)"/> on this async flow.</summary>
    public static IReadOnlyDictionary<string, string>? Current => s_current.Value;

    /// <summary>
    /// Pushes a new value as the current scope. Disposing the returned token restores the previous value.
    /// </summary>
    /// <param name="headers">The header dictionary to surface to the policy. May be <see langword="null"/>.</param>
    public static Scope Push(IReadOnlyDictionary<string, string>? headers)
    {
        var previous = s_current.Value;
        s_current.Value = headers;
        return new Scope(previous);
    }

    /// <summary>Disposable token that restores the previous scope on <see cref="Dispose"/>.</summary>
    internal readonly struct Scope : System.IDisposable
    {
        private readonly IReadOnlyDictionary<string, string>? _previous;

        internal Scope(IReadOnlyDictionary<string, string>? previous)
        {
            this._previous = previous;
        }

        public void Dispose() => s_current.Value = this._previous;
    }
}
