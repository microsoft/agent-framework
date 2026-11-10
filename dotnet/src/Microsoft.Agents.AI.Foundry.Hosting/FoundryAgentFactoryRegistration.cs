// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Records an agent registered through the factory overload of <c>AddFoundryResponses</c>.
/// </summary>
/// <remarks>
/// <para>
/// The factory overload registers the agent and its session store only under the agent name. It does not
/// add a non-keyed registration that forwards to the keyed one, because Microsoft DI records the object a
/// factory returns for disposal once per registration: a forwarding registration would dispose the same
/// object twice, and its lifetime could disagree with the keyed registration it forwards to. Instead, when
/// no default agent existed at registration time, this marker records that requests without an agent name
/// are routed to this agent by the response handler.
/// </para>
/// <para>
/// The markers also fix where sessions are stored. The response handler normally decides that by checking
/// whether the keyed agent and the default agent are the same object, which depends on the lifetime for a
/// factory: a transient registration creates a new object on every lookup. The marker uses the location
/// <c>AddFoundryResponses(agent)</c> would use for an agent with the same name in the same position:
/// <c>name:{agentName}</c> for the default agent and <c>key:{agentName}</c> for any other agent.
/// </para>
/// </remarks>
internal sealed class FoundryAgentFactoryRegistration
{
    public FoundryAgentFactoryRegistration(string agentName, bool isDefault)
    {
        this.AgentName = Throw.IfNullOrWhitespace(agentName);
        this.IsDefault = isDefault;
    }

    /// <summary>Gets the key the agent was registered under.</summary>
    public string AgentName { get; }

    /// <summary>
    /// Gets a value indicating whether no default agent existed when this agent was registered, so requests
    /// without an agent name may be routed to it.
    /// </summary>
    public bool IsDefault { get; }
}

/// <summary>
/// Lookup of <see cref="FoundryAgentFactoryRegistration"/> markers built once by the response handler.
/// </summary>
internal sealed class FoundryAgentFactoryRegistrations
{
    private readonly Dictionary<string, string> _storageIdentities = new(StringComparer.Ordinal);

    /// <summary>
    /// Initializes a new instance of the <see cref="FoundryAgentFactoryRegistrations"/> class.
    /// </summary>
    /// <param name="registrations">The markers registered by the factory overloads.</param>
    /// <param name="nonKeyedAgentRegistered">
    /// Whether the built container has a non-keyed <see cref="AIAgent"/> registration, or <see langword="null"/>
    /// when the container cannot report it. A non-keyed agent registered after a factory overload receives
    /// requests without an agent name, so no factory registration is then treated as the default. When the
    /// container cannot report it, the decision made at registration time is used.
    /// </param>
    public FoundryAgentFactoryRegistrations(
        IEnumerable<FoundryAgentFactoryRegistration> registrations,
        bool? nonKeyedAgentRegistered = null)
    {
        foreach (FoundryAgentFactoryRegistration registration in registrations)
        {
            bool isEffectiveDefault = registration.IsDefault
                && nonKeyedAgentRegistered is not true
                && this.DefaultAgentName is null;
            string storageIdentity = isEffectiveDefault
                ? $"name:{registration.AgentName}"
                : $"key:{registration.AgentName}";
            this._storageIdentities[registration.AgentName] = storageIdentity;
            if (isEffectiveDefault)
            {
                this.DefaultAgentName = registration.AgentName;
                this.DefaultStorageIdentity = storageIdentity;
            }
        }
    }

    /// <summary>
    /// Gets the name of the factory registration that receives requests without an agent name, or
    /// <see langword="null"/> when no factory registration was the default.
    /// </summary>
    public string? DefaultAgentName { get; }

    /// <summary>Gets the storage identity of <see cref="DefaultAgentName"/>.</summary>
    public string? DefaultStorageIdentity { get; }

    /// <summary>Gets the storage identity for a keyed factory registration.</summary>
    public bool TryGetStorageIdentity(string agentName, [NotNullWhen(true)] out string? storageIdentity)
        => this._storageIdentities.TryGetValue(agentName, out storageIdentity);
}
