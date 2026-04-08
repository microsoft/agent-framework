// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.FoundryLocal;

/// <summary>
/// Provides extension methods for <see cref="FoundryLocalChatClient"/>
/// to simplify the creation of AI agents that work with Foundry Local on-device models.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between the Foundry Local chat client and the Microsoft Agent Framework,
/// allowing developers to easily create AI agents that leverage local model inference.
/// The methods wrap the <see cref="FoundryLocalChatClient"/> in <see cref="ChatClientAgent"/> objects
/// that implement the <see cref="AIAgent"/> interface.
/// </remarks>
public static class FoundryLocalChatClientExtensions
{
    /// <summary>
    /// Creates an AI agent from a <see cref="FoundryLocalChatClient"/> for local model inference.
    /// </summary>
    /// <param name="client">The <see cref="FoundryLocalChatClient"/> to use for the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance backed by Foundry Local on-device inference.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent AsAIAgent(
        this FoundryLocalChatClient client,
        string? instructions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null) =>
        client.AsAIAgent(
            new ChatClientAgentOptions()
            {
                Name = name,
                Description = description,
                ChatOptions = tools is null && string.IsNullOrWhiteSpace(instructions) ? null : new ChatOptions()
                {
                    Instructions = instructions,
                    Tools = tools,
                }
            },
            clientFactory,
            loggerFactory,
            services);

    /// <summary>
    /// Creates an AI agent from a <see cref="FoundryLocalChatClient"/> for local model inference.
    /// </summary>
    /// <param name="client">The <see cref="FoundryLocalChatClient"/> to use for the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="options">Full set of options to configure the agent. Cannot be <see langword="null"/>.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance backed by Foundry Local on-device inference.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent AsAIAgent(
        this FoundryLocalChatClient client,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(options);

        IChatClient chatClient = client;

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        return new ChatClientAgent(chatClient, options, loggerFactory, services);
    }
}
