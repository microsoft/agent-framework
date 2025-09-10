// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Declarative;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="ChatClientAgent"/>.
/// </summary>
public sealed class ChatClientAgentFactory : AgentFactory
{
    /// <summary>
    /// The type of the chat client agent.
    /// </summary>
    public const string ChatClientAgentType = "chat_client_agent";

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentFactory"/> class.
    /// </summary>
    public ChatClientAgentFactory()
        : base([ChatClientAgentType])
    {
    }

    /// <inheritdoc/>
    public override Task<AIAgent?> TryCreateAsync(AgentDefinition agentDefinition, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentDefinition);

        ChatClientAgent? agent = null;
        if (this.IsSupported(agentDefinition))
        {
            IChatClient? chatClient = agentCreationOptions.ChatClient;
            if (chatClient == null && agentCreationOptions.ServiceProvider != null)
            {
                chatClient = agentCreationOptions.ServiceProvider.GetService(typeof(IChatClient)) as IChatClient;
            }
            if (chatClient == null)
            {
                throw new ArgumentException("A chat client must be provided via the AgentCreationOptions.", nameof(agentCreationOptions));
            }

            agent = new ChatClientAgent(chatClient, new ChatClientAgentOptions(), agentCreationOptions.LoggerFactory);
        }

        return Task.FromResult<AIAgent?>(agent);
    }
}
