// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Provides extension methods that read the <see cref="JevResult"/> of a <see cref="JevChatClient"/> response.
/// </summary>
public static class JevResultExtensions
{
    /// <summary>
    /// Gets the typed answers of a <see cref="JevChatClient"/> response.
    /// </summary>
    /// <param name="response">The chat response.</param>
    /// <returns>
    /// The answers to the request's questions, with their probabilities and token usage, or <see langword="null"/>
    /// when the response did not come from a <see cref="JevChatClient"/> or ended with a tool call.
    /// </returns>
    public static JevResult? GetJevResult(this ChatResponse response)
    {
        _ = Throw.IfNull(response);
        return response.RawRepresentation as JevResult ?? FromMessages(response.Messages);
    }

    /// <summary>
    /// Gets the typed answers of an agent response produced with a <see cref="JevChatClient"/>.
    /// </summary>
    /// <param name="response">The agent response.</param>
    /// <returns>
    /// The answers to the run's questions, with their probabilities and token usage, or <see langword="null"/> when
    /// the response has none.
    /// </returns>
    public static JevResult? GetJevResult(this AgentResponse response)
    {
        _ = Throw.IfNull(response);

        // A chat client agent keeps the chat response as the raw representation; agents that rebuild the response
        // still keep the messages, which carry the result too.
        return response.RawRepresentation switch
        {
            JevResult result => result,
            ChatResponse chatResponse => chatResponse.GetJevResult(),
            _ => FromMessages(response.Messages),
        };
    }

    private static JevResult? FromMessages(IList<ChatMessage> messages)
    {
        for (int index = messages.Count - 1; index >= 0; index--)
        {
            if (messages[index].RawRepresentation is JevResult result)
            {
                return result;
            }
        }

        return null;
    }
}
