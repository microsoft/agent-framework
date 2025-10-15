// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using Azure.Core;
using Microsoft.Agents.AI;

namespace Microsoft.Extensions.AI.Agents.Purview;

/// <summary>
/// Extension methods to add Purview capabilities to an <see cref="AIAgent"/>.
/// </summary>
public static class PurviewExtensions
{
    /// <summary>
    /// Adds Purview capabilities to an <see cref="AIAgentBuilder"/>.
    /// </summary>
    /// <param name="builder">The AI Agent builder for <see cref="AIAgent"/>.</param>
    /// <param name="tokenCredential">The token credential used to authenticate with Purview.</param>
    /// <param name="purviewSettings">The settings for communication with Purview.</param>
    /// <returns>The updated <see cref="AIAgentBuilder"/></returns>
    public static AIAgentBuilder WithPurview(this AIAgentBuilder builder, TokenCredential tokenCredential, PurviewSettings purviewSettings)
    {
        PurviewAgentWrapper purviewWrapper = new(tokenCredential, purviewSettings);

        return builder.Use(async (IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken) =>
            await purviewWrapper.RunAsync(messages, thread, options, innerAgent, cancellationToken).ConfigureAwait(false),
            null);
    }

    /// <summary>
    /// Sets the user id for a message.
    /// </summary>
    /// <param name="message">The message.</param>
    /// <param name="userId">The id of the owner of the message.</param>
    public static void SetUserId(this ChatMessage message, Guid userId)
    {
        if (message.AdditionalProperties == null)
        {
            message.AdditionalProperties = new AdditionalPropertiesDictionary();
        }

        message.AdditionalProperties[Constants.UserId] = userId.ToString();
    }

    /// <summary>
    /// Sets the conversation id for a message.
    /// </summary>
    /// <param name="message">The messgae.</param>
    /// <param name="conversationId">The id of the conversation that the message belongs to.</param>
    public static void SetConversationId(this ChatMessage message, Guid conversationId)
    {
        if (message.AdditionalProperties == null)
        {
            message.AdditionalProperties = new AdditionalPropertiesDictionary();
        }
        message.AdditionalProperties[Constants.ConversationId] = conversationId.ToString();
    }
}
