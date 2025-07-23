// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenAI.Chat;
using OpenAI.Responses;

namespace OpenAI;

/// <summary>
/// Extension methods for <see cref="AgentRunResponse"/>
/// </summary>
internal static class AgentRunResponseExtensions
{
    internal static ChatCompletion AsChatCompletion(this AgentRunResponse agentResponse)
    {
        if (agentResponse.RawRepresentation is ChatCompletion chatCompletion)
        {
            return chatCompletion;
        }
        throw new ArgumentException("ChatResponse.RawRepresentation must be a ChatCompletion");
    }

    internal static OpenAIResponse AsOpenAIResponse(this AgentRunResponse agentResponse)
    {
        if (agentResponse.RawRepresentation is ChatResponse chatResponse)
        {
            if (chatResponse.RawRepresentation is OpenAIResponse openAIResponse)
            {
                return openAIResponse;
            }
            throw new ArgumentException("ChatResponse.RawRepresentation must be a ChatCompletion");
        }
        throw new ArgumentException("AgentRunResponse.RawRepresentation must be a OpenAIResponse");
    }
}
