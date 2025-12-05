// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using OpenAI.Assistants;

namespace OpenAI;

/// <summary>
/// Provides extension methods for OpenAI <see cref="AssistantClient"/>
/// to simplify the creation of AI agents that work with OpenAI services.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between OpenAI SDK client objects and the Microsoft Agent Framework,
/// allowing developers to easily create AI agents that leverage OpenAI's chat completion and response services.
/// The methods handle the conversion from OpenAI clients to <see cref="IChatClient"/> instances and then wrap them
/// in <see cref="ChatClientAgent"/> objects that implement the <see cref="AIAgent"/> interface.
/// </remarks>
public static class OpenAIAssistantClientExtensions
{
    /// <summary>
    /// Gets a <see cref="ChatClientAgent"/> from a <see cref="ClientResult{Assistant}"/>.
    /// </summary>
    /// <param name="assistantClient">The assistant client.</param>
    /// <param name="assistantClientResult">The client result containing the assistant.</param>
    /// <param name="chatOptions">Optional chat options.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant.</returns>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static ChatClientAgent GetAIAgent(
        this AssistantClient assistantClient,
        ClientResult<Assistant> assistantClientResult,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        if (assistantClientResult is null)
        {
            throw new ArgumentNullException(nameof(assistantClientResult));
        }

