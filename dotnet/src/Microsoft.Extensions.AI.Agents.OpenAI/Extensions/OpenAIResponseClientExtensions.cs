// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

namespace OpenAI;

/// <summary>
/// Provides extension methods for <see cref="OpenAIResponseClient"/>
/// to simplify the creation of AI agents that work with OpenAI services.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between OpenAI SDK client objects and the Microsoft Extensions AI Agent framework,
/// allowing developers to easily create AI agents that leverage OpenAI's chat completion and response services.
/// The methods handle the conversion from OpenAI clients to <see cref="IChatClient"/> instances and then wrap them
/// in <see cref="ChatClientAgent"/> objects that implement the <see cref="AIAgent"/> interface.
/// </remarks>
public static class OpenAIResponseClientExtensions
{
    /// <summary>
    /// Creates an AI agent from an <see cref="OpenAIResponseClient"/> using the OpenAI Response API.
    /// </summary>
    /// <param name="client">The <see cref="OpenAIResponseClient" /> to use for the agent.</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Response service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> is <see langword="null"/>.</exception>
    public static AIAgent CreateAIAgent(this OpenAIResponseClient client, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        return client.CreateAIAgent(
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
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="OpenAIResponseClient"/> using the OpenAI Response API.
    /// </summary>
    /// <param name="client">The <see cref="OpenAIResponseClient" /> to use for the agent.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Response service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static AIAgent CreateAIAgent(this OpenAIResponseClient client, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(options);

#pragma warning disable CA2000 // Dispose objects before losing scope
        var chatClient = client.AsNewIChatClient();
#pragma warning restore CA2000 // Dispose objects before losing scope
        ChatClientAgent agent = new(chatClient, options, loggerFactory);
        return agent;
    }

    /// <summary>Gets an <see cref="IChatClient"/> for use with this <see cref="OpenAIResponseClient"/>.</summary>
    /// <param name="responseClient">The client.</param>
    /// <returns>An <see cref="IChatClient"/> that can be used to converse via the <see cref="OpenAIResponseClient"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="responseClient"/> is <see langword="null"/>.</exception>
    public static IChatClient AsNewIChatClient(this OpenAIResponseClient responseClient) =>
        new NewOpenAIResponsesChatClient(responseClient);
}
