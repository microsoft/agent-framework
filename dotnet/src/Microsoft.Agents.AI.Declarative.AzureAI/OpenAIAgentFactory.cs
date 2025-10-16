// Copyright (c) Microsoft. All rights reserved.
using System;
using System.ClientModel;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Core;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using OpenAI;
using OpenAI.Assistants;
using OpenAI.Chat;
using OpenAI.Responses;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="ChatClientAgent"/> using a Azure AI.
/// </summary>
public sealed class OpenAIAgentFactory : AgentFactory
{
    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        ChatClientAgent? agent = null;
        if (this.IsSupported(promptAgent))
        {
            var options = new ChatClientAgentOptions()
            {
                Name = promptAgent.Name,
                Description = promptAgent.Description,
                Instructions = promptAgent.Instructions?.ToTemplateString(),
                ChatOptions = promptAgent.GetChatOptions(agentCreationOptions),
            };

            var chatClient = agentCreationOptions.ServiceProvider?.GetService(typeof(ChatClient)) as ChatClient;
            var assistantClient = agentCreationOptions.ServiceProvider?.GetService(typeof(AssistantClient)) as AssistantClient;
            var responseClient = agentCreationOptions.ServiceProvider?.GetService(typeof(OpenAIResponseClient)) as OpenAIResponseClient;
            var modelId = promptAgent.Model?.Id;
            var publisher = promptAgent.Model?.Publisher ?? PUBLISHER_OPENAI;
            if (chatClient is not null)
            {
                agent = new ChatClientAgent(
                    chatClient.AsIChatClient(),
                    options,
                    agentCreationOptions.LoggerFactory);
            }
            else if (assistantClient is not null)
            {
                Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI Assistant.");
                var instructions = promptAgent.Instructions?.ToTemplateString();
                Throw.IfNullOrEmpty(instructions, "The instructions must be specified in the agent definition to create an OpenAI Assistant.");

                agent = await assistantClient.CreateAIAgentAsync(
                    model: modelId,
                    name: promptAgent.Name,
                    instructions: instructions,
                    tools: options.ChatOptions?.Tools
                ).ConfigureAwait(false);
            }
            else if (responseClient is not null)
            {
                agent = new ChatClientAgent(
                    responseClient.AsIChatClient(),
                    options,
                    agentCreationOptions.LoggerFactory);
            }
            else if (publisher.Equals(PUBLISHER_OPENAI, StringComparison.OrdinalIgnoreCase))
            {
                agent = CreateOpenAIAgent(promptAgent, agentCreationOptions, options);
            }
            else if (publisher.Equals(PUBLISHER_AZURE, StringComparison.OrdinalIgnoreCase))
            {
                agent = CreateAzureOpenAIAgent(promptAgent, agentCreationOptions, options);
            }
        }

        return agent;
    }

    #region private
    private const string PUBLISHER_OPENAI = "OPENAI";
    private const string PUBLISHER_AZURE = "AZURE";

    private static ChatClientAgent CreateOpenAIAgent(PromptAgent promptAgent, AgentCreationOptions agentCreationOptions, ChatClientAgentOptions agentOptions)
    {
        var modelId = promptAgent.Model?.Id;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        var keyConnection = promptAgent.Model?.Connection as KeyConnection;
        Throw.IfNull(keyConnection, "A key connection must be specified when create an OpenAI agent");

        var apiKey = keyConnection.Key?.LiteralValue;
        Throw.IfNullOrEmpty(apiKey, "The connection key must be specified in the agent definition to create an OpenAI agent.");

        var clientOptions = new OpenAIClientOptions();
        var endpoint = keyConnection.Endpoint?.LiteralValue;
        if (!string.IsNullOrEmpty(endpoint))
        {
            clientOptions.Endpoint = new Uri(endpoint);
        }

        // TODO: Support different API types (Chat, Assistants, Responses, etc).

        return new ChatClientAgent(
            new OpenAIClient(new ApiKeyCredential(apiKey), clientOptions).GetChatClient(modelId).AsIChatClient(),
            agentOptions,
            agentCreationOptions.LoggerFactory);
    }

    private static ChatClientAgent CreateAzureOpenAIAgent(PromptAgent promptAgent, AgentCreationOptions agentCreationOptions, ChatClientAgentOptions agentOptions)
    {
        var deploymentName = promptAgent.Model?.Id;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        var keyConnection = promptAgent.Model?.Connection as KeyConnection;
        Throw.IfNull(keyConnection, "A key connection must be specified when create an Azure OpenAI agent");

        var endpoint = keyConnection.Endpoint?.LiteralValue;
        Throw.IfNullOrEmpty(endpoint, "The connection endpoint must be specified in the agent definition to create an Azure OpenAI agent.");

        if (agentCreationOptions.ServiceProvider?.GetService(typeof(TokenCredential)) is not TokenCredential tokenCredential)
        {
            throw new InvalidOperationException("A TokenCredential must be registered in the service provider to create an PersistentAgentsClient.");
        }

        // TODO: Support different API types (Chat, Assistants, Responses, etc).

        return new ChatClientAgent(
            new AzureOpenAIClient(new Uri(endpoint), tokenCredential).GetChatClient(deploymentName).AsIChatClient(),
            agentOptions,
            agentCreationOptions.LoggerFactory);
    }
    #endregion
}
