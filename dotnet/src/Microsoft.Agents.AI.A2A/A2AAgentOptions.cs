// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Represents configuration options for an <see cref="A2AAgent"/>, including its identifier, name, and description.
/// </summary>
/// <remarks>
/// <para>
/// This class is used to encapsulate information about an A2A agent, such as its unique
/// identifier, display name, and a descriptive summary.
/// </para>
/// <para>
/// When an agent is created from an <see cref="global::A2A.AgentCard"/> that may come from an untrusted source
/// (for example a public registry, a user-supplied address, or any card fetched over the network), setting
/// <see cref="AgentCardAllowedHosts"/> is recommended. Without it, the card alone decides which host receives
/// requests, including any credentials attached to the supplied <see cref="System.Net.Http.HttpClient"/>.
/// </para>
/// </remarks>
public sealed class A2AAgentOptions
{
    /// <summary>
    /// Gets or sets the agent id.
    /// </summary>
    public string? Id { get; set; }

    /// <summary>
    /// Gets or sets the agent name.
    /// </summary>
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets the agent description.
    /// </summary>
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets the host names that an agent card is allowed to direct requests to.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This setting applies when an agent is created from an <see cref="global::A2A.AgentCard"/>. The addresses listed
    /// in a card decide where requests are sent, including any credentials attached to the supplied
    /// <see cref="System.Net.Http.HttpClient"/>. Set this list whenever the source of the card is less trusted than
    /// those credentials. Setting it is recommended whenever the card may come from an untrusted source.
    /// </para>
    /// <para>
    /// Each entry is a host name or IP address, with an optional port (for example <c>contoso.com</c>,
    /// <c>contoso.com:8443</c> or <c>[::1]:8443</c>). An entry without a port allows any port on that host; an entry
    /// with a port allows only that port. Host names are compared ignoring case. Schemes, paths and wildcards are
    /// not supported, and an entry that is not valid causes an <see cref="System.ArgumentException"/> when the agent
    /// is created.
    /// </para>
    /// <para>
    /// When <see langword="null"/> (the default), any host is allowed. An empty list allows no hosts, so every
    /// agent card is rejected.
    /// </para>
    /// </remarks>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public IList<string>? AgentCardAllowedHosts { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether an agent card is allowed to direct requests to
    /// addresses that use plain <c>http</c>.
    /// </summary>
    /// <remarks>
    /// The default is <see langword="false"/>, which accepts only <c>https</c> addresses. Plain <c>http</c> sends
    /// requests and credentials unencrypted, so enable it only for local development or trusted networks.
    /// </remarks>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public bool AllowAgentCardHostsInsecureHttp { get; set; }

    /// <summary>
    /// Creates a new instance of <see cref="A2AAgentOptions"/> with the same values as this instance.
    /// </summary>
    public A2AAgentOptions Clone()
        => new()
        {
            Id = this.Id,
            Name = this.Name,
            Description = this.Description,
            AgentCardAllowedHosts = this.AgentCardAllowedHosts is null ? null : [.. this.AgentCardAllowedHosts],
            AllowAgentCardHostsInsecureHttp = this.AllowAgentCardHostsInsecureHttp
        };
}
