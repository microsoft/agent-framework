// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Declarative;

internal static class AgentDefinitionExtensions
{
    internal static ChatClientAgentOptions ToChatClientAgentOptions(this AgentDefinition agentDefinition)
    {
        if (agentDefinition is null)
        {
            throw new ArgumentNullException(nameof(agentDefinition));
        }
        return new ChatClientAgentOptions
        {
            Name = agentDefinition.Name,
            Description = agentDefinition.Description,
            Instructions = agentDefinition.Instructions,
            ChatOptions = agentDefinition.ToChatOptions(),
        };
    }

    internal static ChatOptions ToChatOptions(this AgentDefinition agentDefinition)
    {
        if (agentDefinition is null)
        {
            throw new ArgumentNullException(nameof(agentDefinition));
        }
        return new ChatOptions
        {
            // TODO: Map other properties as needed
        };
    }
}
