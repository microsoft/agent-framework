// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Carries Foundry hosting metadata alongside the agent served by the response handler.
/// </summary>
/// <remarks>
/// This wrapper is the central extension point for hosting-specific agent metadata. Outer agent
/// middleware continues to expose it through <see cref="AIAgent.GetService{TService}(object?)"/>.
/// </remarks>
internal sealed class FoundryHostingAgent : DelegatingAIAgent
{
    /// <summary>The prefix of the identity of an agent's sessions that is derived from its name.</summary>
    private const string NameIdentityPrefix = "name:";

    /// <summary>
    /// The prefix of the identity that releases through 1.28.0 gave the sessions of an agent resolved from a
    /// keyed registration that was not also the default agent.
    /// </summary>
    private const string LegacyKeyIdentityPrefix = "key:";

    internal FoundryHostingAgent(AIAgent innerAgent, string sessionStorageIdentity)
        : base(innerAgent)
    {
        this.SessionStorageIdentity = Throw.IfNullOrWhitespace(sessionStorageIdentity);
    }

    internal string SessionStorageIdentity { get; }

    /// <summary>
    /// Gets the session storage identity carried by a hosting wrapper, or derives one for direct use.
    /// </summary>
    /// <param name="agent">The agent whose storage identity is required.</param>
    /// <param name="allowInstanceId">
    /// Whether an unnamed direct agent may use its process-local <see cref="AIAgent.Id"/>.
    /// </param>
    /// <returns>The resolved session storage identity.</returns>
    internal static string GetSessionStorageIdentity(AIAgent agent, bool allowInstanceId = false)
    {
        _ = Throw.IfNull(agent);

        if (agent.GetService<FoundryHostingAgent>() is { } hostingAgent)
        {
            return hostingAgent.SessionStorageIdentity;
        }

        if (!string.IsNullOrWhiteSpace(agent.Name))
        {
            return NameIdentityPrefix + agent.Name;
        }

        if (allowInstanceId)
        {
            return $"id:{agent.Id}";
        }

        throw new InvalidOperationException(
            $"Persistent session storage requires a stable {nameof(AIAgent.Name)} or Foundry hosting registration.");
    }

    /// <summary>
    /// Resolves the stable identity used to partition session storage for the resolved agent.
    /// </summary>
    /// <remarks>
    /// A keyed registration normally uses <c>key:{registrationKey}</c>. When keyed resolution
    /// returns the same agent instance as the default registration, reference equality treats both
    /// registrations as aliases and uses the default identity. This ensures named and unnamed
    /// requests for the same agent share session state. The default identity uses
    /// <c>name:{agent.Name}</c> when the agent has a name, or <c>default</c> otherwise.
    /// </remarks>
    /// <param name="agent">The agent resolved for the current request.</param>
    /// <param name="registrationKey">The keyed registration requested by the caller, if any.</param>
    /// <param name="defaultAgent">The agent registered as the default, if any.</param>
    /// <returns>The stable session storage identity.</returns>
    internal static string ResolveSessionStorageIdentity(
        AIAgent agent,
        string? registrationKey,
        AIAgent? defaultAgent)
    {
        _ = Throw.IfNull(agent);

        if (registrationKey is not null && !ReferenceEquals(agent, defaultAgent))
        {
            return LegacyKeyIdentityPrefix + registrationKey;
        }

        return !string.IsNullOrWhiteSpace(agent.Name)
            ? NameIdentityPrefix + agent.Name
            : "default";
    }

    /// <summary>
    /// Gets the identity under which releases through 1.28.0 may have saved the sessions of the agent that
    /// now uses <paramref name="sessionStorageIdentity"/>, so they can still be read.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Those releases saved the sessions of an agent resolved from a keyed registration that was not also the
    /// default agent under <c>key:{registrationKey}</c>, for example the second agent a container registered
    /// with <c>AddFoundryResponses(agent)</c>. The only such sessions this can recover are those of an agent
    /// registered under its own name, so the legacy identity is derived from the current
    /// <c>name:{agent.Name}</c> identity and never from anything a request carries. Other identities,
    /// including <c>default</c> for an unnamed agent, have no legacy counterpart.
    /// </para>
    /// <para>
    /// Only the agent component of a storage key is replaced. The session id and every partition, including
    /// the user partition, are kept, so the legacy identity cannot reach another user's or another
    /// conversation's session.
    /// </para>
    /// </remarks>
    /// <param name="sessionStorageIdentity">The identity the agent's sessions are saved under now.</param>
    /// <returns>The legacy identity, or <see langword="null"/> when there is none.</returns>
    internal static string? GetLegacySessionStorageIdentity(string sessionStorageIdentity)
    {
        _ = Throw.IfNull(sessionStorageIdentity);

        return sessionStorageIdentity.StartsWith(NameIdentityPrefix, StringComparison.Ordinal)
            ? string.Concat(LegacyKeyIdentityPrefix, sessionStorageIdentity.AsSpan(NameIdentityPrefix.Length))
            : null;
    }
}
