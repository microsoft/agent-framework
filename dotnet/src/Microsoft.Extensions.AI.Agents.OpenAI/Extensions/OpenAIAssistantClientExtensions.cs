// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI.Assistants;

namespace OpenAI;

/// <summary>
/// Provides extension methods for OpenAI <see cref="AssistantClient"/>
/// to simplify the creation of AI agents that work with OpenAI services.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between OpenAI SDK client objects and the Microsoft Extensions AI Agent framework,
/// allowing developers to easily create AI agents that leverage OpenAI's chat completion and response services.
/// The methods handle the conversion from OpenAI clients to <see cref="IChatClient"/> instances and then wrap them
/// in <see cref="ChatClientAgent"/> objects that implement the <see cref="AIAgent"/> interface.
/// </remarks>
public static class OpenAIAssistantClientExtensions
{
    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AssistantClient"/>.
    /// </summary>
    /// <param name="assistantClient">The <see cref="AssistantClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId">The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant agent.</returns>
    public static ChatClientAgent GetAIAgent(
        this AssistantClient assistantClient,
        string agentId,
        ChatOptions? chatOptions = null,
        CancellationToken cancellationToken = default)
    {
        if (assistantClient is null)
        {
            throw new ArgumentNullException(nameof(assistantClient));
        }

        if (string.IsNullOrWhiteSpace(agentId))
        {
            throw new ArgumentException($"{nameof(agentId)} should not be null or whitespace.", nameof(agentId));
        }

        var assistant = assistantClient.GetAssistant(agentId, cancellationToken);
        return assistant.AsAIAgent(assistantClient, chatOptions);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AssistantClient"/>.
    /// </summary>
    /// <param name="assistantClient">The <see cref="AssistantClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant agent.</returns>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AssistantClient assistantClient,
        string agentId,
        ChatOptions? chatOptions = null,
        CancellationToken cancellationToken = default)
    {
        if (assistantClient is null)
        {
            throw new ArgumentNullException(nameof(assistantClient));
        }

        if (string.IsNullOrWhiteSpace(agentId))
        {
            throw new ArgumentException($"{nameof(agentId)} should not be null or whitespace.", nameof(agentId));
        }

        var assistanceResponse = await assistantClient.GetAssistantAsync(agentId, cancellationToken).ConfigureAwait(false);

        return assistanceResponse.AsAIAgent(assistantClient, chatOptions);
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static AIAgent CreateAIAgent(this AssistantClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null) =>
        client.CreateAIAgent(
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

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static AIAgent CreateAIAgent(this AssistantClient client, string model, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(client);
        Throw.IfNullOrEmpty(model);
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
                    // Attempting to set the tools at the agent level throws
                    // https://github.com/dotnet/extensions/issues/6743
                    //case AIFunction aiFunction:
                    //    assistantOptions.Tools.Add(ToOpenAIAssistantsFunctionToolDefinition(aiFunction));
                    //    break;

                    case HostedCodeInterpreterTool:
                        var codeInterpreterToolDefinition = new CodeInterpreterToolDefinition();
                        assistantOptions.Tools.Add(codeInterpreterToolDefinition);
                        break;
                }
            }
        }

        var assistantCreateResult = client.CreateAssistant(model, assistantOptions);
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

        return new ChatClientAgent(client.AsIChatClient(assistantId), agentOptions, loggerFactory);
    }

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="instructions">Optional system instructions that define the agent's behavior and personality.</param>
    /// <param name="name">Optional name for the agent for identification purposes.</param>
    /// <param name="description">Optional description of the agent's capabilities and purpose.</param>
    /// <param name="tools">Optional collection of AI tools that the agent can use during conversations.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static async Task<AIAgent> CreateAIAgentAsync(this AssistantClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null) =>
        await client.CreateAIAgentAsync(
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
            loggerFactory).ConfigureAwait(false);

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static async Task<AIAgent> CreateAIAgentAsync(this AssistantClient client, string model, ChatClientAgentOptions options, ILoggerFactory? loggerFactory = null)
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
                    // Attempting to set the tools at the agent level throws
                    // https://github.com/dotnet/extensions/issues/6743
                    //case AIFunction aiFunction:
                    //    assistantOptions.Tools.Add(ToOpenAIAssistantsFunctionToolDefinition(aiFunction));
                    //    break;

                    case HostedCodeInterpreterTool:
                        var codeInterpreterToolDefinition = new CodeInterpreterToolDefinition();
                        assistantOptions.Tools.Add(codeInterpreterToolDefinition);
                        break;
                }
            }
        }

        var assistantCreateResult = await client.CreateAssistantAsync(model, assistantOptions).ConfigureAwait(false);
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

        return new ChatClientAgent(client.AsIChatClient(assistantId), agentOptions, loggerFactory);
    }
}
