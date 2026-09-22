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
/// Use <see cref="WithFoundryHostedAgentSessionId"/> to send <c>agent_session_id</c> on the
/// Responses body for a single run.
/// </para>
/// <para>
/// Hosted-agent session ids supplied via <see cref="WithFoundryHostedAgentSessionId"/> participate in the same
/// conflict rule as <see cref="ChatOptions.ConversationId"/>: if the <see cref="AgentSession"/> already
/// holds a different hosted id in its <see cref="AgentSession.StateBag"/>, the run throws
/// <see cref="System.InvalidOperationException"/>. Prefer pinning at session creation via
/// <see cref="FoundryAgent.CreateFoundryHostedAgentSessionAsync(string?, string?, string?, System.Threading.CancellationToken)"/>.
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
    /// Attaches a hosted-agent session id to the per-call <paramref name="options"/> carrier.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Only valid when the run's session has no hosted id yet, or already has this same id.
    /// Prefer
    /// <see cref="FoundryAgent.CreateFoundryHostedAgentSessionAsync(string?, string?, string?, System.Threading.CancellationToken)"/>
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
}
