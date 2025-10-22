// Copyright (c) Microsoft. All rights reserved.
using System;
using System.ClientModel;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.AI.OpenAI;
using Azure.Core;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.PowerFx;
using Microsoft.Shared.Diagnostics;
using OpenAI;
using OpenAI.Assistants;
using OpenAI.Chat;
using OpenAI.Responses;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="AIAgent"/> using a Azure AI.
/// </summary>
public sealed class OpenAIAgentFactory : AgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIAgentFactory"/> class.
    /// </summary>
    public OpenAIAgentFactory()
    {
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIAgentFactory"/> class.
    /// </summary>
    public OpenAIAgentFactory(ChatClient chatClient)
    {
        Throw.IfNull(chatClient);

        this._chatClient = chatClient;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIAgentFactory"/> class.
    /// </summary>
    public OpenAIAgentFactory(AssistantClient assistantClient)
    {
        Throw.IfNull(assistantClient);

        this._assistantClient = assistantClient;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIAgentFactory"/> class.
    /// </summary>
    public OpenAIAgentFactory(OpenAIResponseClient responseClient)
    {
        Throw.IfNull(responseClient);

        this._responseClient = responseClient;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIAgentFactory"/> class.
    /// </summary>
    public OpenAIAgentFactory(Uri endpoint, TokenCredential tokenCredential)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(tokenCredential);

        this._endpoint = endpoint;
        this._tokenCredential = tokenCredential;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIAgentFactory"/> class.
    /// </summary>
    public OpenAIAgentFactory(IServiceProvider serviceProvider)
    {
        Throw.IfNull(serviceProvider);

        this._serviceProvider = serviceProvider;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, AgentCreationOptions? agentCreationOptions = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var options = new ChatClientAgentOptions()
        {
            Name = promptAgent.Name,
            Description = promptAgent.Description,
            Instructions = promptAgent.Instructions?.ToTemplateString(),
            ChatOptions = promptAgent.GetChatOptions(agentCreationOptions),
        };

        var openaiAgentOptions = agentCreationOptions as OpenAIAgentCreationOptions;
        var serviceProvider = agentCreationOptions?.ServiceProvider ?? this._serviceProvider;
        ILoggerFactory? loggerFactory = serviceProvider?.GetService(typeof(ILoggerFactory)) as ILoggerFactory;

        ChatClient? chatClient = this.GetChatClient(promptAgent, options, openaiAgentOptions, serviceProvider, loggerFactory);
        if (chatClient is not null)
        {
            return new ChatClientAgent(
                chatClient.AsIChatClient(),
                options,
                loggerFactory);
        }

        var assistantClient = this.GetAssistantClient(promptAgent, openaiAgentOptions, serviceProvider);
        if (assistantClient is not null)
        {
            Throw.IfNullOrEmpty(promptAgent.Model?.Id, "The model id must be specified in the agent definition to create an OpenAI Assistant.");
            Throw.IfNullOrEmpty(promptAgent.Instructions?.ToTemplateString(), "The instructions must be specified in the agent definition to create an OpenAI Assistant.");

            return await assistantClient.CreateAIAgentAsync(
                promptAgent.Model!.Id,
                options
            ).ConfigureAwait(false);
        }

        var responseClient = this.GetResponseClient(promptAgent, openaiAgentOptions, serviceProvider);
        if (responseClient is not null)
        {
            return new ChatClientAgent(
                responseClient.AsIChatClient(),
                options,
                loggerFactory);
        }

        return null;
    }

    #region private
    private const string PUBLISHER_OPENAI = "OPENAI";
    private const string PUBLISHER_AZURE = "AZURE";

    private const string API_TYPE_CHAT = "CHAT";
    private const string API_TYPE_ASSISTANTS = "ASSISTANTS";
    private const string API_TYPE_RESPONSES = "RESPONSES";

    private readonly ChatClient? _chatClient;
    private readonly AssistantClient? _assistantClient;
    private readonly OpenAIResponseClient? _responseClient;
    private readonly Uri? _endpoint;
    private readonly TokenCredential? _tokenCredential;
    private readonly IServiceProvider? _serviceProvider;

    private ChatClient? GetChatClient(PromptAgent promptAgent, ChatClientAgentOptions options, OpenAIAgentCreationOptions? openaiAgentOptions, IServiceProvider? serviceProvider, ILoggerFactory? loggerFactory)
    {
        var chatClient = openaiAgentOptions?.ChatClient ?? this._chatClient;

        if (chatClient is null && serviceProvider is not null)
        {
            string? serviceKey = promptAgent.GenerateServiceKey();
            if (!string.IsNullOrEmpty(serviceKey))
            {
                chatClient = serviceProvider.GetKeyedService<ChatClient>(serviceKey);
            }
            chatClient ??= serviceProvider.GetService<ChatClient>();
        }

        if (chatClient is null && promptAgent.Model?.GetApiType()?.Equals(API_TYPE_CHAT, StringComparison.OrdinalIgnoreCase) == true)
        {
            var publisher = promptAgent.Model?.Publisher ?? PUBLISHER_OPENAI;
            if (publisher.Equals(PUBLISHER_OPENAI, StringComparison.OrdinalIgnoreCase))
            {
                chatClient = CreateOpenAIChatClient(promptAgent);
            }
            else if (publisher.Equals(PUBLISHER_AZURE, StringComparison.OrdinalIgnoreCase))
            {
                var tokenCredential = this._tokenCredential ?? serviceProvider?.GetService(typeof(TokenCredential)) as TokenCredential;
                Throw.IfNull(this._endpoint, "The connection endpoint must be specified to create an Azure OpenAI client.");
                Throw.IfNull(tokenCredential, "A token credential must be specified to create an Azure OpenAI client");
                chatClient = CreateAzureOpenAIChatClient(promptAgent, this._endpoint, tokenCredential);
            }
        }

        return chatClient;
    }

    private AssistantClient? GetAssistantClient(PromptAgent promptAgent, OpenAIAgentCreationOptions? openaiAgentOptions, IServiceProvider? serviceProvider)
    {
        var assistantClient = openaiAgentOptions?.AssistantClient ?? this._assistantClient;

        if (assistantClient is null && serviceProvider is not null)
        {
            string? serviceKey = promptAgent.GenerateServiceKey();
            if (!string.IsNullOrEmpty(serviceKey))
            {
                assistantClient = serviceProvider.GetKeyedService<AssistantClient>(serviceKey);
            }
            assistantClient ??= serviceProvider.GetService<AssistantClient>();
        }

        if (assistantClient is null && promptAgent.Model?.GetApiType()?.Equals(API_TYPE_ASSISTANTS, StringComparison.OrdinalIgnoreCase) == true)
        {
            var publisher = promptAgent.Model?.Publisher ?? PUBLISHER_OPENAI;
            if (publisher.Equals(PUBLISHER_OPENAI, StringComparison.OrdinalIgnoreCase))
            {
                assistantClient = CreateOpenAIAssistantClient(promptAgent);
            }
            else if (publisher.Equals(PUBLISHER_AZURE, StringComparison.OrdinalIgnoreCase))
            {
                var tokenCredential = this._tokenCredential ?? serviceProvider?.GetService(typeof(TokenCredential)) as TokenCredential;
                Throw.IfNull(this._endpoint, "The connection endpoint must be specified to create an Azure OpenAI client.");
                Throw.IfNull(tokenCredential, "A token credential must be specified to create an Azure OpenAI client");
                assistantClient = CreateAzureOpenAIAssistantClient(promptAgent, this._endpoint, tokenCredential);
            }
        }

        return assistantClient;
    }

    private OpenAIResponseClient? GetResponseClient(PromptAgent promptAgent, OpenAIAgentCreationOptions? openaiAgentOptions, IServiceProvider? serviceProvider)
    {
        var responseClient = openaiAgentOptions?.ResponseClient ?? this._responseClient;

        if (responseClient is null && serviceProvider is not null)
        {
            string? serviceKey = promptAgent.GenerateServiceKey();
            if (!string.IsNullOrEmpty(serviceKey))
            {
                responseClient = serviceProvider.GetKeyedService<OpenAIResponseClient>(serviceKey);
            }
            responseClient ??= serviceProvider.GetService<OpenAIResponseClient>();
        }

        if (responseClient is null && promptAgent.Model?.GetApiType()?.Equals(API_TYPE_RESPONSES, StringComparison.OrdinalIgnoreCase) == true)
        {
            var publisher = promptAgent.Model?.Publisher ?? PUBLISHER_OPENAI;
            if (publisher.Equals(PUBLISHER_OPENAI, StringComparison.OrdinalIgnoreCase))
            {
                responseClient = CreateOpenAIResponseClient(promptAgent);
            }
            else if (publisher.Equals(PUBLISHER_AZURE, StringComparison.OrdinalIgnoreCase))
            {
                var tokenCredential = this._tokenCredential ?? serviceProvider?.GetService(typeof(TokenCredential)) as TokenCredential;
                Throw.IfNull(this._endpoint, "The connection endpoint must be specified to create an Azure OpenAI client.");
                Throw.IfNull(tokenCredential, "A token credential must be specified to create an Azure OpenAI client");
                responseClient = CreateAzureOpenAIResponseClient(promptAgent, this._endpoint, tokenCredential);
            }
        }

        return responseClient;
    }

    private static ChatClient CreateOpenAIChatClient(PromptAgent promptAgent)
    {
        var modelId = promptAgent.Model?.Id;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        return CreateOpenAIClient(promptAgent).GetChatClient(modelId);
    }

    private static ChatClient CreateAzureOpenAIChatClient(PromptAgent promptAgent, Uri endpoint, TokenCredential tokenCredential)
    {
        var deploymentName = promptAgent.Model?.Id;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        return new AzureOpenAIClient(endpoint, tokenCredential).GetChatClient(deploymentName);
    }

    private static AssistantClient CreateOpenAIAssistantClient(PromptAgent promptAgent)
    {
        var modelId = promptAgent.Model?.Id;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        return CreateOpenAIClient(promptAgent).GetAssistantClient();
    }

    private static AssistantClient CreateAzureOpenAIAssistantClient(PromptAgent promptAgent, Uri endpoint, TokenCredential tokenCredential)
    {
        var deploymentName = promptAgent.Model?.Id;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        return new AzureOpenAIClient(endpoint, tokenCredential).GetAssistantClient();
    }

    private static OpenAIResponseClient CreateOpenAIResponseClient(PromptAgent promptAgent)
    {
        var modelId = promptAgent.Model?.Id;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        return CreateOpenAIClient(promptAgent).GetOpenAIResponseClient(modelId);
    }

    private static OpenAIResponseClient CreateAzureOpenAIResponseClient(PromptAgent promptAgent, Uri endpoint, TokenCredential tokenCredential)
    {
        var deploymentName = promptAgent.Model?.Id;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        return new AzureOpenAIClient(endpoint, tokenCredential).GetOpenAIResponseClient(deploymentName);
    }

    private static OpenAIClient CreateOpenAIClient(PromptAgent promptAgent)
    {
        var keyConnection = promptAgent.Model?.Connection as KeyConnection;
        Throw.IfNull(keyConnection, "A key connection must be specified when create an OpenAI client");

        var apiKey = keyConnection.Key?.LiteralValue;
        Throw.IfNullOrEmpty(apiKey, "The connection key must be specified in the agent definition to create an OpenAI client.");

        var clientOptions = new OpenAIClientOptions();
        var endpoint = keyConnection.Endpoint?.LiteralValue;
        if (!string.IsNullOrEmpty(endpoint))
        {
            clientOptions.Endpoint = new Uri(endpoint);
        }

        return new OpenAIClient(new ApiKeyCredential(apiKey), clientOptions);
    }
    #endregion
}
