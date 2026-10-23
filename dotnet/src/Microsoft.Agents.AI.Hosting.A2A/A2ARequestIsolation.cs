// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// The isolation key of the request that performs the A2A operations in the current asynchronous flow.
/// </summary>
/// <remarks>
/// The key is resolved once while the request services are alive, so operations that A2A continues in the
/// background after the request ends reuse it instead of resolving request-scoped services.
/// </remarks>
internal sealed class A2ARequestIsolation
{
    private static readonly AsyncLocal<A2ARequestIsolation?> s_current = new();

    private readonly string? _key;
    private readonly bool _isRequired;

    private A2ARequestIsolation(string? key, bool isRequired)
    {
        this._key = key;
        this._isRequired = isRequired;
    }

    /// <summary>
    /// Gets or sets the isolation of the request that performs the operations in the current asynchronous flow.
    /// </summary>
    public static A2ARequestIsolation? Current
    {
        get => s_current.Value;
        set => s_current.Value = value;
    }

    /// <summary>
    /// Resolves the isolation key from the <see cref="AgentIsolationKeyProvider"/> registered in <paramref name="services"/>.
    /// </summary>
    /// <param name="services">The services of the request or operation.</param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation.</param>
    /// <returns>The resolved isolation, which requires a key when a provider is registered.</returns>
    public static async ValueTask<A2ARequestIsolation> ResolveAsync(IServiceProvider services, CancellationToken cancellationToken)
    {
        AgentIsolationKeyProvider? provider = services.GetService<AgentIsolationKeyProvider>();
        string? key = provider is null ? null : await provider.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);
        return new A2ARequestIsolation(key, isRequired: provider is not null);
    }

    /// <summary>
    /// Gets the isolation key.
    /// </summary>
    /// <returns>The isolation key, or <see langword="null"/> when no provider is registered.</returns>
    /// <exception cref="InvalidOperationException">A provider is registered but did not supply a non-empty key.</exception>
    public string? GetKey() =>
        this._isRequired && string.IsNullOrWhiteSpace(this._key)
            ? throw new InvalidOperationException("Agent isolation key is required but was not provided by the configured AgentIsolationKeyProvider.")
            : this._key;
}
