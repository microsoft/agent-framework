// Copyright (c) Microsoft. All rights reserved.

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
    internal FoundryHostingAgent(AIAgent innerAgent, string sessionStorageIdentity)
        : base(innerAgent)
    {
        this.SessionStorageIdentity = Throw.IfNullOrWhitespace(sessionStorageIdentity);
    }

    internal string SessionStorageIdentity { get; }

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
            return $"key:{registrationKey}";
        }

        return !string.IsNullOrWhiteSpace(agent.Name)
            ? $"name:{agent.Name}"
            : "default";
    }
}
