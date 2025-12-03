// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Azure.AI.Agents.Persistent;

/// <summary>
/// Provides extension methods for <see cref="PersistentAgentsClient"/>.
/// </summary>
public static class PersistentAgentsClientExtensions
{
    /// <summary>
    /// Gets a runnable agent instance from the provided response containing persistent agent metadata.
    /// </summary>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentResponse">The response containing the persistent agent to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="chatOptions">The default <see cref="ChatOptions"/> to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static ChatClientAgent GetAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        Response<PersistentAgent> persistentAgentResponse,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        if (persistentAgentResponse is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentResponse));
        }

        return GetAIAgent(persistentAgentsClient, persistentAgentResponse.Value, chatOptions, clientFactory, services);
    }

    /// <summary>
    /// Gets a runnable agent instance from a <see cref="PersistentAgent"/> containing metadata about a persistent agent.
    /// </summary>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentMetadata">The persistent agent metadata to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="chatOptions">The default <see cref="ChatOptions"/> to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static ChatClientAgent GetAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        PersistentAgent persistentAgentMetadata,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        if (persistentAgentMetadata is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentMetadata));
        }

        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        var chatClient = persistentAgentsClient.AsIChatClient(persistentAgentMetadata.Id);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        if (!string.IsNullOrWhiteSpace(persistentAgentMetadata.Instructions) && chatOptions?.Instructions is null)
        {
            chatOptions ??= new ChatOptions();
            chatOptions.Instructions = persistentAgentMetadata.Instructions;
        }

        return new ChatClientAgent(chatClient, options: new()
        {
            Id = persistentAgentMetadata.Id,
            Name = persistentAgentMetadata.Name,
            Description = persistentAgentMetadata.Description,
            ChatOptions = chatOptions
        }, services: services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <returns>A <see cref="ChatClientAgent"/> for the persistent agent.</returns>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static ChatClientAgent GetAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        if (string.IsNullOrWhiteSpace(agentId))
        {
            throw new ArgumentException($"{nameof(agentId)} should not be null or whitespace.", nameof(agentId));
        }

        var persistentAgentResponse = persistentAgentsClient.Administration.GetAgent(agentId, cancellationToken);
        return persistentAgentsClient.GetAIAgent(persistentAgentResponse, chatOptions, clientFactory, services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <returns>A <see cref="ChatClientAgent"/> for the persistent agent.</returns>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        if (string.IsNullOrWhiteSpace(agentId))
        {
            throw new ArgumentException($"{nameof(agentId)} should not be null or whitespace.", nameof(agentId));
        }

        var persistentAgentResponse = await persistentAgentsClient.Administration.GetAgentAsync(agentId, cancellationToken).ConfigureAwait(false);
        return persistentAgentsClient.GetAIAgent(persistentAgentResponse, chatOptions, clientFactory, services);
    }

    /// <summary>
    /// Gets a runnable agent instance from the provided response containing persistent agent metadata.
    /// </summary>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentResponse">The response containing the persistent agent to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentResponse"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        Response<PersistentAgent> persistentAgentResponse,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        if (persistentAgentResponse is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentResponse));
        }

        return GetAIAgent(persistentAgentsClient, persistentAgentResponse.Value, options, clientFactory, services);
    }

    /// <summary>
    /// Gets a runnable agent instance from a <see cref="PersistentAgent"/> containing metadata about a persistent agent.
    /// </summary>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentMetadata">The persistent agent metadata to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentMetadata"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        PersistentAgent persistentAgentMetadata,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null)
    {
        if (persistentAgentMetadata is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentMetadata));
        }

        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var chatClient = persistentAgentsClient.AsIChatClient(persistentAgentMetadata.Id);

        if (clientFactory is not null)
        {
            chatClient = clientFactory(chatClient);
        }

        if (!string.IsNullOrWhiteSpace(persistentAgentMetadata.Instructions) && options.ChatOptions?.Instructions is null)
        {
            options.ChatOptions ??= new ChatOptions();
            options.ChatOptions.Instructions = persistentAgentMetadata.Instructions;
        }

        var agentOptions = new ChatClientAgentOptions()
        {
            Id = persistentAgentMetadata.Id,
            Name = options.Name ?? persistentAgentMetadata.Name,
            Description = options.Description ?? persistentAgentMetadata.Description,
            ChatOptions = options.ChatOptions,
            AIContextProviderFactory = options.AIContextProviderFactory,
            ChatMessageStoreFactory = options.ChatMessageStoreFactory,
            UseProvidedChatClientAsIs = options.UseProvidedChatClientAsIs
        };

        return new ChatClientAgent(chatClient, agentOptions, services: services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId">The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentsClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="agentId"/> is empty or whitespace.</exception>
    public static ChatClientAgent GetAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        if (string.IsNullOrWhiteSpace(agentId))
        {
            throw new ArgumentException($"{nameof(agentId)} should not be null or whitespace.", nameof(agentId));
        }

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var persistentAgentResponse = persistentAgentsClient.Administration.GetAgent(agentId, cancellationToken);
        return persistentAgentsClient.GetAIAgent(persistentAgentResponse, options, clientFactory, services);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId">The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentsClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="agentId"/> is empty or whitespace.</exception>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        if (string.IsNullOrWhiteSpace(agentId))
        {
            throw new ArgumentException($"{nameof(agentId)} should not be null or whitespace.", nameof(agentId));
        }

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var persistentAgentResponse = await persistentAgentsClient.Administration.GetAgentAsync(agentId, cancellationToken).ConfigureAwait(false);
        return persistentAgentsClient.GetAIAgent(persistentAgentResponse, options, clientFactory, services);
    }

    /// <summary>
    /// Creates a new server side agent using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the agent with.</param>
    /// <param name="model">The model to be used by the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="tools">The tools to be used by the agent.</param>
    /// <param name="toolResources">The resources for the tools.</param>
    /// <param name="temperature">The temperature setting for the agent.</param>
    /// <param name="topP">The top-p setting for the agent.</param>
    /// <param name="responseFormat">The response format for the agent.</param>
    /// <param name="metadata">The metadata for the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this PersistentAgentsClient persistentAgentsClient,
        string model,
        string? name = null,
        string? description = null,
        string? instructions = null,
        IEnumerable<ToolDefinition>? tools = null,
        ToolResources? toolResources = null,
        float? temperature = null,
        float? topP = null,
        BinaryData? responseFormat = null,
        IReadOnlyDictionary<string, string>? metadata = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        var createPersistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: model,
            name: name,
            description: description,
            instructions: instructions,
            tools: tools,
            toolResources: toolResources,
            temperature: temperature,
            topP: topP,
            responseFormat: responseFormat,
            metadata: metadata,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        // Get a local proxy for the agent to work with.
        return await persistentAgentsClient.GetAIAgentAsync(createPersistentAgentResponse.Value.Id, clientFactory: clientFactory, services: services, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Creates a new server side agent using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the agent with.</param>
    /// <param name="model">The model to be used by the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="tools">The tools to be used by the agent.</param>
    /// <param name="toolResources">The resources for the tools.</param>
    /// <param name="temperature">The temperature setting for the agent.</param>
    /// <param name="topP">The top-p setting for the agent.</param>
    /// <param name="responseFormat">The response format for the agent.</param>
    /// <param name="metadata">The metadata for the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    public static ChatClientAgent CreateAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        string model,
        string? name = null,
        string? description = null,
        string? instructions = null,
        IEnumerable<ToolDefinition>? tools = null,
        ToolResources? toolResources = null,
        float? temperature = null,
        float? topP = null,
        BinaryData? responseFormat = null,
        IReadOnlyDictionary<string, string>? metadata = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        var createPersistentAgentResponse = persistentAgentsClient.Administration.CreateAgent(
            model: model,
            name: name,
            description: description,
            instructions: instructions,
            tools: tools,
            toolResources: toolResources,
            temperature: temperature,
            topP: topP,
            responseFormat: responseFormat,
            metadata: metadata,
            cancellationToken: cancellationToken);

        // Get a local proxy for the agent to work with.
        return persistentAgentsClient.GetAIAgent(createPersistentAgentResponse.Value.Id, clientFactory: clientFactory, services: services, cancellationToken: cancellationToken);
    }

    /// <summary>
    /// Creates a new server side agent using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the agent with.</param>
    /// <param name="model">The model to be used by the agent.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentsClient"/> or <paramref name="model"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static ChatClientAgent CreateAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        if (string.IsNullOrWhiteSpace(model))
        {
            throw new ArgumentException($"{nameof(model)} should not be null or whitespace.", nameof(model));
        }

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var toolDefinitionsAndResources = ConvertAIToolsToToolDefinitions(options.ChatOptions?.Tools);

        var createPersistentAgentResponse = persistentAgentsClient.Administration.CreateAgent(
            model: model,
            name: options.Name,
            description: options.Description,
            instructions: options.ChatOptions?.Instructions,
            tools: toolDefinitionsAndResources.ToolDefinitions,
            toolResources: toolDefinitionsAndResources.ToolResources,
            temperature: null,
            topP: null,
            responseFormat: null,
            metadata: null,
            cancellationToken: cancellationToken);

        if (options.ChatOptions?.Tools is { Count: > 0 } && (toolDefinitionsAndResources.FunctionToolsAndOtherTools is null || options.ChatOptions.Tools.Count != toolDefinitionsAndResources.FunctionToolsAndOtherTools.Count))
        {
            options = options.Clone();
            options.ChatOptions!.Tools = toolDefinitionsAndResources.FunctionToolsAndOtherTools;
        }

        // Get a local proxy for the agent to work with.
        return persistentAgentsClient.GetAIAgent(createPersistentAgentResponse.Value.Id, options, clientFactory: clientFactory, services: services, cancellationToken: cancellationToken);
    }

    /// <summary>
    /// Creates a new server side agent using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the agent with.</param>
    /// <param name="model">The model to be used by the agent.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="services">An optional <see cref="IServiceProvider"/> to use for resolving services required by the <see cref="AIFunction"/> instances being invoked.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentsClient"/> or <paramref name="model"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="model"/> is empty or whitespace.</exception>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this PersistentAgentsClient persistentAgentsClient,
        string model,
        ChatClientAgentOptions options,
        Func<IChatClient, IChatClient>? clientFactory = null,
        IServiceProvider? services = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        if (string.IsNullOrWhiteSpace(model))
        {
            throw new ArgumentException($"{nameof(model)} should not be null or whitespace.", nameof(model));
        }

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var toolDefinitionsAndResources = ConvertAIToolsToToolDefinitions(options.ChatOptions?.Tools);

        var createPersistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model: model,
            name: options.Name,
            description: options.Description,
            instructions: options.ChatOptions?.Instructions,
            tools: toolDefinitionsAndResources.ToolDefinitions,
            toolResources: toolDefinitionsAndResources.ToolResources,
            temperature: null,
            topP: null,
            responseFormat: null,
            metadata: null,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        if (options.ChatOptions?.Tools is { Count: > 0 } && (toolDefinitionsAndResources.FunctionToolsAndOtherTools is null || options.ChatOptions.Tools.Count != toolDefinitionsAndResources.FunctionToolsAndOtherTools.Count))
        {
            options = options.Clone();
            options.ChatOptions!.Tools = toolDefinitionsAndResources.FunctionToolsAndOtherTools;
        }

        // Get a local proxy for the agent to work with.
        return await persistentAgentsClient.GetAIAgentAsync(createPersistentAgentResponse.Value.Id, options, clientFactory: clientFactory, services: services, cancellationToken: cancellationToken).ConfigureAwait(false);
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
                            FileSearch = new() { MaxNumResults = fileSearchTool.MaximumResultCount }
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

                    case HostedWebSearchTool webSearch when webSearch.AdditionalProperties?.TryGetValue("connectionId", out object? connectionId) is true:
                        toolDefinitions ??= [];
                        toolDefinitions.Add(new BingGroundingToolDefinition(new BingGroundingSearchToolParameters([new BingGroundingSearchConfiguration(connectionId!.ToString())])));
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
