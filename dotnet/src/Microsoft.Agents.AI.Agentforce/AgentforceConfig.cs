// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Agentforce;

/// <summary>
/// Configuration for connecting to a Salesforce Agentforce agent.
/// </summary>
public sealed class AgentforceConfig
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentforceConfig"/> class.
    /// </summary>
    /// <param name="myDomainHost">The Salesforce My Domain host (e.g., "your-org.my.salesforce.com").</param>
    /// <param name="consumerKey">The OAuth consumer key (client_id) from the External Client App.</param>
    /// <param name="consumerSecret">The OAuth consumer secret (client_secret) from the External Client App.</param>
    /// <param name="agentId">The Salesforce Agentforce Agent ID.</param>
    public AgentforceConfig(string myDomainHost, string consumerKey, string consumerSecret, string agentId)
    {
        this.MyDomainHost = Throw.IfNullOrWhitespace(myDomainHost);
        this.ConsumerKey = Throw.IfNullOrWhitespace(consumerKey);
        this.ConsumerSecret = Throw.IfNullOrWhitespace(consumerSecret);
        this.AgentId = Throw.IfNullOrWhitespace(agentId);
    }

    /// <summary>
    /// Gets the Salesforce My Domain host.
    /// </summary>
    /// <value>
    /// The domain host used for OAuth authentication (e.g., "your-org.my.salesforce.com").
    /// </value>
    public string MyDomainHost { get; }

    /// <summary>
    /// Gets the OAuth consumer key.
    /// </summary>
    /// <value>
    /// The consumer key (client_id) from the Salesforce External Client App configuration.
    /// </value>
    public string ConsumerKey { get; }

    /// <summary>
    /// Gets the OAuth consumer secret.
    /// </summary>
    /// <value>
    /// The consumer secret (client_secret) from the Salesforce External Client App configuration.
    /// </value>
    public string ConsumerSecret { get; }

    /// <summary>
    /// Gets the Agentforce Agent ID.
    /// </summary>
    /// <value>
    /// The identifier assigned by Salesforce to the Agentforce agent.
    /// </value>
    public string AgentId { get; }

    /// <summary>
    /// Gets the full OAuth token endpoint URL.
    /// </summary>
    internal Uri TokenEndpoint => new($"https://{this.MyDomainHost}/services/oauth2/token");

    /// <summary>
    /// Gets the full Salesforce instance endpoint URL.
    /// </summary>
    internal Uri InstanceEndpoint => new($"https://{this.MyDomainHost}");
}
