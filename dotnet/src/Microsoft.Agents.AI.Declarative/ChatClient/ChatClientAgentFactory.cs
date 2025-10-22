// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
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
    public ChatClientAgentFactory()
    {
    }

    /// <summary>
    /// Creates a new instance of the <see cref="ChatClientAgentFactory"/> class.
    /// </summary>
    public ChatClientAgentFactory(IChatClient chatClient)
    {
        Throw.IfNull(chatClient);

        this._chatClient = chatClient;
    }

    /// <summary>
    /// Creates a new instance of the <see cref="ChatClientAgentFactory"/> class.
    /// </summary>
    public ChatClientAgentFactory(IServiceProvider serviceProvider)
    {
        Throw.IfNull(serviceProvider);

        this._serviceProvider = serviceProvider;
    }

    /// <inheritdoc/>
    public override Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, AgentCreationOptions? agentCreationOptions, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var chatClientAgentOptions = agentCreationOptions as ChatClientAgentCreationOptions;
        IServiceProvider? serviceProvider = agentCreationOptions?.ServiceProvider ?? this._serviceProvider;
        IChatClient? chatClient = this.GetIChatClient(promptAgent, chatClientAgentOptions, serviceProvider);
        if (chatClient == null)
        {
            throw new ArgumentException("A chat client must be provided via ChatClientAgentCreationOptions.", nameof(agentCreationOptions));
        }
        ILoggerFactory? loggerFactory = serviceProvider?.GetService(typeof(ILoggerFactory)) as ILoggerFactory;

        var options = new ChatClientAgentOptions()
        {
            Name = promptAgent.Name,
            Description = promptAgent.Description,
            Instructions = promptAgent.Instructions?.ToTemplateString(),
            ChatOptions = promptAgent.GetChatOptions(agentCreationOptions),
        };

        var agent = new ChatClientAgent(chatClient, options, loggerFactory);

        return Task.FromResult<AIAgent?>(agent);
    }

    #region
    private readonly IChatClient? _chatClient;
    private readonly IServiceProvider? _serviceProvider;

    private IChatClient? GetIChatClient(PromptAgent promptAgent, ChatClientAgentCreationOptions? agentOptions, IServiceProvider? serviceProvider)
    {
        var chatClient = agentOptions?.ChatClient ?? this._chatClient;

        if (chatClient is null && serviceProvider is not null)
        {
            string? serviceKey = promptAgent.GenerateServiceKey();
            if (!string.IsNullOrEmpty(serviceKey))
            {
                chatClient = serviceProvider.GetKeyedService<IChatClient>(serviceKey);
            }
            chatClient ??= serviceProvider.GetService<IChatClient>();
        }

        return chatClient;
    }
    #endregion
}
