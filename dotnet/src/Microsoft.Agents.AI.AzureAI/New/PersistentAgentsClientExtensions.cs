// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace Azure.AI.Agents.V2;

/// <summary>
/// Provides extension methods for <see cref="AgentsClient"/>.
/// </summary>
public static class AgentsClientExtensions
{
    /*
    /// <summary>
    /// Gets a runnable agent instance from the provided response containing persistent agent metadata.
    /// </summary>
    /// <param name="client">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentResponse">The response containing the persistent agent to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="chatOptions">The default <see cref="ChatOptions"/> to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static ChatClientAgent GetAIAgent(this AgentsClient client, Response<PersistentAgent> persistentAgentResponse, ChatOptions? chatOptions = null, Func<IChatClient, IChatClient>? clientFactory = null)
    {
        if (persistentAgentResponse is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentResponse));
        }

        return GetAIAgent(client, persistentAgentResponse.Value, chatOptions, clientFactory);
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
    /// Gets a runnable agent instance from the provided response containing persistent agent metadata.
    /// </summary>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentResponse">The response containing the persistent agent to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentResponse"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(this PersistentAgentsClient persistentAgentsClient, Response<PersistentAgent> persistentAgentResponse, ChatClientAgentOptions options, Func<IChatClient, IChatClient>? clientFactory = null)
    {
        if (persistentAgentResponse is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentResponse));
        }

        return GetAIAgent(persistentAgentsClient, persistentAgentResponse.Value, options, clientFactory);
    }

    /// <summary>
    /// Gets a runnable agent instance from a <see cref="PersistentAgent"/> containing metadata about a persistent agent.
    /// </summary>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentMetadata">The persistent agent metadata to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentMetadata"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    public static ChatClientAgent GetAIAgent(this PersistentAgentsClient persistentAgentsClient, PersistentAgent persistentAgentMetadata, ChatClientAgentOptions options, Func<IChatClient, IChatClient>? clientFactory = null)
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

        var agentOptions = new ChatClientAgentOptions()
        {
            Id = persistentAgentMetadata.Id,
            Name = options.Name ?? persistentAgentMetadata.Name,
            Description = options.Description ?? persistentAgentMetadata.Description,
            Instructions = options.Instructions ?? persistentAgentMetadata.Instructions,
            ChatOptions = options.ChatOptions,
            AIContextProviderFactory = options.AIContextProviderFactory,
            ChatMessageStoreFactory = options.ChatMessageStoreFactory,
            UseProvidedChatClientAsIs = options.UseProvidedChatClientAsIs
        };

        return new ChatClientAgent(chatClient, agentOptions);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId">The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentsClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="agentId"/> is empty or whitespace.</exception>
    public static ChatClientAgent GetAIAgent(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatClientAgentOptions options,
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

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var persistentAgentResponse = persistentAgentsClient.Administration.GetAgent(agentId, cancellationToken);
        return persistentAgentsClient.GetAIAgent(persistentAgentResponse, options, clientFactory);
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <param name="agentId">The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="persistentAgentsClient"/> or <paramref name="options"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="agentId"/> is empty or whitespace.</exception>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatClientAgentOptions options,
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

        if (options is null)
        {
            throw new ArgumentNullException(nameof(options));
        }

        var persistentAgentResponse = await persistentAgentsClient.Administration.GetAgentAsync(agentId, cancellationToken).ConfigureAwait(false);
        return persistentAgentsClient.GetAIAgent(persistentAgentResponse, options, clientFactory);
    }*/

