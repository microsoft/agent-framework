// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents the unique identifier for a long-running operation.
/// </summary>
public sealed partial class RunId
{
    /// <summary>Gets or sets an identifier for the state of the conversation.</summary>
    public string? ConversationId { get; set; }

    /// <summary>Gets or sets the ID of the chat response.</summary>
    public string? ResponseId { get; set; }

    /// <summary>
    /// Creates a new instance of <see cref="RunId"/> from <see cref="NewChatOptions"/>."/>
    /// </summary>
    /// <param name="response">The <see cref="NewChatOptions"/> to extract the RunId from.</param>
    /// <returns>An instance of <see cref="RunId"/>.</returns>
    public static RunId FromChatResponse(NewChatResponse response)
    {
        _ = Throw.IfNull(response);

        return new RunId
        {
            ResponseId = response.ResponseId,
            ConversationId = response.ConversationId
        };
    }

    /// <summary>
    /// Creates a new instance of <see cref="RunId"/> from <see cref="NewChatResponseUpdate"/>."/>
    /// </summary>
    /// <param name="responseUpdate">The <see cref="NewChatResponseUpdate"/> to extract the RunId from.</param>
    /// <returns>An instance of <see cref="RunId"/>.</returns>
    public static RunId FromChatResponseUpdate(NewChatResponseUpdate responseUpdate)
    {
        _ = Throw.IfNull(responseUpdate);
        return new RunId
        {
            ResponseId = responseUpdate.ResponseId,
            ConversationId = responseUpdate.ConversationId
        };
    }

    ///// <summary>
    ///// Creates a new instance of <see cref="RunId"/> from <see cref="NewChatResponseUpdate"/>.
    ///// </summary>
    ///// <param name="update">The <see cref="NewChatResponseUpdate"/> to extract the RunId from.</param>
    ///// <returns>An instance of <see cref="RunId"/>.</returns>
    //public static implicit operator RunId(NewChatResponseUpdate update) => new() { ConversationId = update.ConversationId, ResponseId = update.ResponseId };

    ///// <summary>
    ///// Creates a new instance of <see cref="RunId"/> from <see cref="NewChatResponse"/>.
    ///// </summary>
    ///// <param name="response">The <see cref="NewChatResponse"/> to extract the RunId from.</param>
    ///// <returns>An instance of <see cref="RunId"/>.</returns>
    //public static implicit operator RunId(NewChatResponse response) => new() { ResponseId = response.RunId, ConversationId = null };
}
