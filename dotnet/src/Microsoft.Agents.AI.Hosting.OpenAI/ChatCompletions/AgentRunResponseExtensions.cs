// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.VisualBasic;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;

/// <summary>
/// Extension methods for converting agent responses to ChatCompletion models.
/// </summary>
internal static class AgentRunResponseExtensions
{
    public static ChatCompletion ToChatCompletion(this AgentRunResponse agentRunResponse, CreateChatCompletion request)
    {
        IList<ChatCompletionChoice> choices = agentRunResponse.ToChoices();

        return new ChatCompletion
        {
            Id = agentRunResponse.ResponseId!, // TODO generate an ID here if missing
            Choices = choices,
            Created = (agentRunResponse.CreatedAt ?? DateTimeOffset.UtcNow).ToUnixTimeSeconds(),
            Model = /* request.Agent?.Name ?? */ request.Model,
            Usage = agentRunResponse.Usage.ToCompletionUsage(),
            ServiceTier = request.ServiceTier ?? "default",
            // SystemFingerprint = ...
        };
    }

    public static List<ChatCompletionChoice> ToChoices(this AgentRunResponse agentRunResponse)
    {
        var chatCompletionChoices = new List<ChatCompletionChoice>();
        var index = 0;

        foreach (var message in agentRunResponse.Messages)
        {
            foreach (var content in message.Contents)
            {
                ChatCompletionChoice? choice = content switch
                {
                    // text
                    TextContent textContent => new() { Index = index, Message = ChoiceMessage.FromText(role: message.Role, textContent.Text) },
                    _ => null
                };

                if (choice is null)
                {
                    throw new ArgumentOutOfRangeException($"Got unsupported content: {content.GetType()}");
                }

                switch (content)
                {
                    case FunctionCallContent functionCallContent:
                        // message.Role == ChatRole.Assistant
                        yield return functionCallContent.ToFunctionToolCallItemResource(idGenerator.GenerateFunctionCallId(), jsonSerializerOptions);
                        break;
                    case FunctionResultContent functionResultContent:
                        // message.Role == ChatRole.Tool
                        yield return functionResultContent.ToFunctionToolCallOutputItemResource(
                            idGenerator.GenerateFunctionOutputId());
                        break;
                    default:
                        // message.Role == ChatRole.Assistant
                        if (ItemContentConverter.ToItemContent(content) is { } itemContent)
                        {
                            contents.Add(itemContent);
                        }

                        break;
                }
            }
        }
    }

    /// <summary>
    /// Converts UsageDetails to ResponseUsage.
    /// </summary>
    /// <param name="usage">The usage details to convert.</param>
    /// <returns>A ResponseUsage object with zeros if usage is null.</returns>
    public static CompletionUsage ToCompletionUsage(this UsageDetails? usage)
    {
        if (usage == null)
        {
            return CompletionUsage.Zero;
        }

        var cachedTokens = usage.AdditionalCounts?.TryGetValue("InputTokenDetails.CachedTokenCount", out var cachedInputToken) ?? false
            ? (int)cachedInputToken
            : 0;
        var reasoningTokens =
            usage.AdditionalCounts?.TryGetValue("OutputTokenDetails.ReasoningTokenCount", out var reasoningToken) ?? false
                ? (int)reasoningToken
                : 0;

        return new CompletionUsage
        {
            PromptTokens = (int)(usage.InputTokenCount ?? 0),
            PromptTokensDetails = new() { CachedTokens = cachedTokens },
            CompletionTokens = (int)(usage.OutputTokenCount ?? 0),
            CompletionTokensDetails = new() { ReasoningTokens = reasoningTokens },
            TotalTokens = (int)(usage.TotalTokenCount ?? 0)
        };
    }
}
