// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

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
    public override Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        ChatClientAgent? agent = null;
        if (this.IsSupported(promptAgent))
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

            var options = new ChatClientAgentOptions()
            {
                Name = promptAgent.Name,
                Description = promptAgent.Description,
                Instructions = promptAgent.Instructions?.ToTemplateString(),
                ChatOptions = promptAgent.GetChatOptions(),
            };

            agent = new ChatClientAgent(chatClient, options, agentCreationOptions.LoggerFactory);
        }

        return Task.FromResult<AIAgent?>(agent);
    }
}
