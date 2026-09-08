// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Resolves the isolation key for the caller and composes storage identifiers that are scoped to it.
/// </summary>
/// <remarks>
/// <para>
/// This mirrors the scoping performed by <see cref="IsolationKeyScopedAgentSessionStore"/>: a
/// client-supplied identifier is rewritten to <c>{escapedIsolationKey}::{identifier}</c> before it reaches
/// storage, so an identifier belonging to another caller resolves into a namespace that does not contain
/// their data.
/// </para>
/// </remarks>
internal sealed class IsolationKeyResolver
{
    private readonly AgentIsolationKeyProvider? _keyProvider;
    private readonly bool _strict;

    /// <summary>
    /// Initializes a new instance of the <see cref="IsolationKeyResolver"/> class.
    /// </summary>
    /// <param name="keyProvider">The provider used to resolve the isolation key, or <see langword="null"/> when isolation is not configured.</param>
    /// <param name="strict">When <see langword="true"/>, an <see cref="InvalidOperationException"/> is thrown if the key cannot be determined.</param>
    public IsolationKeyResolver(AgentIsolationKeyProvider? keyProvider, bool strict)
    {
        this._keyProvider = keyProvider;
        this._strict = strict;
    }

    /// <summary>
    /// Resolves the isolation key for the current caller.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The isolation key, or <see langword="null"/> when isolation is not configured.</returns>
    /// <exception cref="InvalidOperationException">Isolation is configured but no key could be resolved.</exception>
    public async ValueTask<string?> GetKeyAsync(CancellationToken cancellationToken)
    {
        string? key = this._keyProvider is null
            ? null
            : await this._keyProvider.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);

        if (this._strict && key is null)
        {
            throw new InvalidOperationException(
                "Agent isolation key is required but was not provided by the configured AgentIsolationKeyProvider. " +
                "Ensure the endpoints require an authenticated caller (for example by calling RequireAuthorization()) " +
                "and that the configured claim type is present on that caller.");
        }

        return key;
    }

    /// <summary>
    /// Resolves the isolation key and composes a storage identifier scoped to it.
    /// </summary>
    /// <param name="id">The bare identifier supplied by the caller.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The scoped identifier, or <paramref name="id"/> when isolation is not configured.</returns>
    public async ValueTask<string> ScopeIdAsync(string id, CancellationToken cancellationToken)
        => ScopeId(id, await this.GetKeyAsync(cancellationToken).ConfigureAwait(false));

    /// <summary>
    /// Prefixes a bare identifier with the escaped isolation key, or returns it unchanged when no key applies.
    /// </summary>
    /// <param name="id">The bare identifier.</param>
    /// <param name="key">The isolation key, or <see langword="null"/> when isolation is not configured.</param>
    /// <returns>The scoped identifier.</returns>
    public static string ScopeId(string id, string? key)
        => key is null ? id : $"{EscapeIsolationKey(key)}::{id}";

    /// <summary>
    /// Determines whether an identifier belongs to the supplied isolation key.
    /// </summary>
    /// <param name="scopedId">The scoped identifier.</param>
    /// <param name="key">The isolation key, or <see langword="null"/> when isolation is not configured.</param>
    /// <returns><see langword="true"/> when the identifier belongs to the supplied isolation key; otherwise, <see langword="false"/>.</returns>
    public static bool IsInScope(string scopedId, string? key)
        => key is null || scopedId.StartsWith(GetPrefix(key), StringComparison.Ordinal);

    /// <summary>
    /// Strips the isolation key prefix from a scoped identifier, or returns it unchanged when the prefix is absent.
    /// </summary>
    /// <param name="scopedId">The scoped identifier.</param>
    /// <param name="key">The isolation key, or <see langword="null"/> when isolation is not configured.</param>
    /// <returns>The bare identifier.</returns>
    public static string UnscopeId(string scopedId, string? key)
    {
        if (key is null)
        {
            return scopedId;
        }

        string prefix = GetPrefix(key);

        return scopedId.StartsWith(prefix, StringComparison.Ordinal)
            ? scopedId.Substring(prefix.Length)
            : scopedId;
    }

    private static string GetPrefix(string key) => $"{EscapeIsolationKey(key)}::";

    /// <summary>
    /// Escapes special characters in the isolation key so that scoped identifiers remain unambiguous.
    /// </summary>
    /// <remarks>
    /// Backslashes are escaped first (<c>\</c> becomes <c>\\</c>), then colons (<c>:</c> becomes <c>\:</c>),
    /// matching <see cref="IsolationKeyScopedAgentSessionStore"/>.
    /// For example, the input key <c>tenant\region:alice</c> is escaped as
    /// <c>tenant\\region\:alice</c>.
    /// </remarks>
    private static string EscapeIsolationKey(string key) => key.Replace("\\", "\\\\").Replace(":", "\\:");
}
