// Copyright (c) Microsoft. All rights reserved.
using Azure.AI.OpenAI;

namespace Microsoft.Extensions.AI.Agents.AzureAI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="ChatClientAgent"/> using a <see cref="AzureOpenAIClient"/>.
/// </summary>
public sealed class AzureOpenAIAgentFactory : AgentFactory
{
    /// <summary>
    /// The type of the chat client agent.
    /// </summary>
    public const string AzureOpenAIAgentType = "azureopenai_agent";

    /// <summary>
    /// Initializes a new instance of the <see cref="AzureOpenAIAgentFactory"/> class.
    /// </summary>
    public AzureOpenAIAgentFactory()
        : base([AzureOpenAIAgentType])
    {
    }

    /// <inheritdoc/>
    public override Task<AIAgent?> TryCreateAsync(AgentDefinition agentDefinition, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        //Throw.IfNull(agentDefinition);

        ChatClientAgent? agent = null;
        if (this.IsSupported(agentDefinition))
        {
            IChatClient? chatClient = null;

            var client = agentCreationOptions.ServiceProvider?.GetService(typeof(AzureOpenAIClient)) as AzureOpenAIClient;
            if (client is not null)
            {
                //agentDefinition.Model.Connection?.Options
                //chatClient = client.GetChatClient(deploymentName).AsIChatClient();
            }

            if (chatClient is not null)
            {
                agent = new ChatClientAgent(chatClient, new ChatClientAgentOptions(), agentCreationOptions.LoggerFactory);
            }
        }

        return Task.FromResult<AIAgent?>(agent);
    }
}
