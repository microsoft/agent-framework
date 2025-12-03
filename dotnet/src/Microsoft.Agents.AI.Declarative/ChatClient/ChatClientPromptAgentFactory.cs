// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.PowerFx;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="PromptAgentFactory"/> which creates instances of <see cref="ChatClientAgent"/>.
/// </summary>
public sealed class ChatClientPromptAgentFactory : PromptAgentFactory
{
    /// <summary>
    /// Creates a new instance of the <see cref="ChatClientPromptAgentFactory"/> class.
    /// </summary>
    public ChatClientPromptAgentFactory(IChatClient chatClient, IList<AIFunction>? functions = null, RecalcEngine? engine = null, IConfiguration? configuration = null, ILoggerFactory? loggerFactory = null) : base(engine, configuration)
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
            ChatOptions = promptAgent.GetChatOptions(this.Engine, this._functions),
        };

        var agent = new ChatClientAgent(this._chatClient, options, this._loggerFactory);

        return Task.FromResult<AIAgent?>(agent);
    }

    #region private
    private readonly IChatClient _chatClient;
    private readonly IList<AIFunction>? _functions;
    private readonly ILoggerFactory? _loggerFactory;
    #endregion
}
