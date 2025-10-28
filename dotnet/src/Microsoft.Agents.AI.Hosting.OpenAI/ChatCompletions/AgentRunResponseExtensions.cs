// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;

/// <summary>
/// Extension methods for converting agent responses to ChatCompletion models.
/// </summary>
internal static class AgentRunResponseExtensions
{
#pragma warning disable RCS1175 // Unused 'this' parameter
    public static ChatCompletion ToChatCompletion(this AgentRunResponse agentRunResponse, CreateChatCompletion request)
#pragma warning restore RCS1175 // Unused 'this' parameter
    {
        return new();
    }
}
