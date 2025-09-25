// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

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
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant.</returns>
    public static ChatClientAgent AsAIAgent(this ClientResult<Assistant> assistantClientResult, AssistantClient assistantClient, ChatOptions? chatOptions = null)
    {
        if (assistantClientResult is null)
        {
            throw new ArgumentNullException(nameof(assistantClientResult));
        }

        return AsAIAgent(assistantClientResult.Value, assistantClient, chatOptions);
    }

    /// <summary>
    /// Converts an <see cref="Assistant"/> to a <see cref="ChatClientAgent"/>.
    /// </summary>
    /// <param name="assistantMetadata">The assistant metadata.</param>
    /// <param name="assistantClient">The assistant client.</param>
    /// <param name="chatOptions">Optional chat options.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the assistant.</returns>
    public static ChatClientAgent AsAIAgent(this Assistant assistantMetadata, AssistantClient assistantClient, ChatOptions? chatOptions = null)
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
