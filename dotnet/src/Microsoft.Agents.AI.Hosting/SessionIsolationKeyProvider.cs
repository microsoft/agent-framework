// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides an abstract base class for resolving session isolation keys used to scope agent sessions.
/// </summary>
/// <remarks>
/// <para>
/// Session isolation keys enable multi-tenant or multi-user scenarios by scoping agent session storage
/// to a specific logical partition (e.g., user ID, tenant ID, or composite key). Derived classes
/// implement the key resolution logic appropriate to their hosting environment.
/// </para>
/// <para>
/// When a key is unavailable or cannot be determined, implementations should return <see langword="null"/>.
/// The consuming session store can then enforce strict behavior (throwing an exception) or fall back
/// to unscoped storage based on its configuration.
/// </para>
/// </remarks>
public abstract class SessionIsolationKeyProvider
{
    /// <summary>
    /// Asynchronously retrieves the session isolation key for the current request or execution context.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A task that represents the asynchronous operation. The task result contains the isolation key string,
    /// or <see langword="null"/> if no key is available in the current context.
    /// </returns>
    /// <remarks>
    /// Implementations should extract the key from ambient context (e.g., HTTP request headers, claims,
    /// or environment variables). If the key cannot be determined, return <see langword="null"/> to allow
    /// the caller to decide on strict vs. pass-through behavior.
    /// </remarks>
    public abstract ValueTask<string?> GetSessionIsolationKeyAsync(CancellationToken cancellationToken = default);
}
