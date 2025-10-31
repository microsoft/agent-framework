﻿// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AgentFactory"/> which creates instances of <see cref="ChatClientAgent"/>.
/// </summary>
public sealed class ChatClientAgentFactory : AgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="ChatClientAgentFactory"/> class.
    /// </summary>
    public ChatClientAgentFactory(IChatClient chatClient, IList<AIFunction>? functions = null, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(chatClient);

        this._chatClient = chatClient;
        this._functions = functions;
        this._loggerFactory = loggerFactory;
    }

    /// <inheritdoc/>
    public override Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var options = new ChatClientAgentOptions()
        {
            Name = promptAgent.Name,
            Description = promptAgent.Description,
            Instructions = promptAgent.Instructions?.ToTemplateString(),
            ChatOptions = promptAgent.GetChatOptions(this._functions),
        };

        var agent = new ChatClientAgent(this._chatClient, options, this._loggerFactory);

        return Task.FromResult<AIAgent?>(agent);
    }

    #region
    private readonly IChatClient _chatClient;
    private readonly IList<AIFunction>? _functions;
    private readonly ILoggerFactory? _loggerFactory;
    #endregion
}
