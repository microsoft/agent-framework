// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.PowerFx;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="PromptAgentFactory"/> which creates instances of <see cref="AIAgent"/> using a <see cref="ResponsesClient"/>.
/// </summary>
public sealed class OpenAIResponsesPromptAgentFactory : BaseOpenAIPromptAgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIResponsesPromptAgentFactory"/> class.
    /// </summary>
    public OpenAIResponsesPromptAgentFactory(IList<AIFunction>? functions = null, RecalcEngine? engine = null, IConfiguration? configuration = null, ILoggerFactory? loggerFactory = null) : base(engine, configuration, loggerFactory)
    {
        this._functions = functions;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIResponsesPromptAgentFactory"/> class.
    /// </summary>
    public OpenAIResponsesPromptAgentFactory(ResponsesClient responsesClient, IList<AIFunction>? functions = null, RecalcEngine? engine = null, IConfiguration? configuration = null, ILoggerFactory? loggerFactory = null) : base(engine, configuration, loggerFactory)
    {
        Throw.IfNull(responsesClient);

        this._responsesClient = responsesClient;
        this._functions = functions;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIResponsesPromptAgentFactory"/> class.
    /// </summary>
    public OpenAIResponsesPromptAgentFactory(Uri endpoint, TokenCredential tokenCredential, IList<AIFunction>? functions = null, RecalcEngine? engine = null, IConfiguration? configuration = null, ILoggerFactory? loggerFactory = null) : base(endpoint, tokenCredential, engine, configuration, loggerFactory)
    {
        this._functions = functions;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var model = promptAgent.Model as CurrentModels;
        var apiType = model?.ApiType;
        if (apiType?.IsUnknown() == true || apiType?.Value != ModelApiType.Responses)
        {
            return null;
        }

        var options = new ChatClientAgentOptions()
        {
            Name = promptAgent.Name,
            Description = promptAgent.Description,
            ChatOptions = promptAgent.GetChatOptions(this.Engine, this._functions),
        };

        var responseClient = this._responsesClient ?? this.CreateResponseClient(promptAgent);
        if (responseClient is not null)
        {
            return new ChatClientAgent(
                responseClient.AsIChatClient(),
                options,
                this.LoggerFactory);
        }

        return null;
    }

    #region private
    private readonly ResponsesClient? _responsesClient;
    private readonly IList<AIFunction>? _functions;
    #endregion
}
