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
using OpenAI.Chat;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="PromptAgentFactory"/> which creates instances of <see cref="AIAgent"/> using a <see cref="ChatClient"/>.
/// </summary>
public sealed class OpenAIPromptAgentFactory : BaseOpenAIPromptAgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIPromptAgentFactory"/> class.
    /// </summary>
    public OpenAIPromptAgentFactory(IList<AIFunction>? functions = null, RecalcEngine? engine = null, IConfiguration? configuration = null, ILoggerFactory? loggerFactory = null) : base(engine, configuration, loggerFactory)
    {
        this._functions = functions;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIPromptAgentFactory"/> class.
    /// </summary>
    public OpenAIPromptAgentFactory(ChatClient chatClient, IList<AIFunction>? functions = null, RecalcEngine? engine = null, IConfiguration? configuration = null, ILoggerFactory? loggerFactory = null) : base(engine, configuration, loggerFactory)
    {
        Throw.IfNull(chatClient);

        this._chatClient = chatClient;
        this._functions = functions;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIPromptAgentFactory"/> class.
    /// </summary>
    public OpenAIPromptAgentFactory(Uri endpoint, TokenCredential tokenCredential, IList<AIFunction>? functions = null, RecalcEngine? engine = null, IConfiguration? configuration = null, ILoggerFactory? loggerFactory = null) : base(endpoint, tokenCredential, engine, configuration, loggerFactory)
    {
        this._functions = functions;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var model = promptAgent.Model as CurrentModels;
        var apiType = model?.ApiType;
        if (apiType?.IsUnknown() == true || apiType?.Value != ModelApiType.Chat)
        {
            return null;
        }

        var options = new ChatClientAgentOptions()
        {
            Name = promptAgent.Name,
            Description = promptAgent.Description,
            ChatOptions = promptAgent.GetChatOptions(this.Engine, this._functions),
        };

        ChatClient? chatClient = this._chatClient ?? this.CreateChatClient(promptAgent);
        if (chatClient is not null)
        {
            return new ChatClientAgent(
                chatClient.AsIChatClient(),
                options,
                this.LoggerFactory);
        }

        return null;
    }

    #region private
    private readonly ChatClient? _chatClient;
    private readonly IList<AIFunction>? _functions;
    #endregion
}
