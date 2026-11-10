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
/// The response handler normally decides where sessions are stored by checking whether the keyed agent
/// and the default agent are the same object. For a factory registration that check depends on the
/// lifetime: a transient registration creates a new object on every lookup. This marker lets the
/// handler use the registration name instead, so the storage location stays the same for every lifetime
/// and matches what <c>AddFoundryResponses(agent)</c> uses for an agent with the same name.
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

    /// <summary>Gets a value indicating whether the registration also supplied the default (non-keyed) agent.</summary>
    public bool IsDefault { get; }

    /// <summary>Gets the session storage identity used for this registration.</summary>
    public string StorageIdentity => $"name:{this.AgentName}";
}

/// <summary>
/// Lookup of <see cref="FoundryAgentFactoryRegistration"/> markers built once by the response handler.
/// </summary>
internal sealed class FoundryAgentFactoryRegistrations
{
    private readonly Dictionary<string, string> _storageIdentities = new(StringComparer.Ordinal);

    public FoundryAgentFactoryRegistrations(IEnumerable<FoundryAgentFactoryRegistration> registrations)
    {
        foreach (FoundryAgentFactoryRegistration registration in registrations)
        {
            this._storageIdentities[registration.AgentName] = registration.StorageIdentity;
            if (registration.IsDefault)
            {
                this.DefaultStorageIdentity = registration.StorageIdentity;
            }
        }
    }

    /// <summary>
    /// Gets the storage identity of the factory registration that supplied the default agent, or
    /// <see langword="null"/> when the default agent was not registered through a factory overload.
    /// </summary>
    public string? DefaultStorageIdentity { get; }

    /// <summary>Gets the storage identity for a keyed factory registration.</summary>
    public bool TryGetStorageIdentity(string agentName, [NotNullWhen(true)] out string? storageIdentity)
        => this._storageIdentities.TryGetValue(agentName, out storageIdentity);
}
