// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// A generator for streaming events from MCP tool results, combining the stashed
/// <see cref="McpServerToolCallContent"/> with the <see cref="McpServerToolResultContent"/>
/// into a single <see cref="MCPCallItemResource"/> matching the OpenAI <c>mcp_call</c> spec type.
/// </summary>
internal sealed class McpCallEventGenerator(
        IdGenerator idGenerator,
        SequenceNumber seq,
        int outputIndex,
        JsonSerializerOptions jsonSerializerOptions,
        Dictionary<string, McpServerToolCallContent>? pendingMcpCalls) : StreamingEventGenerator
{
    public override bool IsSupported(AIContent content) => content is McpServerToolResultContent;

    public override IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content)
    {
        if (content is not McpServerToolResultContent mcpResult)
        {
            throw new InvalidOperationException("McpCallEventGenerator only supports McpServerToolResultContent.");
        }

        // Look up the stashed call to get name, server_label, and arguments.
        if (pendingMcpCalls?.TryGetValue(mcpResult.CallId, out var associatedCall) is not true)
        {
            throw new InvalidOperationException($"No matching McpServerToolCallContent found for CallId '{mcpResult.CallId}'.");
        }

        pendingMcpCalls.Remove(mcpResult.CallId);

        var errorContent = mcpResult.Outputs?.OfType<ErrorContent>().FirstOrDefault();
        var output = errorContent is null
            ? string.Concat(mcpResult.Outputs?.OfType<TextContent>() ?? [])
            : null;

        var item = new MCPCallItemResource
        {
            Id = idGenerator.GenerateFunctionCallId(),
            ServerLabel = associatedCall.ServerName ?? string.Empty,
            Name = associatedCall.Name,
            Arguments = associatedCall.Arguments is not null
                ? JsonSerializer.Serialize(
                    associatedCall.Arguments,
                    jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object>)))
                : string.Empty,
            Output = output,
            Error = errorContent?.Message,
        };

        yield return new StreamingOutputItemAdded
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            Item = item
        };

        yield return new StreamingOutputItemDone
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            Item = item
        };
    }

    public override IEnumerable<StreamingResponseEvent> Complete() => [];
}
