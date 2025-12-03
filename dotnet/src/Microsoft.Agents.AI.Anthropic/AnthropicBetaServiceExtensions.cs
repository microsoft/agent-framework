// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Anthropic.Services;

/// <summary>
/// Provides extension methods for the <see cref="IBetaService"/> class.
/// </summary>
public static class AnthropicBetaServiceExtensions
{
    /// <summary>
    /// Specifies the default maximum number of tokens allowed for processing operations.
    /// </summary>
    public static int DefaultMaxTokens { get; set; } = 4096;

    /// <summary>
    /// Creates a new AI agent using the specified model and options.
    /// </summary>
    /// <param name="betaService">The Anthropic beta service.</param>
    /// <param name="model">The model to use for chat completions.</param>
    /// <param name="instructions">The instructions for the AI agent.</param>
    /// <param name="name">The name of the AI agent.</param>
    /// <param name="description">The description of the AI agent.</param>
    /// <param name="tools">The tools available to the AI agent.</param>
    /// <param name="defaultMaxTokens">The default maximum tokens for chat completions. Defaults to <see cref="DefaultMaxTokens"/> if not provided.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>The created <see cref="ChatClientAgent"/> AI agent.</returns>
    public static ChatClientAgent CreateAIAgent(
        this IBetaService betaService,
        string model,
        string? instructions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        int? defaultMaxTokens = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        var options = new ChatClientAgentOptions
        {
            Name = name,
            Description = description,
        };

        if (!string.IsNullOrWhiteSpace(instructions))
        {
            options.ChatOptions ??= new();
            options.ChatOptions.Instructions = instructions;
        }

        if (tools is { Count: > 0 })
        {
            options.ChatOptions ??= new();
            options.ChatOptions.Tools = tools;
        }

        var chatClient = betaService.AsIChatClient(model, defaultMaxTokens ?? DefaultMaxTokens);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, options, loggerFactory, services);
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="IBetaService"/> using the Anthropic Chat Completion API.
    /// </summary>
    /// <param name="betaService">The Anthropic <see cref="IBetaService"/> to use for the agent.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>An <see cref="ChatClientAgent"/> instance backed by the Anthropic Chat Completion service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="betaService"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent CreateAIAgent(
        this IBetaService betaService,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(betaService);
        Throw.IfNull(options);

        var chatClient = betaService.AsIChatClient();

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, options, loggerFactory, services);
    }
}
