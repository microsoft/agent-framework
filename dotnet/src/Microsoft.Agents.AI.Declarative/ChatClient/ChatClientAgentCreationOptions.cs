// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Parameters for agent creation used when create an <see cref="AIAgent"/>
/// using an instance of <see cref="ChatClientAgentFactory"/>.
/// </summary>
public sealed class ChatClientAgentCreationOptions : AgentCreationOptions
{
    /// <summary>
    /// Gets or sets the <see cref="IChatClient"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public IChatClient? ChatClient { get; set; }

    /// <summary>
    /// Gets or sets the collection of <see cref="AITool"/> instances to register with the <see cref="AIAgent"/>.
    /// </summary>
    public IList<AITool>? Tools { get; set; }
}
