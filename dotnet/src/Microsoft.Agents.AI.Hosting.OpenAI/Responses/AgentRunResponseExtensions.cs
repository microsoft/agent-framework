// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Extension methods for converting agent responses to Response models.
/// </summary>
internal static class AgentRunResponseExtensions
{
    /// <summary>
    /// Converts an AgentRunResponse to a Response model.
    /// </summary>
    /// <param name="agentRunResponse">The agent run response to convert.</param>
    /// <param name="request">The original create response request.</param>
    /// <param name="context">The agent invocation context.</param>
    /// <returns>A Response model.</returns>
    public static Response ToResponse(
        this AgentRunResponse agentRunResponse,
        CreateResponse request,
        AgentInvocationContext context)
    {
        List<ItemResource> output = [];

        // Add a reasoning item if reasoning is configured in the request
        if (request.Reasoning != null)
        {
            output.Add(new ReasoningItemResource
            {
                Id = context.IdGenerator.GenerateReasoningId(),
                Status = null
            });
        }

        output.AddRange(agentRunResponse.Messages
            .SelectMany(msg => msg.ToItemResource(context.IdGenerator, context.JsonSerializerOptions)));

        return new Response
        {
            Id = context.ResponseId,
            CreatedAt = (agentRunResponse.CreatedAt ?? DateTimeOffset.UtcNow).ToUnixTimeSeconds(),
            Model = request.Agent?.Name ?? request.Model,
            Status = ResponseStatus.Completed,
            Agent = request.Agent?.ToAgentId(),
            Conversation = request.Conversation ?? (context.ConversationId != null ? new ConversationReference { Id = context.ConversationId } : null),
            Metadata = request.Metadata is IReadOnlyDictionary<string, string> metadata ? new Dictionary<string, string>(metadata) : [],
            Instructions = request.Instructions,
            Temperature = request.Temperature ?? 1.0,
            TopP = request.TopP ?? 1.0,
            Output = output,
            Usage = agentRunResponse.Usage.ToResponseUsage(),
            ParallelToolCalls = request.ParallelToolCalls ?? true,
            Tools = [.. request.Tools ?? []],
            ToolChoice = request.ToolChoice,
            ServiceTier = request.ServiceTier ?? "default",
            Store = request.Store ?? true,
            PreviousResponseId = request.PreviousResponseId,
            Reasoning = request.Reasoning,
            Text = request.Text,
            MaxOutputTokens = request.MaxOutputTokens,
            Truncation = request.Truncation,
#pragma warning disable CS0618 // Type or member is obsolete
            User = request.User,
#pragma warning restore CS0618 // Type or member is obsolete
            PromptCacheKey = request.PromptCacheKey,
            SafetyIdentifier = request.SafetyIdentifier,
            TopLogprobs = request.TopLogprobs,
            MaxToolCalls = request.MaxToolCalls,
            Background = request.Background,
            Prompt = request.Prompt,
            Error = null
        };
    }

    /// <summary>
    /// Converts a ChatMessage to ItemResource objects.
    /// </summary>
    /// <param name="message">The chat message to convert.</param>
    /// <param name="idGenerator">The ID generator to use for creating IDs.</param>
    /// <param name="jsonSerializerOptions">The JSON serializer options to use.</param>
    /// <returns>An enumerable of ItemResource objects.</returns>
    public static IEnumerable<ItemResource> ToItemResource(this ChatMessage message, IdGenerator idGenerator, JsonSerializerOptions jsonSerializerOptions)
    {
        IList<ItemContent> contents = [];
        foreach (var content in message.Contents)
        {
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

        if (contents.Count > 0)
        {
            yield return new ResponsesAssistantMessageItemResource
            {
                Id = idGenerator.GenerateMessageId(),
                Status = ResponsesMessageItemResourceStatus.Completed,
                Content = contents
            };
        }
    }

    /// <summary>
    /// Converts FunctionCallContent to a FunctionToolCallItemResource.
    /// </summary>
    /// <param name="functionCallContent">The function call content to convert.</param>
    /// <param name="id">The ID to assign to the resource.</param>
    /// <param name="jsonSerializerOptions">The JSON serializer options to use.</param>
    /// <returns>A FunctionToolCallItemResource.</returns>
    public static FunctionToolCallItemResource ToFunctionToolCallItemResource(
        this FunctionCallContent functionCallContent,
        string id,
        JsonSerializerOptions jsonSerializerOptions)
    {
        return new FunctionToolCallItemResource
        {
            Id = id,
            Status = FunctionToolCallItemResourceStatus.Completed,
            CallId = functionCallContent.CallId,
            Name = functionCallContent.Name,
            Arguments = JsonSerializer.Serialize(functionCallContent.Arguments, jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object?>)))
        };
    }

    /// <summary>
    /// Converts FunctionResultContent to a FunctionToolCallOutputItemResource.
    /// </summary>
    /// <param name="functionResultContent">The function result content to convert.</param>
    /// <param name="id">The ID to assign to the resource.</param>
    /// <returns>A FunctionToolCallOutputItemResource.</returns>
    public static FunctionToolCallOutputItemResource ToFunctionToolCallOutputItemResource(
        this FunctionResultContent functionResultContent,
        string id)
    {
        var output = functionResultContent.Exception is not null
            ? $"{functionResultContent.Exception.GetType().Name}(\"{functionResultContent.Exception.Message}\")"
            : $"{functionResultContent.Result?.ToString() ?? "(null)"}";
        return new FunctionToolCallOutputItemResource
        {
            Id = id,
            Status = FunctionToolCallOutputItemResourceStatus.Completed,
            CallId = functionResultContent.CallId,
            Output = output
        };
    }

    /// <summary>
    /// Converts UsageDetails to ResponseUsage.
    /// </summary>
    /// <param name="usage">The usage details to convert.</param>
    /// <returns>A ResponseUsage object with zeros if usage is null.</returns>
    public static ResponseUsage ToResponseUsage(this UsageDetails? usage)
    {
        if (usage == null)
        {
            return ResponseUsage.Zero;
        }

        var cachedTokens = usage.AdditionalCounts?.TryGetValue("InputTokenDetails.CachedTokenCount", out var cachedInputToken) ?? false
            ? (int)cachedInputToken
            : 0;
        var reasoningTokens =
            usage.AdditionalCounts?.TryGetValue("OutputTokenDetails.ReasoningTokenCount", out var reasoningToken) ?? false
                ? (int)reasoningToken
                : 0;

        return new ResponseUsage
        {
            InputTokens = (int)(usage.InputTokenCount ?? 0),
            InputTokensDetails = new InputTokensDetails { CachedTokens = cachedTokens },
            OutputTokens = (int)(usage.OutputTokenCount ?? 0),
            OutputTokensDetails = new OutputTokensDetails { ReasoningTokens = reasoningTokens },
            TotalTokens = (int)(usage.TotalTokenCount ?? 0)
        };
    }
}
