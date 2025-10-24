// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI.Chat;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="AIAgent"/> using a <see cref="ChatClient"/>.
/// </summary>
public sealed class OpenAIChatAgentFactory : OpenAIAgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIChatAgentFactory"/> class.
    /// </summary>
    public OpenAIChatAgentFactory(IList<AIFunction>? functions = null, ILoggerFactory? loggerFactory = null) : base(loggerFactory)
    {
        this._functions = functions;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIChatAgentFactory"/> class.
    /// </summary>
    public OpenAIChatAgentFactory(ChatClient chatClient, IList<AIFunction>? functions = null, ILoggerFactory? loggerFactory = null) : base(loggerFactory)
    {
        Throw.IfNull(chatClient);

        this._chatClient = chatClient;
        this._functions = functions;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="OpenAIChatAgentFactory"/> class.
    /// </summary>
    public OpenAIChatAgentFactory(Uri endpoint, TokenCredential tokenCredential, IList<AIFunction>? functions = null, ILoggerFactory? loggerFactory = null) : base(endpoint, tokenCredential, loggerFactory)
    {
        this._functions = functions;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var apiType = promptAgent.Model.ApiType;
        if (apiType?.IsUnknown() == false && apiType.Value != ApiType.Chat)
        {
            return null;
        }

        var options = new ChatClientAgentOptions()
        {
            Name = promptAgent.Name,
            Description = promptAgent.Description,
            Instructions = promptAgent.Instructions?.ToTemplateString(),
            ChatOptions = promptAgent.GetChatOptions(this._functions),
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
