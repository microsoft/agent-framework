// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace Azure.AI.Agents.Persistent;

/// <summary>
/// Provides extension methods for working with <see cref="Response{PersistentAgent}"/>.
/// </summary>
internal static class PersistentAgentResponseExtensions
{
    /// <summary>
    /// Converts a response containing persistent agent metadata into a runnable agent instance.
    /// </summary>
    /// <param name="persistentAgentResponse">The response containing the persistent agent to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="chatOptions">The default <see cref="ChatOptions"/> to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static ChatClientAgent AsAIAgent(this Response<PersistentAgent> persistentAgentResponse, PersistentAgentsClient persistentAgentsClient, ChatOptions? chatOptions = null, Func<IChatClient, IChatClient>? clientFactory = null)
    {
        if (persistentAgentResponse is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentResponse));
        }

        return AsAIAgent(persistentAgentResponse.Value, persistentAgentsClient, chatOptions, clientFactory);
    }

    /// <summary>
    /// Converts a <see cref="PersistentAgent"/> containing metadata about a persistent agent into a runnable agent instance.
    /// </summary>
    /// <param name="persistentAgentMetadata">The persistent agent metadata to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <param name="chatOptions">The default <see cref="ChatOptions"/> to use when interacting with the agent.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static ChatClientAgent AsAIAgent(this PersistentAgent persistentAgentMetadata, PersistentAgentsClient persistentAgentsClient, ChatOptions? chatOptions = null, Func<IChatClient, IChatClient>? clientFactory = null)
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
}
