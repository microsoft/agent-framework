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

public static class ResponseConverterExtensions
{
    private static readonly JsonSerializerOptions Json = JsonExtensions.DefaultJsonSerializerOptions;

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

    public static FunctionToolCallItemResource ToFunctionToolCallItemResource(
        this FunctionCallContent functionCallContent,
        string id)
    {
        return AzureAIAgentsModelFactory.FunctionToolCallItemResource(
            id: id,
            status: FunctionToolCallItemResourceStatus.Completed,
            callId: functionCallContent.CallId,
            name: functionCallContent.Name,
            arguments: JsonSerializer.Serialize(functionCallContent.Arguments, Json)
        );
    }

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
