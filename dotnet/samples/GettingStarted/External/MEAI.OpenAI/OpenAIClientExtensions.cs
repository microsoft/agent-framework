// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI.Assistants;
using OpenAI.Chat;
using OpenAI.Responses;

namespace OpenAI;

/// <summary>
/// Provides extension methods for <see cref="OpenAIClient"/>, <see cref="ChatClient"/>, and <see cref="OpenAIResponseClient"/>
/// to simplify the creation of AI agents that work with OpenAI services.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between OpenAI SDK client objects and the Microsoft Extensions AI Agent framework,
/// allowing developers to easily create AI agents that leverage OpenAI's chat completion and response services.
/// The methods handle the conversion from OpenAI clients to <see cref="IChatClient"/> instances and then wrap them
/// in <see cref="ChatClientAgent"/> objects that implement the <see cref="AIAgent"/> interface.
/// </remarks>
public static class OpenAIClientExtensions
{
    /// <summary>
    /// Creates an AI agent from an <see cref="OpenAIClient"/> using the OpenAI Chat Completion API.
    /// </summary>
    /// <param name="client">The OpenAI client to use for the agent.</param>
    /// <param name="model">The model identifier to use for chat completions (e.g., "gpt-4", "gpt-3.5-turbo").</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Chat Completion service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static AIAgent CreateChatClientAgent(this OpenAIClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        return client.CreateChatClientAgent(
            model,
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
    /// Creates an AI agent from an <see cref="OpenAIClient"/> using the OpenAI Chat Completion API.
    /// </summary>
    /// <param name="client">The OpenAI client to use for the agent.</param>
    /// <param name="model">The model identifier to use for chat completions (e.g., "gpt-4", "gpt-3.5-turbo").</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Chat Completion service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static AIAgent CreateChatClientAgent(this OpenAIClient client, string model, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(model);

        var chatClient = client.GetChatClient(model).AsIChatClient();
        ChatClientAgent agent = new(chatClient, options, loggerFactory);
        return agent;
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="OpenAIClient"/> using the OpenAI Response API.
    /// </summary>
    /// <param name="client">The OpenAI client to use for the agent.</param>
    /// <param name="model">The model identifier to use for responses (e.g., "gpt-4", "gpt-3.5-turbo").</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Response service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static AIAgent CreateResponseClientAgent(this OpenAIClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        return client.CreateResponseClientAgent(
            model,
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
    /// Creates an AI agent from an <see cref="OpenAIClient"/> using the OpenAI Response API.
    /// </summary>
    /// <param name="client">The OpenAI client to use for the agent.</param>
    /// <param name="model">The model identifier to use for responses (e.g., "gpt-4", "gpt-3.5-turbo").</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Response service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static AIAgent CreateResponseClientAgent(this OpenAIClient client, string model, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(model);

        var chatClient = client.GetOpenAIResponseClient(model).AsIChatClient();
        ChatClientAgent agent = new(chatClient, options, loggerFactory);
        return agent;
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="OpenAIClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI client to use for the agent.</param>
    /// <param name="model">The model identifier to use for responses (e.g., "gpt-4", "gpt-3.5-turbo").</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Response service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static async Task<AIAgent> CreateAssistantClientAgentAsync(this OpenAIClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        return await client.CreateAssistantClientAgentAsync(
            model,
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
    /// Creates an AI agent from an <see cref="OpenAIClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI client to use for the agent.</param>
    /// <param name="model">The model identifier to use for responses (e.g., "gpt-4", "gpt-3.5-turbo").</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Response service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static async Task<AIAgent> CreateAssistantClientAgentAsync(this OpenAIClient client, string model, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNull(model);
        Throw.IfNull(options);

        var assistantOptions = new AssistantCreationOptions()
        {
            Name = options.Name,
            Description = options.Description,
            Instructions = options.Instructions,
        };

        if (options.ChatOptions?.Tools is not null)
        {
            foreach (AITool tool in options.ChatOptions.Tools)
            {
                switch (tool)
                {
                    case AIFunction aiFunction:
                        assistantOptions.Tools.Add(NewOpenAIAssistantChatClient.ToOpenAIAssistantsFunctionToolDefinition(aiFunction));
                        break;

                    case HostedCodeInterpreterTool:
                        var codeInterpreterToolDefinition = new CodeInterpreterToolDefinition();
                        assistantOptions.Tools.Add(codeInterpreterToolDefinition);
                        break;
                }
            }
        }

        var assistantClient = client.GetAssistantClient();

        var assistantCreateResult = await assistantClient.CreateAssistantAsync(model, assistantOptions);
        var assistantId = assistantCreateResult.Value.Id;

        var agentOptions = new ChatClientAgentOptions()
        {
            Id = assistantId,
            Name = options.Name,
            Description = options.Description,
            Instructions = options.Instructions,
            ChatOptions = options.ChatOptions?.Tools is null ? null : new ChatOptions()
            {
                Tools = options.ChatOptions.Tools,
            }
        };

        var chatClient = new NewOpenAIAssistantChatClient(assistantClient, assistantId);
        return new ChatClientAgent(chatClient, agentOptions, loggerFactory);
    }
}
