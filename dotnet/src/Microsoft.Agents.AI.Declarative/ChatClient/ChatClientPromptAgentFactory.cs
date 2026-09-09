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
        : this(
            chatClient,
            functions,
            new ChatClientPromptAgentFactoryOptions()
            {
                Engine = engine,
                Configuration = configuration,
                LoggerFactory = loggerFactory,
            })
    {
    }

    /// <summary>
    /// Creates a new instance of the <see cref="ChatClientPromptAgentFactory"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client used by created agents.</param>
    /// <param name="functions">Optional functions exposed as tools to created agents.</param>
    /// <param name="options">Options used to configure the created agents and declarative expression evaluation.</param>
    public ChatClientPromptAgentFactory(
        IChatClient chatClient,
        IList<AIFunction>? functions,
        ChatClientPromptAgentFactoryOptions options) :
        base(options?.Engine, options?.Configuration, options?.AllowedConfigurationVariables, options?.MaximumExpressionLength, options?.MaximumCallDepth)
    {
        Throw.IfNull(chatClient);
        Throw.IfNull(options);

        this._chatClient = chatClient;
        this._functions = functions;
        this._loggerFactory = options.LoggerFactory;
    }

    /// <inheritdoc/>
    public override Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        this.InitializeConfigurationVariables(promptAgent);

        var options = new ChatClientAgentOptions()
        {
            Name = promptAgent.Name,
            Description = promptAgent.Description,
            ChatOptions = promptAgent.GetChatOptions(this.Engine, this._functions),
        };

        var agent = new ChatClientAgent(this._chatClient, options, this._loggerFactory);

        Declarative.FeatureUsageMarker.MarkUsed();
        return Task.FromResult<AIAgent?>(agent);
    }

    #region private
    private readonly IChatClient _chatClient;
    private readonly IList<AIFunction>? _functions;
    private readonly ILoggerFactory? _loggerFactory;
    #endregion
}

/// <summary>
/// Options for configuring <see cref="ChatClientPromptAgentFactory"/>.
/// </summary>
public sealed class ChatClientPromptAgentFactoryOptions
{
    /// <summary>
    /// Gets or sets configuration keys that may be exposed to Power Fx when the agent definition references them through <c>Env</c>.
    /// </summary>
    public IEnumerable<string>? AllowedConfigurationVariables { get; init; }

    /// <summary>
    /// Gets or sets an optional Power Fx engine used to evaluate declarative expressions.
    /// </summary>
    public RecalcEngine? Engine { get; init; }

    /// <summary>
    /// Gets or sets optional configuration used to resolve explicitly allowed environment variables referenced by the agent definition.
    /// </summary>
    public IConfiguration? Configuration { get; init; }

    /// <summary>
    /// Gets or sets an optional logger factory used by created agents.
    /// </summary>
    public ILoggerFactory? LoggerFactory { get; init; }

    /// <summary>
    /// Gets or sets an optional maximum length for Power Fx expressions evaluated by the factory-created engine.
    /// </summary>
    public int? MaximumExpressionLength { get; init; }

    /// <summary>
    /// Gets or sets an optional maximum nested call depth for Power Fx expressions evaluated by the factory-created engine.
    /// </summary>
    public int? MaximumCallDepth { get; init; }
}
