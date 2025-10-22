// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Parameters for agent creation used when create an <see cref="AIAgent"/>
/// using an instance of <see cref="AIFoundryAgentFactory"/>.
/// </summary>
public sealed class AIFoundryAgentCreationOptions : AgentCreationOptions
{
    /// <summary>
    /// Gets or sets the <see cref="PersistentAgentsClient"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public PersistentAgentsClient? PersistentAgentsClient { get; set; }

    /// <summary>
    /// Gets or sets the <see cref="TokenCredential"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public TokenCredential? TokenCredential { get; set; }

    /// <summary>
    /// Gets or sets the collection of <see cref="AITool"/> instances to register with the <see cref="AIAgent"/>.
    /// </summary>
    public IList<AITool>? Tools { get; set; }
}
