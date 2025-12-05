// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using Microsoft.Shared.Diagnostics;
using OpenAI.Chat;
using OpenAI.Responses;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for <see cref="AgentRunResponse"/> and <see cref="AgentRunResponseUpdate"/> instances to
/// create or extract native OpenAI response objects from the Microsoft Agent Framework responses.
/// </summary>
public static class AgentRunResponseExtensions
{
    /// <summary>
    /// Creates or extracts a native OpenAI <see cref="ChatCompletion"/> object from an <see cref="AgentRunResponse"/>.
    /// </summary>
    /// <param name="response">The agent response.</param>
    /// <returns>The OpenAI <see cref="ChatCompletion"/> object.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    public static ChatCompletion AsOpenAIChatCompletion(this AgentRunResponse response)
    {
        Throw.IfNull(response);

        return
            response.RawRepresentation as ChatCompletion ??
            response.AsChatResponse().AsOpenAIChatCompletion();
    }

    /// <summary>
    /// Creates or extracts a native OpenAI <see cref="OpenAIResponse"/> object from an <see cref="AgentRunResponse"/>.
    /// </summary>
    /// <param name="response">The agent response.</param>
    /// <returns>The OpenAI <see cref="OpenAIResponse"/> object.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="response"/> is <see langword="null"/>.</exception>
    public static OpenAIResponse AsOpenAIResponse(this AgentRunResponse response)
    {
        Throw.IfNull(response);

        return
            response.RawRepresentation as OpenAIResponse ??
            response.AsChatResponse().AsOpenAIResponse();
    }
}
