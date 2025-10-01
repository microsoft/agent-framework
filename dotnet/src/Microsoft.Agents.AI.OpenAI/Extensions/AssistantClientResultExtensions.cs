// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace OpenAI.Assistants;

/// <summary>
/// Provides extension methods for working with <see cref="ClientResult{Assistant}"/> where T is <see cref="Assistant"/>.
/// </summary>
public static class AssistantExtensions
{
    /// <summary>
    /// Converts a <see cref="ClientResult{Assistant}"/> to a <see cref="ChatClientAgent"/>.
    /// </summary>
    /// <param name="assistantClientResult">The client result containing the assistant.</param>
    /// <param name="assistantClient">The assistant client.</param>
    /// <param name="chatOptions">Optional chat options.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant.</returns>
    public static ChatClientAgent AsAIAgent(
        this ClientResult<Assistant> assistantClientResult,
        AssistantClient assistantClient,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null)
    {
        if (assistantClientResult is null)
        {
            throw new ArgumentNullException(nameof(assistantClientResult));
        }

        return AsAIAgent(assistantClientResult.Value, assistantClient, chatOptions, clientFactory);
    }

    /// <summary>
    /// Converts an <see cref="Assistant"/> to a <see cref="ChatClientAgent"/>.
    /// </summary>
    /// <param name="assistantMetadata">The assistant metadata.</param>
    /// <param name="assistantClient">The assistant client.</param>
    /// <param name="chatOptions">Optional chat options.</param>
    /// <param name="clientFactory">Provides a way to customize the creation of the underlying <see cref="IChatClient"/> used by the agent.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant.</returns>
    public static ChatClientAgent AsAIAgent(
        this Assistant assistantMetadata,
        AssistantClient assistantClient,
        ChatOptions? chatOptions = null,
        Func<IChatClient, IChatClient>? clientFactory = null)
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

        return new ChatClientAgent(chatClient, options: new()
        {
            Id = assistantMetadata.Id,
            Name = assistantMetadata.Name,
            Description = assistantMetadata.Description,
            Instructions = assistantMetadata.Instructions,
            ChatOptions = chatOptions
        });
    }
}
