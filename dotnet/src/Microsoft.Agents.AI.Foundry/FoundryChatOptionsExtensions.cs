// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Foundry;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Foundry-specific extension methods for <see cref="ChatOptions"/>.
/// </summary>
/// <remarks>
/// <para>
/// Use these helpers to attach per-call Foundry request fields:
/// <list type="bullet">
/// <item><description><see cref="WithFoundryHostedAgentSessionId"/> sends <c>agent_session_id</c> on the Responses body.</description></item>
/// <item><description><see cref="WithFoundryHostedAgentUserIdentity"/> sends <c>x-ms-user-identity</c> on the request.</description></item>
/// </list>
/// </para>
/// <para>
/// Hosted-agent session ids supplied via <see cref="WithFoundryHostedAgentSessionId"/> participate in the same
/// conflict rule as <see cref="ChatOptions.ConversationId"/>: if the <see cref="AgentSession"/> already
/// holds a different hosted id in its <see cref="AgentSession.StateBag"/>, the run throws
/// <see cref="System.InvalidOperationException"/>. Prefer pinning at session creation via
/// <see cref="FoundryAgent.CreateFoundryHostedAgentSessionAsync(string?, string?, System.Threading.CancellationToken)"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIRequestPolicies)]
public static class FoundryChatOptionsExtensions
{
    /// <summary>HTTP header name for delegated application user identity.</summary>
    public const string FoundryHostedAgentUserIdentityHeaderName = "x-ms-user-identity";

    /// <summary>
    /// Well-known <see cref="ChatOptions.AdditionalProperties"/> key used to carry a per-call
    /// hosted-agent session id.
    /// </summary>
    internal const string FoundryHostedAgentSessionIdKey = "Microsoft.Agents.AI.Foundry.HostedAgentSessionId";

    /// <summary>
    /// Well-known <see cref="ChatOptions.AdditionalProperties"/> key used to carry the per-call
    /// user identity value.
    /// </summary>
    internal const string FoundryHostedAgentUserIdentityKey = "Microsoft.Agents.AI.Foundry.UserIdentity";

    /// <summary>
    /// Attaches a hosted-agent session id to the per-call <paramref name="options"/> carrier.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Only valid when the run's session has no hosted id yet, or already has this same id.
    /// Prefer
    /// <see cref="FoundryAgent.CreateFoundryHostedAgentSessionAsync(string?, string?, System.Threading.CancellationToken)"/>
    /// to pin at session creation.
    /// </para>
    /// <para>
    /// The value is stored in <see cref="ChatOptions.AdditionalProperties"/>. Replacing that
    /// dictionary after calling this method removes the value; populate or replace the dictionary
    /// first, then call this method.
    /// </para>
    /// </remarks>
    public static ChatOptions WithFoundryHostedAgentSessionId(this ChatOptions options, string hostedSessionId)
    {
        _ = Throw.IfNull(options);
        _ = Throw.IfNullOrWhitespace(hostedSessionId);

        options.AdditionalProperties ??= new AdditionalPropertiesDictionary();
        options.AdditionalProperties[FoundryHostedAgentSessionIdKey] = hostedSessionId;
        return options;
    }

    /// <summary>
    /// Attaches a delegated user identity value that will be sent as the
    /// <c>x-ms-user-identity</c> request header.
    /// </summary>
    /// <param name="options">The per-call chat options to mutate.</param>
    /// <param name="userIdentity">Opaque application user identifier. Must be non-empty.</param>
    /// <returns><paramref name="options"/> for fluent chaining.</returns>
    /// <remarks>
    /// <para>
    /// User identity is always request-scoped. It is never stored on <see cref="AgentSession"/>.
    /// </para>
    /// <para>
    /// Per Foundry hosted-agent isolation, a Responses chain created under one user cannot be
    /// continued by another user via <c>previous_response_id</c>, even when both calls share the
    /// same hosted sandbox (<c>agent_session_id</c>). See
    /// <see href="https://learn.microsoft.com/azure/foundry/agents/how-to/multiplex-session-users">Multiplex multiple users in one hosted agent session</see>.
    /// Reusing one <see cref="AgentSession"/> across identities typically reuses that chain, so the
    /// second identity's run fails at the platform (observed as a response not-found error). Prefer
    /// a distinct <see cref="AgentSession"/> per identity; those sessions may still share one hosted
    /// sandbox pin via <see cref="WithFoundryHostedAgentSessionId"/> or
    /// <see cref="FoundryAgent.CreateFoundryHostedAgentSessionAsync(string?, string?, System.Threading.CancellationToken)"/>.
    /// </para>
    /// <para>
    /// The value is stored in <see cref="ChatOptions.AdditionalProperties"/>. Replacing that
    /// dictionary after calling this method removes the value; populate or replace the dictionary
    /// first, then call this method.
    /// </para>
    /// </remarks>
    public static ChatOptions WithFoundryHostedAgentUserIdentity(this ChatOptions options, string userIdentity)
    {
        _ = Throw.IfNull(options);
        _ = Throw.IfNullOrWhitespace(userIdentity);

        options.AdditionalProperties ??= new AdditionalPropertiesDictionary();
        options.AdditionalProperties[FoundryHostedAgentUserIdentityKey] = userIdentity;
        return options;
    }

    /// <summary>Reads the per-call hosted-agent session id stamped by <see cref="WithFoundryHostedAgentSessionId"/>.</summary>
    internal static string? GetFoundryHostedAgentSessionId(this ChatOptions options)
    {
        if (options.AdditionalProperties is null)
        {
            return null;
        }

        if (!options.AdditionalProperties.TryGetValue(FoundryHostedAgentSessionIdKey, out var raw))
        {
            return null;
        }

        return raw as string;
    }

    /// <summary>Reads the per-call user identity stamped by <see cref="WithFoundryHostedAgentUserIdentity"/>.</summary>
    internal static string? GetFoundryHostedAgentUserIdentity(this ChatOptions options)
    {
        if (options.AdditionalProperties is null)
        {
            return null;
        }

        if (!options.AdditionalProperties.TryGetValue(FoundryHostedAgentUserIdentityKey, out var raw))
        {
            return null;
        }

        return raw as string;
    }
}
