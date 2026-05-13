// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// A delegating <see cref="AgentSessionStore"/> that scopes session keys by an isolation key
/// provided by a <see cref="SessionIsolationKeyProvider"/>, ensuring that sessions are isolated
/// per logical partition (e.g., user, tenant, or composite key).
/// </summary>
public class IsolationKeyScopedAgentSessionStore : DelegatingAgentSessionStore
{
    private readonly SessionIsolationKeyProvider? _keyProvider;
    private readonly bool _strict;

    /// <summary>
    /// Initializes a new instance of the <see cref="IsolationKeyScopedAgentSessionStore"/> class.
    /// </summary>
    /// <param name="innerStore">The underlying <see cref="AgentSessionStore"/> to delegate to.</param>
    /// <param name="keyProvider">
    /// The <see cref="SessionIsolationKeyProvider"/> used to retrieve the isolation key for the current context.
    /// </param>
    /// <param name="options">The options for configuring the session store. If null, defaults are used.</param>
    /// <exception cref="ArgumentNullException">
    /// <paramref name="innerStore"/> is <see langword="null"/>.
    /// </exception>
    public IsolationKeyScopedAgentSessionStore(
        AgentSessionStore innerStore,
        SessionIsolationKeyProvider? keyProvider,
        IsolationKeyScopedAgentSessionStoreOptions? options = null)
        : base(innerStore)
    {
        this._keyProvider = keyProvider;
        options ??= new IsolationKeyScopedAgentSessionStoreOptions();
        this._strict = options.Strict;
    }

    /// <summary>
    /// Asynchronously retrieves the isolation key from the provider and validates it if in strict mode.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>
    /// The isolation key string, or <see langword="null"/> if no key is available and non-strict mode is enabled.
    /// </returns>
    /// <exception cref="InvalidOperationException">
    /// The provider returned <see langword="null"/> and strict mode is enabled.
    /// </exception>
    private async ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken)
    {
        string? key = this._keyProvider != null
                    ? await this._keyProvider.GetSessionIsolationKeyAsync(cancellationToken).ConfigureAwait(false)
                    : null;

        if (this._strict && key == null)
        {
            throw new InvalidOperationException("Session isolation key is required but was not provided by the configured SessionIsolationKeyProvider.");
        }

        return key;
    }

    /// <summary>
    /// Escapes special characters in the isolation key to ensure unambiguous scoped conversation IDs.
    /// </summary>
    /// <param name="key">The raw isolation key.</param>
    /// <returns>The escaped isolation key.</returns>
    /// <remarks>
    /// Backslashes are escaped first (\ becomes \\), then colons (: becomes \:).
    /// This ensures the scoped conversation ID format {key}::{conversationId} can be parsed correctly.
    /// </remarks>
    private static string EscapeIsolationKey(string key) => key.Replace("\\", "\\\\").Replace(":", "\\:");

    /// <summary>
    /// Constructs a scoped conversation ID by prefixing the bare conversation ID with the escaped isolation key.
    /// </summary>
    /// <param name="bareConversationId">The original conversation ID.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>
    /// The scoped conversation ID in the format {escapedKey}::{conversationId}, or the bare conversation ID
    /// if no isolation key is available and non-strict mode is enabled.
    /// </returns>
    private async ValueTask<string> GetScopedConversationIdAsync(string bareConversationId, CancellationToken cancellationToken)
    {
        string? key = await this.GetIsolationKeyAsync(cancellationToken).ConfigureAwait(false);
        if (key == null)
        {
            return bareConversationId;
        }

        return $"{EscapeIsolationKey(key)}::{bareConversationId}";
    }

    /// <inheritdoc />
    public override async ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
    {
        string scopedConversationId = await this.GetScopedConversationIdAsync(conversationId, cancellationToken).ConfigureAwait(false);
        return await this.InnerStore.GetSessionAsync(agent, scopedConversationId, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public override async ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, CancellationToken cancellationToken = default)
    {
        string scopedConversationId = await this.GetScopedConversationIdAsync(conversationId, cancellationToken).ConfigureAwait(false);
        await this.InnerStore.SaveSessionAsync(agent, scopedConversationId, session, cancellationToken).ConfigureAwait(false);
    }
}
