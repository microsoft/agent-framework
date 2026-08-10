// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides an abstract base class for resolving keys that isolate resources owned by hosted agents.
/// </summary>
/// <remarks>
/// <para>
/// The <c>Agent</c> prefix identifies the hosting API domain; it does not mean that agent instances
/// themselves are isolated. The returned key scopes agent-owned resources, such as sessions and A2A
/// tasks, to a logical partition (e.g., user ID, tenant ID, or composite key). Other agent resources,
/// such as memory or retrieval data, can use the same key when they require the same isolation boundary.
/// Derived classes implement the key resolution logic appropriate to their hosting environment.
/// </para>
/// <para>
/// When a key is unavailable or cannot be determined, implementations should return <see langword="null"/>.
/// Consuming stores can then enforce strict behavior (throwing an exception) or fall back to unscoped
/// storage based on their configuration.
/// </para>
/// </remarks>
public abstract class AgentIsolationKeyProvider
{
    /// <summary>
    /// Asynchronously retrieves the isolation key for agent-owned resources in the current request or execution context.
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
    public abstract ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken = default);
}
