// Copyright (c) Microsoft. All rights reserved.
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="ChatClientAgent"/> using a Azure AI.
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
    public override Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        //Throw.IfNull(promptAgent);

        ChatClientAgent? agent = null;
        if (this.IsSupported(promptAgent))
        {
            /*
            var chatClient = agentCreationOptions.ServiceProvider?.GetService(typeof(ChatClient)) as OpenAI.Chat.ChatClient;
            var assistantClient = agentCreationOptions.ServiceProvider?.GetService(typeof(AssistantClient)) as AssistantClient;
            var responseClient = agentCreationOptions.ServiceProvider?.GetService(typeof(OpenAIResponseClient)) as OpenAIResponseClient;
            if (chatClient is not null)
            {
                agent = new ChatClientAgent(
                    chatClient.AsIChatClient(),
                    new ChatClientAgentOptions(),
                    agentCreationOptions.LoggerFactory);
            }
            else if (assistantClient is not null)
            {
                agent = assistantClient.CreateAIAgentAsync();
            }
            else if (responseClient is not null)
            {
                agent = new ChatClientAgent(
                    responseClient.AsIChatClient(),
                    new ChatClientAgentOptions(),
                    agentCreationOptions.LoggerFactory);
            }
            else
            {
                var deploymentName = promptAgent.Model?.Connection?.GetDeploymentName();
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
                    var endpoint = promptAgent.Model?.Connection?.GetEndpoint();
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
            }
            */
        }

        return Task.FromResult<AIAgent?>(agent);
    }
}
