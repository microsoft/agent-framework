using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

using Azure.AI.AgentsHosting.Ingress.Common;
using Azure.AI.AgentsHosting.Ingress.Common.Http.Json;
using Azure.AI.AgentsHosting.Ingress.Common.Id;
using Azure.AI.AgentsHosting.Ingress.Invocation;

using AzureAIAgents.Models;

using Microsoft.Extensions.AI;
using Microsoft.Agents.AI;

namespace Microsoft.Agents.AI.Hosting.Converters;

/// <summary>
/// Extension methods for converting agent responses to Response models.
/// </summary>
public static class ResponseConverterExtensions
{
    private static readonly JsonSerializerOptions Json = JsonExtensions.DefaultJsonSerializerOptions;

    /// <summary>
    /// Converts an AgentRunResponse to a Response model.
    /// </summary>
    /// <param name="agentRunResponse">The agent run response to convert.</param>
    /// <param name="request">The original create response request.</param>
    /// <param name="context">The agent invocation context.</param>
    /// <returns>A Response model.</returns>
    public static AzureAIAgents.Models.Response ToResponse(this AgentRunResponse agentRunResponse, CreateResponse request,
        AgentInvocationContext context)
    {
        var output = agentRunResponse.Messages
            .SelectMany(msg => msg.ToItemResource(context.IdGenerator));

        return AzureAIAgentsModelFactory.Response(
            @object: "response",
            id: context.ResponseId,
            conversationId: context.ConversationId,
            metadata: request.Metadata as IReadOnlyDictionary<string, string>,
            agent: request.Agent.ToAgentId(),
            createdAt: agentRunResponse.CreatedAt ?? DateTimeOffset.UtcNow,
            parallelToolCalls: true,
            status: ResponseStatus.Completed,
            output: output,
            usage: agentRunResponse.Usage.ToResponseUsage()
        );
    }

    /// <summary>
    /// Converts a ChatMessage to ItemResource objects.
    /// </summary>
    /// <param name="message">The chat message to convert.</param>
    /// <param name="idGenerator">The ID generator to use for creating IDs.</param>
    /// <returns>An enumerable of ItemResource objects.</returns>
    public static IEnumerable<ItemResource> ToItemResource(this ChatMessage message, IIdGenerator idGenerator)
    {
        IList<ItemContent> contents = [];
        foreach (var content in message.Contents)
        {
            switch (content)
            {
                case FunctionCallContent functionCallContent:
                    // message.Role == ChatRole.Assistant
                    yield return functionCallContent.ToFunctionToolCallItemResource(idGenerator.GenerateFunctionCallId());
                    break;
                case FunctionResultContent functionResultContent:
                    // message.Role == ChatRole.Tool
                    yield return functionResultContent.ToFunctionToolCallOutputItemResource(
                        idGenerator.GenerateFunctionOutputId());
                    break;
                default:
                    // message.Role == ChatRole.Assistant
                    var itemContent = ToItemContent(content);
                    if (itemContent != null)
                    {
                        contents.Add(itemContent);
                    }

                    break;
            }
        }

        if (contents.Count > 0)
        {
            yield return new ResponsesAssistantMessageItemResource(
                id: idGenerator.GenerateMessageId(),
                status: ResponsesMessageItemResourceStatus.Completed,
                content: contents
            );
        }
    }

    /// <summary>
    /// Converts FunctionCallContent to a FunctionToolCallItemResource.
    /// </summary>
    /// <param name="functionCallContent">The function call content to convert.</param>
    /// <param name="id">The ID to assign to the resource.</param>
    /// <returns>A FunctionToolCallItemResource.</returns>
    public static FunctionToolCallItemResource ToFunctionToolCallItemResource(
        this FunctionCallContent functionCallContent,
        string id)
    {
#pragma warning disable IL2026, IL3050 // JSON serialization requires dynamic access
        return AzureAIAgentsModelFactory.FunctionToolCallItemResource(
            id: id,
            status: FunctionToolCallItemResourceStatus.Completed,
            callId: functionCallContent.CallId,
            name: functionCallContent.Name,
            arguments: JsonSerializer.Serialize(functionCallContent.Arguments, Json)
        );
#pragma warning restore IL2026, IL3050
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
        return AzureAIAgentsModelFactory.FunctionToolCallOutputItemResource(
            id: id,
            status: FunctionToolCallOutputItemResourceStatus.Completed,
            callId: functionResultContent.CallId,
            output: output
        );
    }

    /// <summary>
    /// Converts UsageDetails to ResponseUsage.
    /// </summary>
    /// <param name="usage">The usage details to convert.</param>
    /// <returns>A ResponseUsage object, or null if usage is null.</returns>
    public static ResponseUsage? ToResponseUsage(this UsageDetails? usage)
    {
        if (usage == null)
        {
            return null;
        }

        var inputTokensDetails =
            usage.AdditionalCounts?.TryGetValue("InputTokenDetails.CachedTokenCount", out var cachedInputToken) ?? false
                ? AzureAIAgentsModelFactory.ResponseUsageInputTokensDetails((int)cachedInputToken)
                : null;
        var outputTokensDetails =
            usage.AdditionalCounts?.TryGetValue("OutputTokenDetails.ReasoningTokenCount", out var reasoningToken) ??
            false
                ? AzureAIAgentsModelFactory.ResponseUsageOutputTokensDetails((int)reasoningToken)
                : null;

        return AzureAIAgentsModelFactory.ResponseUsage(
            inputTokens: (int)(usage.InputTokenCount ?? 0),
            inputTokensDetails: inputTokensDetails,
            outputTokens: (int)(usage.OutputTokenCount ?? 0),
            outputTokensDetails: outputTokensDetails,
            totalTokens: (int)(usage.TotalTokenCount ?? 0)
        );
    }

    /// <summary>
    /// Converts AIContent to ItemContent.
    /// </summary>
    /// <param name="content">The AI content to convert.</param>
    /// <returns>An ItemContent object, or null if the content cannot be converted.</returns>
    public static ItemContent? ToItemContent(this AIContent content)
    {
        switch (content)
        {
            case TextContent textContent:
                return new ItemContentOutputText(textContent?.Text ?? string.Empty, []);
            case ErrorContent errorContent:
                var message = $"Error = \"{errorContent.Message}\"" +
                              (!string.IsNullOrWhiteSpace(errorContent.ErrorCode)
                                  ? $" ({errorContent.ErrorCode})"
                                  : string.Empty) +
                              (!string.IsNullOrWhiteSpace(errorContent.Details)
                                  ? $" - \"{errorContent.Details}\""
                                  : string.Empty);
                var error = AzureAIAgentsModelFactory.ResponseError(message: message);
                throw new AgentInvocationException(error);
            default:
                return null;
        }
    }
}
