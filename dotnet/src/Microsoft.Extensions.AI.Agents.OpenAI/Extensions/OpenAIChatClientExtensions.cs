// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI.Chat;

namespace OpenAI;

/// <summary>
/// Provides extension methods for <see cref="ChatClient"/>
/// to simplify the creation of AI agents that work with OpenAI services.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between OpenAI SDK client objects and the Microsoft Extensions AI Agent framework,
/// allowing developers to easily create AI agents that leverage OpenAI's chat completion and response services.
/// The methods handle the conversion from OpenAI clients to <see cref="IChatClient"/> instances and then wrap them
/// in <see cref="ChatClientAgent"/> objects that implement the <see cref="AIAgent"/> interface.
/// </remarks>
public static class OpenAIChatClientExtensions
{
    /// <summary>
    /// Creates an AI agent from an <see cref="ChatClient"/> using the OpenAI Chat Completion API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="ChatClient"/> to use for the agent.</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Chat Completion service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> is <see langword="null"/>.</exception>
    public static AIAgent CreateAIAgent(this ChatClient client, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null) =>
        client.CreateAIAgent(
            new ChatClientAgentOptions()
            {
                Name = name,
                Description = description,
                Instructions = instructions,
                ChatOptions = tools is null ? null : new ChatOptions()
                {
                    Tools = tools,
                }
            },
            loggerFactory);

    /// <summary>
    /// Creates an AI agent from an <see cref="ChatClient"/> using the OpenAI Chat Completion API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="ChatClient"/> to use for the agent.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Chat Completion service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static AIAgent CreateAIAgent(this ChatClient client, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(options);

        var chatClient = client.AsIChatClient();
        return new ChatClientAgent(chatClient, options, loggerFactory);
    }
}
