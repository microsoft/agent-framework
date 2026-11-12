// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// The name of the agent registered through the factory overload of <c>AddFoundryResponses</c> that answers
/// requests without a matching agent name.
/// </summary>
/// <remarks>
/// <para>
/// The factory overload registers its agent only under the agent name. It does not add a non-keyed
/// registration that forwards to the keyed one, because Microsoft DI disposes the object a factory returns
/// once per registration that created or returned it, so a forwarding registration would dispose the same
/// object twice. This value is registered instead, only when no default agent existed at registration time,
/// so the response handler can route requests without an agent name to that agent.
/// </para>
/// <para>
/// The response handler ignores it when an <see cref="AIAgent"/> is registered without a key, because that
/// agent receives requests without an agent name. Sessions of the agent named here are stored in the location
/// <c>AddFoundryResponses(agent)</c> uses for the default agent, <c>name:{Name}</c>, whatever its lifetime.
/// </para>
/// </remarks>
internal sealed class FoundryDefaultAgentName
{
    public FoundryDefaultAgentName(string name)
    {
        this.Name = Throw.IfNullOrWhitespace(name);
    }

    /// <summary>Gets the key the default factory agent is registered under.</summary>
    public string Name { get; }
}
