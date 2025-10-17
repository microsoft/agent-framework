// Copyright (c) Microsoft. All rights reserved.

using System;
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
    /// <param name="builder">The AI Agent builder for the <see cref="AIAgent"/>.</param>
    /// <param name="tokenCredential">The token credential used to authenticate with Purview.</param>
    /// <param name="purviewSettings">The settings for communication with Purview.</param>
    /// <returns>The updated <see cref="AIAgentBuilder"/></returns>
    public static AIAgentBuilder WithPurview(this AIAgentBuilder builder, TokenCredential tokenCredential, PurviewSettings purviewSettings)
    {
        PurviewWrapper purviewWrapper = new(tokenCredential, purviewSettings);
        return builder.Use(purviewWrapper.ProcessAgentContentAsync, null);
    }

    /// <summary>
    /// Adds Purview capabilities to a <see cref="ChatClientBuilder"/>.
    /// </summary>
    /// <param name="builder">The chat client builder for the <see cref="IChatClient"/>.</param>
    /// <param name="tokenCredential">The token credential used to authenticate with Purview.</param>
    /// <param name="purviewSettings">The settings for communication with Purview.</param>
    /// <returns>The updated <see cref="ChatClientBuilder"/></returns>
    public static ChatClientBuilder WithPurview(this ChatClientBuilder builder, TokenCredential tokenCredential, PurviewSettings purviewSettings)
    {
        PurviewWrapper purviewWrapper = new(tokenCredential, purviewSettings);
        return builder.Use(purviewWrapper.ProcessChatContentAsync, null);
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
}
