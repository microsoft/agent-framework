// Copyright (c) Microsoft. All rights reserved.
using Azure.AI.OpenAI;
using Azure.Core;
using Microsoft.Agents.Declarative;

namespace Microsoft.Extensions.AI.Agents.AzureAI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="ChatClientAgent"/> using a <see cref="AzureOpenAIClient"/>.
/// </summary>
public sealed class AzureOpenAIAgentFactory : AgentFactory
{
    /// <summary>
    /// The type of the chat client agent.
    /// </summary>
    public const string AzureOpenAIAgentType = "azure_openai_agent";

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

            var deploymentName = agentDefinition.Model.Connection?.Options?["deployment_name"] as string;
            if (string.IsNullOrEmpty(deploymentName))
            {
                throw new InvalidOperationException("The deployment_name must be specified in the agent definition model connection options to create a ChatClient.");
            }

            var client = agentCreationOptions.ServiceProvider?.GetService(typeof(AzureOpenAIClient)) as AzureOpenAIClient;
            if (client is not null)
            {
                chatClient = client.GetChatClient(deploymentName).AsIChatClient();
            }
            else
            {
                var endpoint = agentDefinition.Model.Connection?.Endpoint;
                if (string.IsNullOrEmpty(endpoint))
                {
                    throw new InvalidOperationException("The endpoint must be specified in the agent definition model connection to create an AzureOpenAIClient.");
                }

                if (agentCreationOptions.ServiceProvider?.GetService(typeof(TokenCredential)) is not TokenCredential credential)
                {
                    throw new InvalidOperationException("A TokenCredential must be registered in the service provider to create an AzureOpenAIClient.");
                }

                chatClient = new AzureOpenAIClient(
                    new Uri(endpoint),
                    credential)
                     .GetChatClient(deploymentName)
                     .AsIChatClient();
            }

            agent = new ChatClientAgent(chatClient, new ChatClientAgentOptions(), agentCreationOptions.LoggerFactory);
        }

        return Task.FromResult<AIAgent?>(agent);
    }
}
