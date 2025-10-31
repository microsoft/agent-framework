// Copyright (c) Microsoft. All rights reserved.
using System;
using System.ClientModel;
using Azure.AI.OpenAI;
using Azure.Core;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI;
using OpenAI.Assistants;
using OpenAI.Chat;
using OpenAI.Responses;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="OpenAIAgentFactory"/> abstract base class.
/// </summary>
public abstract class OpenAIAgentFactory : AgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIAgentFactory"/> class.
    /// </summary>
    protected OpenAIAgentFactory(ILoggerFactory? loggerFactory)
    {
        this.LoggerFactory = loggerFactory;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIAgentFactory"/> class.
    /// </summary>
    protected OpenAIAgentFactory(Uri endpoint, TokenCredential tokenCredential, ILoggerFactory? loggerFactory)
    {
        Throw.IfNull(endpoint);
        Throw.IfNull(tokenCredential);

        this._endpoint = endpoint;
        this._tokenCredential = tokenCredential;
        this.LoggerFactory = loggerFactory;
    }

    /// <summary>
    /// Gets the <see cref="ILoggerFactory"/> instance used for creating loggers.
    /// </summary>
    protected ILoggerFactory? LoggerFactory { get; }

    /// <summary>
    /// Creates a new instance of the <see cref="ChatClient"/> class.
    /// </summary>
    protected ChatClient? CreateChatClient(GptComponentMetadata promptAgent)
    {
        var model = promptAgent.Model as ExternalModel;
        var provider = model?.Provider?.Value ?? ModelProvider.OpenAI;
        if (provider == ModelProvider.OpenAI)
        {
            return CreateOpenAIChatClient(promptAgent);
        }
        else if (provider == ModelProvider.AzureOpenAI)
        {
            Throw.IfNull(this._endpoint, "A endpoint must be specified to create an Azure OpenAI client");
            Throw.IfNull(this._tokenCredential, "A token credential must be specified to create an Azure OpenAI client");
            return CreateAzureOpenAIChatClient(promptAgent, this._endpoint, this._tokenCredential);
        }

        return null;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="AssistantClient"/> class.
    /// </summary>
    protected AssistantClient? CreateAssistantClient(GptComponentMetadata promptAgent)
    {
        var model = promptAgent.Model as ExternalModel;
        var provider = model?.Provider?.Value ?? ModelProvider.OpenAI;
        if (provider == ModelProvider.OpenAI)
        {
            return CreateOpenAIAssistantClient(promptAgent);
        }
        else if (provider == ModelProvider.AzureOpenAI)
        {
            Throw.IfNull(this._endpoint, "The connection endpoint must be specified to create an Azure OpenAI client.");
            Throw.IfNull(this._tokenCredential, "A token credential must be specified to create an Azure OpenAI client");
            return CreateAzureOpenAIAssistantClient(promptAgent, this._endpoint, this._tokenCredential);
        }

        return null;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIResponseClient"/> class.
    /// </summary>
    protected OpenAIResponseClient? CreateResponseClient(GptComponentMetadata promptAgent)
    {
        var model = promptAgent.Model as ExternalModel;
        var provider = model?.Provider?.Value ?? ModelProvider.OpenAI;
        if (provider == ModelProvider.OpenAI)
        {
            return CreateOpenAIResponseClient(promptAgent);
        }
        else if (provider == ModelProvider.AzureOpenAI)
        {
            Throw.IfNull(this._endpoint, "The connection endpoint must be specified to create an Azure OpenAI client.");
            Throw.IfNull(this._tokenCredential, "A token credential must be specified to create an Azure OpenAI client");
            return CreateAzureOpenAIResponseClient(promptAgent, this._endpoint, this._tokenCredential);
        }

        return null;
    }

    #region private
    private readonly Uri? _endpoint;
    private readonly TokenCredential? _tokenCredential;

    private static ChatClient CreateOpenAIChatClient(GptComponentMetadata promptAgent)
    {
        var modelId = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        return CreateOpenAIClient(promptAgent).GetChatClient(modelId);
    }

    private static ChatClient CreateAzureOpenAIChatClient(GptComponentMetadata promptAgent, Uri endpoint, TokenCredential tokenCredential)
    {
        var deploymentName = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        return new AzureOpenAIClient(endpoint, tokenCredential).GetChatClient(deploymentName);
    }

    private static AssistantClient CreateOpenAIAssistantClient(GptComponentMetadata promptAgent)
    {
        var modelId = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        return CreateOpenAIClient(promptAgent).GetAssistantClient();
    }

    private static AssistantClient CreateAzureOpenAIAssistantClient(GptComponentMetadata promptAgent, Uri endpoint, TokenCredential tokenCredential)
    {
        var deploymentName = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        return new AzureOpenAIClient(endpoint, tokenCredential).GetAssistantClient();
    }

    private static OpenAIResponseClient CreateOpenAIResponseClient(GptComponentMetadata promptAgent)
    {
        var modelId = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        return CreateOpenAIClient(promptAgent).GetOpenAIResponseClient(modelId);
    }

    private static OpenAIResponseClient CreateAzureOpenAIResponseClient(GptComponentMetadata promptAgent, Uri endpoint, TokenCredential tokenCredential)
    {
        var deploymentName = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        return new AzureOpenAIClient(endpoint, tokenCredential).GetOpenAIResponseClient(deploymentName);
    }

    private static OpenAIClient CreateOpenAIClient(GptComponentMetadata promptAgent)
    {
        var model = promptAgent.Model as ExternalModel;

        var keyConnection = model?.Connection as ApiKeyConnection;
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
