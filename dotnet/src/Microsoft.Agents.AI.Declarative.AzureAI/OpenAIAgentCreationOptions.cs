// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using OpenAI.Assistants;
using OpenAI.Chat;
using OpenAI.Responses;

namespace Microsoft.Agents.AI;

/// <summary>
/// Parameters for agent creation used when create an <see cref="AIAgent"/>
/// using an instance of <see cref="OpenAIAgentFactory"/>.
/// </summary>
public sealed class OpenAIAgentCreationOptions : AgentCreationOptions
{
    /// <summary>
    /// Gets or sets the <see cref="ChatClient"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public ChatClient? ChatClient { get; set; }

    /// <summary>
    /// Gets or sets the <see cref="AssistantClient"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public AssistantClient? AssistantClient { get; set; }

    /// <summary>
    /// Gets or sets the <see cref="OpenAIResponseClient"/> instance to use when creating the <see cref="AIAgent"/>.
    /// </summary>
    public OpenAIResponseClient? ResponseClient { get; set; }

    /// <summary>
    /// Gets or sets the collection of <see cref="AITool"/> instances to register with the <see cref="AIAgent"/>.
    /// </summary>
    public IList<AITool>? Tools { get; set; }
}
