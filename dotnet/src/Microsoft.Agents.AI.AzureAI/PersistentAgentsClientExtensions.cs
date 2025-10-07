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
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static ChatClientAgent GetAIAgent(this PersistentAgentsClient persistentAgentsClient, Response<PersistentAgent> persistentAgentResponse, ChatOptions? chatOptions = null, Func<IChatClient, IChatClient>? clientFactory = null)
    {
        if (persistentAgentResponse is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentResponse));
        }

        return GetAIAgent(persistentAgentsClient, persistentAgentResponse.Value, chatOptions, clientFactory);
    }

    /// <summary>
    /// Gets a runnable agent instance from a <see cref="PersistentAgent"/> containing metadata about a persistent agent.
    /// </summary>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentMetadata">The persistent agent metadata to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="chatOptions">The default <see cref="ChatOptions"/> to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static ChatClientAgent GetAIAgent(this PersistentAgentsClient persistentAgentsClient, PersistentAgent persistentAgentMetadata, ChatOptions? chatOptions = null, Func<IChatClient, IChatClient>? clientFactory = null)
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

        return new ChatClientAgent(chatClient, options: new()
        {
            Id = persistentAgentMetadata.Id,
            Name = persistentAgentMetadata.Name,
            Description = persistentAgentMetadata.Description,
            Instructions = persistentAgentMetadata.Instructions,
            ChatOptions = chatOptions
        });
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <returns>A <see cref="ChatClientAgent"/> for the persistent agent.</returns>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static ChatClientAgent GetAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
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
        return persistentAgentsClient.GetAIAgent(persistentAgentResponse, chatOptions, clientFactory);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <returns>A <see cref="ChatClientAgent"/> for the persistent agent.</returns>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
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
        return persistentAgentsClient.GetAIAgent(persistentAgentResponse, chatOptions, clientFactory);
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
        return await persistentAgentsClient.GetAIAgentAsync(createPersistentAgentResponse.Value.Id, clientFactory: clientFactory, cancellationToken: cancellationToken).ConfigureAwait(false);
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
        return persistentAgentsClient.GetAIAgent(createPersistentAgentResponse.Value.Id, clientFactory: clientFactory, cancellationToken: cancellationToken);
    }
}
