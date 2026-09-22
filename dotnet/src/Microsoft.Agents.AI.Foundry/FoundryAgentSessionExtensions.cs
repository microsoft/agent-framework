// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Foundry-specific extension methods for <see cref="AgentSession"/>.
/// </summary>
/// <remarks>
/// <para>
/// The hosted-agent session id (sandbox / <c>agent_session_id</c>) is stored in
/// <see cref="AgentSession.StateBag"/> under <see cref="FoundryHostedAgentSessionIdKey"/>. That keeps
/// Foundry-specific state off the sealed <see cref="ChatClientAgentSession"/> type while still
/// serializing with the session.
/// </para>
/// <para>
/// The delegated user identity is stored in the same state bag. A session created for one user must
/// not be reused for another user, even when both sessions share the same hosted-agent session id.
/// </para>
/// <para>
/// This is not <see cref="Extensions.AI.ChatOptions.AdditionalProperties"/>. Per-call
/// overrides use
/// <see cref="Extensions.AI.FoundryChatOptionsExtensions.WithFoundryHostedAgentSessionId(Extensions.AI.ChatOptions, string)"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIRequestPolicies)]
public static class FoundryAgentSessionExtensions
{
    /// <summary>
    /// Well-known <see cref="AgentSessionStateBag"/> key for the sticky hosted-agent session id.
    /// </summary>
    public const string FoundryHostedAgentSessionIdKey = "Microsoft.Agents.AI.Foundry.HostedAgentSessionId";

    private const string FoundryHostedAgentUserIdentityKey = "Microsoft.Agents.AI.Foundry.UserIdentity";

    extension(AgentSession session)
    {
        /// <summary>
        /// Gets the sticky Microsoft Foundry hosted-agent session id associated with this
        /// Agent Framework session.
        /// </summary>
        /// <value>
        /// The Foundry <c>agent_session_id</c>, or <see langword="null"/> when no hosted sandbox
        /// has been pinned or captured yet.
        /// </value>
        /// <remarks>
        /// <para>
        /// This id identifies the Foundry-managed hosted-agent sandbox: its compute, persisted
        /// <c>$HOME</c>, and files. It is separate from
        /// <see cref="ChatClientAgentSession.ConversationId"/>, which identifies conversation
        /// history.
        /// </para>
        /// <para>
        /// Prefer creating or pinning through
        /// <see cref="FoundryAgent.CreateFoundryHostedAgentSessionAsync(string?, string?, string?, System.Threading.CancellationToken)"/>.
        /// The property is populated automatically when Foundry creates a sandbox on first use.
        /// See
        /// <see href="https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-sessions#sessions-versus-conversations">Manage hosted agent sessions</see>.
        /// </para>
        /// </remarks>
        public string? FoundryHostedAgentSessionId
        {
            get
            {
                _ = Throw.IfNull(session);
                return session.StateBag.TryGetValue<string>(FoundryHostedAgentSessionIdKey, out var value)
                    ? value
                    : null;
            }

            internal set
            {
                _ = Throw.IfNull(session);
                _ = Throw.IfNullOrWhitespace(value);
                session.StateBag.SetValue(FoundryHostedAgentSessionIdKey, value);
            }
        }

        /// <summary>
        /// Gets the delegated application user identity associated with this Agent Framework session.
        /// </summary>
        /// <value>
        /// The opaque application user identifier sent as <c>x-ms-user-identity</c>, or
        /// <see langword="null"/> when the session has no delegated identity.
        /// </value>
        /// <remarks>
        /// The identity is fixed when the session is created through
        /// <see cref="FoundryAgent.CreateFoundryHostedAgentSessionAsync(string?, string?, string?, System.Threading.CancellationToken)"/>.
        /// Reusing this session automatically sends the same identity on every run. Create a separate
        /// <see cref="AgentSession"/> for each user; separate sessions may share the same
        /// <c>FoundryHostedAgentSessionId</c>.
        /// </remarks>
        public string? FoundryHostedAgentUserIdentity
        {
            get
            {
                _ = Throw.IfNull(session);
                return session.StateBag.TryGetValue<string>(FoundryHostedAgentUserIdentityKey, out var value)
                    ? value
                    : null;
            }

            internal set
            {
                _ = Throw.IfNull(session);
                _ = Throw.IfNullOrWhitespace(value);
                session.StateBag.SetValue(FoundryHostedAgentUserIdentityKey, value);
            }
        }
    }
}