        return assistantClient.GetAIAgent(assistantClientResult.Value, chatOptions, clientFactory, services);
    }

    /// <summary>
    /// Gets a <see cref="ChatClientAgent"/> from an <see cref="Assistant"/>.
    /// </summary>
    /// <param name="assistantClient">The assistant client.</param>
    /// <param name="assistantMetadata">The assistant metadata.</param>
    /// <param name="chatOptions">Optional chat options.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant.</returns>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static ChatClientAgent GetAIAgent(
        this AssistantClient assistantClient,
        Assistant assistantMetadata,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        if (assistantMetadata is null)
        {
            throw new ArgumentNullException(nameof(assistantMetadata));
        }
        if (assistantClient is null)
        {
            throw new ArgumentNullException(nameof(assistantClient));
        }

        var chatClient = assistantClient.AsIChatClient(assistantMetadata.Id);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        if (!string.IsNullOrWhiteSpace(assistantMetadata.Instructions) && chatOptions?.Instructions is null)
        {
            chatOptions ??= new ChatOptions();
            chatOptions.Instructions = assistantMetadata.Instructions;
        }

        return new ChatClientAgent(chatClient, options: new()
        {
            Id = assistantMetadata.Id,
            Name = assistantMetadata.Name,
            Description = assistantMetadata.Description,
            ChatOptions = chatOptions
        }, services: services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AssistantClient"/>.
    /// </summary>
    /// <param name="assistantClient">The <see cref="AssistantClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId">The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant agent.</returns>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static ChatClientAgent GetAIAgent(
        this AssistantClient assistantClient,
        string agentId,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
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
        return assistantClient.GetAIAgent(assistant, chatOptions, clientFactory, services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AssistantClient"/>.
    /// </summary>
    /// <param name="assistantClient">The <see cref="AssistantClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant agent.</returns>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AssistantClient assistantClient,
        string agentId,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
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

        var assistantResponse = await assistantClient.GetAssistantAsync(agentId, cancellationToken).ConfigureAwait(false);
        return assistantClient.GetAIAgent(assistantResponse, chatOptions, clientFactory, services);
    }

    /// <summary>
    /// Gets a <see cref="ChatClientAgent"/> from a <see cref="ClientResult{Assistant}"/>.
    /// </summary>
    /// <param name="assistantClient">The assistant client.</param>
    /// <param name="assistantClientResult">The client result containing the assistant.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="assistantClientResult"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static ChatClientAgent GetAIAgent(
        this AssistantClient assistantClient,
        ClientResult<Assistant> assistantClientResult,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        if (assistantClientResult is null)
        {
            throw new ArgumentNullException(nameof(assistantClientResult));
        }

        return assistantClient.GetAIAgent(assistantClientResult.Value, options, clientFactory, services);
    }

    /// <summary>
    /// Gets a <see cref="ChatClientAgent"/> from an <see cref="Assistant"/>.
    /// </summary>
    /// <param name="assistantClient">The assistant client.</param>
    /// <param name="assistantMetadata">The assistant metadata.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="assistantMetadata"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static ChatClientAgent GetAIAgent(
        this AssistantClient assistantClient,
        Assistant assistantMetadata,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        if (assistantMetadata is null)
        {
            throw new ArgumentNullException(nameof(assistantMetadata));
        }

        if (assistantClient is null)
        {
            throw new ArgumentNullException(nameof(assistantClient));
        }

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var chatClient = assistantClient.AsIChatClient(assistantMetadata.Id);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        if (string.IsNullOrWhiteSpace(options.ChatOptions?.Instructions) && !string.IsNullOrWhiteSpace(assistantMetadata.Instructions))
        {
            options.ChatOptions ??= new ChatOptions();
            options.ChatOptions.Instructions = assistantMetadata.Instructions;
        }

        var mergedOptions = new ChatClientAgentOptions()
        {
            Id = assistantMetadata.Id,
            Name = options.Name ?? assistantMetadata.Name,
            Description = options.Description ?? assistantMetadata.Description,
            ChatOptions = options.ChatOptions,
            AIContextProviderFactory = options.AIContextProviderFactory,
            ChatMessageStoreFactory = options.ChatMessageStoreFactory,
            UseProvidedChatClientAsIs = options.UseProvidedChatClientAsIs
        };

        return new ChatClientAgent(chatClient, mergedOptions, services: services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AssistantClient"/>.
    /// </summary>
    /// <param name="assistantClient">The <see cref="AssistantClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId">The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant agent.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="assistantClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="agentId"/> is empty or whitespace.</exception>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static ChatClientAgent GetAIAgent(
        this AssistantClient assistantClient,
        string agentId,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
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

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var assistant = assistantClient.GetAssistant(agentId, cancellationToken);
        return assistantClient.GetAIAgent(assistant, options, clientFactory, services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="AssistantClient"/>.
    /// </summary>
    /// <param name="assistantClient">The <see cref="AssistantClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant agent.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="assistantClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="agentId"/> is empty or whitespace.</exception>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this AssistantClient assistantClient,
        string agentId,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
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

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var assistantResponse = await assistantClient.GetAssistantAsync(agentId, cancellationToken).ConfigureAwait(false);
        return assistantClient.GetAIAgent(assistantResponse, options, clientFactory, services);
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
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>An <see cref="ChatClientAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static ChatClientAgent CreateAIAgent(
        this AssistantClient client,
        string model,
        string? instructions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null) =>
        client.CreateAIAgent(
            model,
            new ChatClientAgentOptions()
            {
                Name = name,
                Description = description,
                ChatOptions = tools is null && string.IsNullOrWhiteSpace(instructions) ? null : new ChatOptions()
                {
                    Tools = tools,
                    Instructions = instructions
                }
            },
            clientFactory,
            loggerFactory,
            services);

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>An <see cref="ChatClientAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static ChatClientAgent CreateAIAgent(
        this AssistantClient client,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null)
    {
        Throw.IfNull(client);
        Throw.IfNullOrEmpty(model);
        Throw.IfNull(options);

        var assistantOptions = new AssistantCreationOptions()
        {
            Name = options.Name,
            Description = options.Description,
            Instructions = options.ChatOptions?.Instructions,
        };

        // Convert AITools to ToolDefinitions and ToolResources
        var toolDefinitionsAndResources = ConvertAIToolsToToolDefinitions(options.ChatOptions?.Tools);
        if (toolDefinitionsAndResources.ToolDefinitions is { Count: > 0 })
        {
            toolDefinitionsAndResources.ToolDefinitions.ForEach(x => assistantOptions.Tools.Add(x));
        }

        if (toolDefinitionsAndResources.ToolResources is not null)
        {
            assistantOptions.ToolResources = toolDefinitionsAndResources.ToolResources;
        }

        // Create the assistant in the assistant service.
        var assistantCreateResult = client.CreateAssistant(model, assistantOptions);
        var assistantId = assistantCreateResult.Value.Id;

        // Build the local agent object.
        var chatClient = client.AsIChatClient(assistantId);
        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        var agentOptions = options.Clone();
        agentOptions.Id = assistantId;
        options.ChatOptions ??= new ChatOptions();
        options.ChatOptions!.Tools = toolDefinitionsAndResources.FunctionToolsAndOtherTools;

        return new ChatClientAgent(chatClient, agentOptions, loggerFactory, services);
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
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An <see cref="ChatClientAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AssistantClient client,
        string model,
        string? instructions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default) =>
        await client.CreateAIAgentAsync(model,
            new ChatClientAgentOptions()
            {
                Name = name,
                Description = description,
                ChatOptions = tools is null && string.IsNullOrWhiteSpace(instructions) ? null : new ChatOptions()
                {
                    Tools = tools,
                    Instructions = instructions,
                }
            },
            clientFactory,
            loggerFactory,
            services,
            cancellationToken).ConfigureAwait(false);

    /// <summary>
    /// Creates an AI agent from an <see cref="AssistantClient"/> using the OpenAI Assistant API.
    /// </summary>
    /// <param name="client">The OpenAI <see cref="AssistantClient" /> to use for the agent.</param>
    /// <param name="model">The model identifier to use (e.g., "gpt-4").</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An <see cref="ChatClientAgent"/> instance backed by the OpenAI Assistant service.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="client"/> or <paramref name="model"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    [Obsolete("The Assistants API has been deprecated. Please use the Responses API instead.")]
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AssistantClient client,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(client);
        Throw.IfNull(model);
        Throw.IfNull(options);

        var assistantOptions = new AssistantCreationOptions()
        {
            Name = options.Name,
            Description = options.Description,
            Instructions = options.ChatOptions?.Instructions,
        };

        // Convert AITools to ToolDefinitions and ToolResources
        var toolDefinitionsAndResources = ConvertAIToolsToToolDefinitions(options.ChatOptions?.Tools);
        if (toolDefinitionsAndResources.ToolDefinitions is { Count: > 0 } toolDefinitions)
        {
            toolDefinitions.ForEach(x => assistantOptions.Tools.Add(x));
        }
        if (toolDefinitionsAndResources.ToolResources is not null)
        {
            assistantOptions.ToolResources = toolDefinitionsAndResources.ToolResources;
        }

        // Create the assistant in the assistant service.
        var assistantCreateResult = await client.CreateAssistantAsync(model, assistantOptions, cancellationToken).ConfigureAwait(false);
        var assistantId = assistantCreateResult.Value.Id;

        // Build the local agent object.
        var chatClient = client.AsIChatClient(assistantId);
        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        var agentOptions = options.Clone();
        agentOptions.Id = assistantId;
        options.ChatOptions ??= new ChatOptions();
        options.ChatOptions!.Tools = toolDefinitionsAndResources.FunctionToolsAndOtherTools;

        return new ChatClientAgent(chatClient, agentOptions, loggerFactory, services);
    }

    private static (List<ToolDefinition>? ToolDefinitions, ToolResources? ToolResources, List<AITool>? FunctionToolsAndOtherTools) ConvertAIToolsToToolDefinitions(IList<AITool>? tools)
    {
        List<ToolDefinition>? toolDefinitions = null;
        ToolResources? toolResources = null;
        List<AITool>? functionToolsAndOtherTools = null;

        if (tools is not null)
        {
            foreach (AITool tool in tools)
            {
                switch (tool)
                {
                    case HostedCodeInterpreterTool codeTool:

                        toolDefinitions ??= [];
                        toolDefinitions.Add(new CodeInterpreterToolDefinition());

                        if (codeTool.Inputs is { Count: > 0 })
                        {
                            foreach (var input in codeTool.Inputs)
                            {
                                switch (input)
                                {
                                    case HostedFileContent hostedFile:
                                        // If the input is a HostedFileContent, we can use its ID directly.
                                        toolResources ??= new();
                                        toolResources.CodeInterpreter ??= new();
                                        toolResources.CodeInterpreter.FileIds.Add(hostedFile.FileId);
                                        break;
                                }
                            }
                        }
                        break;

                    case HostedFileSearchTool fileSearchTool:
                        toolDefinitions ??= [];
                        toolDefinitions.Add(new FileSearchToolDefinition
                        {
                            MaxResults = fileSearchTool.MaximumResultCount,
                        });

                        if (fileSearchTool.Inputs is { Count: > 0 })
                        {
                            foreach (var input in fileSearchTool.Inputs)
                            {
                                switch (input)
                                {
                                    case HostedVectorStoreContent hostedVectorStore:
                                        toolResources ??= new();
                                        toolResources.FileSearch ??= new();
                                        toolResources.FileSearch.VectorStoreIds.Add(hostedVectorStore.VectorStoreId);
                                        break;
                                }
                            }
                        }
                        break;

                    default:
                        functionToolsAndOtherTools ??= [];
                        functionToolsAndOtherTools.Add(tool);
                        break;
                }
            }
        }

        return (toolDefinitions, toolResources, functionToolsAndOtherTools);
    }
}
