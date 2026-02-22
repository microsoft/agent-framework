// Copyright (c) Microsoft. All rights reserved.
using System;
using System.ClientModel;
using Azure.AI.OpenAI;
using Azure.Core;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.PowerFx;
using Microsoft.Shared.Diagnostics;
using OpenAI;
using OpenAI.Assistants;
using OpenAI.Chat;
using OpenAI.Responses;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="BaseOpenAIPromptAgentFactory"/> abstract base class.
/// </summary>
public abstract class BaseOpenAIPromptAgentFactory : PromptAgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="BaseOpenAIPromptAgentFactory"/> class.
    /// </summary>
    protected BaseOpenAIPromptAgentFactory(RecalcEngine? engine = null, IConfiguration? configuration = null, ILoggerFactory? loggerFactory = null) : base(engine, configuration)
    {
        this.LoggerFactory = loggerFactory;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="BaseOpenAIPromptAgentFactory"/> class.
    /// </summary>
    protected BaseOpenAIPromptAgentFactory(Uri endpoint, TokenCredential tokenCredential, RecalcEngine? engine = null, IConfiguration? configuration = null, ILoggerFactory? loggerFactory = null) : base(engine, configuration)
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
        var model = promptAgent.Model as CurrentModels;
        var provider = model?.Provider?.Value ?? ModelProvider.OpenAI;
        if (provider == ModelProvider.OpenAI)
        {
            return this.CreateOpenAIChatClient(promptAgent);
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
        var model = promptAgent.Model as CurrentModels;
        var provider = model?.Provider?.Value ?? ModelProvider.OpenAI;
        if (provider == ModelProvider.OpenAI)
        {
            return this.CreateOpenAIAssistantClient(promptAgent);
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
    /// Creates a new instance of the <see cref="ResponsesClient"/> class.
    /// </summary>
    protected ResponsesClient? CreateResponseClient(GptComponentMetadata promptAgent)
    {
        var model = promptAgent.Model as CurrentModels;
        var provider = model?.Provider?.Value ?? ModelProvider.OpenAI;
        if (provider == ModelProvider.OpenAI)
        {
            return this.CreateResponsesClient(promptAgent);
        }
        else if (provider == ModelProvider.AzureOpenAI)
        {
            Throw.IfNull(this._endpoint, "The connection endpoint must be specified to create an Azure OpenAI client.");
            Throw.IfNull(this._tokenCredential, "A token credential must be specified to create an Azure OpenAI client");
            return CreateAzureResponsesClient(promptAgent, this._endpoint, this._tokenCredential);
        }

        return null;
    }

    #region private
    private readonly Uri? _endpoint;
    private readonly TokenCredential? _tokenCredential;

    private ChatClient CreateOpenAIChatClient(GptComponentMetadata promptAgent)
    {
        var modelId = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        return this.CreateOpenAIClient(promptAgent).GetChatClient(modelId);
    }

    private static ChatClient CreateAzureOpenAIChatClient(GptComponentMetadata promptAgent, Uri endpoint, TokenCredential tokenCredential)
    {
        var deploymentName = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        return new AzureOpenAIClient(endpoint, tokenCredential).GetChatClient(deploymentName);
    }

    private AssistantClient CreateOpenAIAssistantClient(GptComponentMetadata promptAgent)
    {
        var modelId = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        return this.CreateOpenAIClient(promptAgent).GetAssistantClient();
    }

    private static AssistantClient CreateAzureOpenAIAssistantClient(GptComponentMetadata promptAgent, Uri endpoint, TokenCredential tokenCredential)
    {
        var deploymentName = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        return new AzureOpenAIClient(endpoint, tokenCredential).GetAssistantClient();
    }

    private ResponsesClient CreateResponsesClient(GptComponentMetadata promptAgent)
    {
        var modelId = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(modelId, "The model id must be specified in the agent definition to create an OpenAI agent.");

        return this.CreateOpenAIClient(promptAgent).GetResponsesClient(modelId);
    }

    private static ResponsesClient CreateAzureResponsesClient(GptComponentMetadata promptAgent, Uri endpoint, TokenCredential tokenCredential)
    {
        var deploymentName = promptAgent.Model?.ModelNameHint;
        Throw.IfNullOrEmpty(deploymentName, "The deployment name (using model.id) must be specified in the agent definition to create an Azure OpenAI agent.");

        return new AzureOpenAIClient(endpoint, tokenCredential).GetResponsesClient(deploymentName);
    }

    private OpenAIClient CreateOpenAIClient(GptComponentMetadata promptAgent)
    {
        var model = promptAgent.Model as CurrentModels;

        var keyConnection = model?.Connection as ApiKeyConnection;
        Throw.IfNull(keyConnection, "A key connection must be specified when create an OpenAI client");

        var apiKey = keyConnection.Key!.Eval(this.Engine);
        Throw.IfNullOrEmpty(apiKey, "The connection key must be specified in the agent definition to create an OpenAI client.");

        var clientOptions = new OpenAIClientOptions();
        var endpoint = keyConnection.Endpoint?.Eval(this.Engine);
        if (!string.IsNullOrEmpty(endpoint))
        {
            clientOptions.Endpoint = new Uri(endpoint);
        }

        return new OpenAIClient(new ApiKeyCredential(apiKey), clientOptions);
    }
    #endregion
}