    /// <summary>
    /// Creates a new server side agent using the provided <see cref="AgentsClient"/>.
    /// </summary>
    /// <param name="client">The <see cref="AgentsClient"/> to create the agent with.</param>
    /// <param name="model">The model to be used by the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="tools">The tools to be used by the agent.</param>
    /// <param name="temperature">The temperature setting for the agent.</param>
    /// <param name="topP">The top-p setting for the agent.</param>
    /// <param name="raiConfig">The responsible AI config</param>
    /// <param name="reasoningOptions">The reasoning options for the agent.</param>
    /// <param name="textOptions">The text options for the agent.</param>
    /// <param name="structuredInputs">The structured inputs for the agent.</param>
    /// <param name="metadata">The metadata for the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this AgentsClient client,
        string model,
        string? name = null,
        string? instructions = null,
        IEnumerable<ResponseTool>? tools = null,
        float? temperature = null,
        float? topP = null,
        RaiConfig? raiConfig = null,
        ResponseReasoningOptions? reasoningOptions = null,
        ResponseTextOptions? textOptions = null,
        IDictionary<string, StructuredInputDefinition>? structuredInputs = null,
        IReadOnlyDictionary<string, string>? metadata = null,
        Func<IChatClient, IChatClient>? clientFactory = null,
        CancellationToken cancellationToken = default)
    {
        if (client is null)
        {
            throw new ArgumentNullException(nameof(client));
        }

        var openAIClient = client.GetOpenAIClient();
        var chatClient = openAIClient.GetOpenAIResponseClient(model).AsIChatClient();

        var promptAgentDefinition = new PromptAgentDefinition(model)
        {
            Instructions = instructions,
            Temperature = temperature,
            TopP = topP,
            RaiConfig = raiConfig,
            ReasoningOptions = reasoningOptions,
            TextOptions = textOptions,
        };

        var versionCreation = new AgentVersionCreationOptions();
        if (metadata is not null)
        {
            foreach (var kvp in metadata)
            {
                versionCreation.Metadata.Add(kvp.Key, kvp.Value);
            }
        }

        AgentVersion newAgentVersion = await client.CreateAgentVersionAsync(name, promptAgentDefinition, versionCreation, cancellationToken).ConfigureAwait(false);

        if (tools is not null)
        {
            if (promptAgentDefinition.Tools is List<ResponseTool> toolsList)
            {
                toolsList.AddRange(tools);
            }
            else
            {
                foreach (var tool in tools)
                {
                    promptAgentDefinition.Tools.Add(tool);
                }
            }
        }

        if (structuredInputs is not null)
        {
            foreach (var kvp in structuredInputs)
            {
                promptAgentDefinition.StructuredInputs.Add(kvp.Key, kvp.Value);
            }
        }

        var agent = new ChatClientAgent(chatClient);
        agent.AsBuilder().Use(FoundryAgentMiddlewareAsync).Build();

        async Task FoundryAgentMiddlewareAsync(IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken, Task> sharedFunc, CancellationToken cancellationToken)
        {
            if (options is not ChatClientAgentRunOptions chatClientOptions)
            {
                throw new InvalidOperationException("The provided AgentRunOptions is not of type ChatClientAgentRunOptions.");
            }

            ChatClientAgentThread? chatClientThread = null;
            if (thread is not null)
            {
                if (thread is not ChatClientAgentThread asChatClientAgentThread)
                {
                    throw new InvalidOperationException("The provided AgentThread is not of type ChatClientAgentThread.");
                }

                if (string.IsNullOrWhiteSpace(asChatClientAgentThread.ConversationId))
                {
                    throw new InvalidOperationException("The ChatClientAgentThread does not have a valid ConversationId.");
                }

                chatClientThread = asChatClientAgentThread;
            }

            var conversation =
                chatClientThread is not null ?
                    await client.GetConversationClient().GetConversationAsync(chatClientThread.ConversationId, cancellationToken).ConfigureAwait(false) :
                    await client.GetConversationClient().CreateConversationAsync(cancellationToken: cancellationToken).ConfigureAwait(false);

            chatClientOptions.ChatOptions ??= new();
            chatClientOptions.ChatOptions.RawRepresentationFactory = (client) =>
            {
                var rawRepresentationFactory = chatClientOptions.ChatOptions?.RawRepresentationFactory;
                ResponseCreationOptions? responseCreationOptions = null;

                if (rawRepresentationFactory is not null)
                {
                    responseCreationOptions = rawRepresentationFactory.Invoke(chatClient) as ResponseCreationOptions;

                    if (responseCreationOptions is null)
                    {
                        throw new InvalidOperationException("The RawRepresentationFactory did not return a valid ResponseCreationOptions instance.");
                    }
                }
                else
                {
                    responseCreationOptions = new ResponseCreationOptions();
                }

                responseCreationOptions.SetAgentReference(name);
                responseCreationOptions.SetConversationReference(conversation);

                return responseCreationOptions;
            };

            await sharedFunc(messages, thread, options, cancellationToken).ConfigureAwait(false);
        }

        return agent;
    }
}
