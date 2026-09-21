// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.ObjectModel;
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
    /// <param name="chatClient">The chat client used by created agents.</param>
    /// <param name="functions">Optional functions exposed as tools to created agents.</param>
    /// <param name="engine">Optional Power Fx engine used to evaluate declarative expressions.</param>
    /// <param name="configuration">Optional configuration used to resolve explicitly allowed environment variables referenced by the agent definition.</param>
    /// <param name="loggerFactory">Optional logger factory used by created agents.</param>
    public ChatClientPromptAgentFactory(
        IChatClient chatClient,
        IList<AIFunction>? functions = null,
        RecalcEngine? engine = null,
        IConfiguration? configuration = null,
        ILoggerFactory? loggerFactory = null)
        : this(chatClient, functions, engine, configuration, loggerFactory, null)
    {
        // BINARY COMPAT CONSTRUCTOR
    }

    /// <summary>
    /// Creates a new instance of the <see cref="ChatClientPromptAgentFactory"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client used by created agents.</param>
    /// <param name="functions">Optional functions exposed as tools to created agents.</param>
    /// <param name="engine">Optional Power Fx engine used to evaluate declarative expressions.</param>
    /// <param name="configuration">Optional configuration used to resolve explicitly allowed environment variables referenced by the agent definition.</param>
    /// <param name="loggerFactory">Optional logger factory used by created agents.</param>
    /// <param name="allowedConfigurationVariables">Optional explicitly allowed environment variables referenced by the agent definition.</param>
    public ChatClientPromptAgentFactory(
        IChatClient chatClient,
        IList<AIFunction>? functions,
        RecalcEngine? engine,
        IConfiguration? configuration,
        ILoggerFactory? loggerFactory,
        IEnumerable<string>? allowedConfigurationVariables)
        : base(engine, configuration, allowedConfigurationVariables)
    {
        Throw.IfNull(chatClient);
        this._chatClient = chatClient;
        this._functions = functions;
        this._loggerFactory = loggerFactory;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        this.InitializeConfigurationVariables(promptAgent);

        var options = new ChatClientAgentOptions()
        {
            Name = promptAgent.Name,
            Description = promptAgent.Description,
            ChatOptions = await promptAgent.GetChatOptionsAsync(this.Engine, this._functions, cancellationToken: cancellationToken).ConfigureAwait(false),
        };

        var agent = new ChatClientAgent(this._chatClient, options, this._loggerFactory);

        Declarative.FeatureUsageMarker.MarkUsed();
        return agent;
    }

    #region private
    private readonly IChatClient _chatClient;
    private readonly IList<AIFunction>? _functions;
    private readonly ILoggerFactory? _loggerFactory;

    #endregion
}
