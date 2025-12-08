// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Threading;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Provides extension methods for mapping AG-UI agents to ASP.NET Core endpoints.
/// </summary>
public static class AGUIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps an AG-UI agent endpoint.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <param name="aiAgent">The agent instance.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        AIAgent aiAgent)
    {
        return endpoints.MapPost(pattern, async ([FromBody] RunAgentInput? input, HttpContext context, CancellationToken cancellationToken) =>
        {
            if (input is null)
            {
                return Results.BadRequest();
            }

            var jsonOptions = context.RequestServices.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>();
            var jsonSerializerOptions = jsonOptions.Value.SerializerOptions;

            // Normalize assistant/tool ordering before we map to ChatMessage
            var aguiMessages = input.Messages?.ToList() ?? new List<AGUIMessage>();
            FixToolMessageOrdering(aguiMessages);

            var messages = aguiMessages.AsChatMessages(jsonSerializerOptions);
            var clientTools = input.Tools?.AsAITools().ToList();

            // Create run options with AG-UI context in AdditionalProperties
            var runOptions = new ChatClientAgentRunOptions
            {
                ChatOptions = new ChatOptions
                {
                    Tools = clientTools,
                    AdditionalProperties = new AdditionalPropertiesDictionary
                    {
                        ["ag_ui_state"] = input.State,
                        ["ag_ui_context"] = input.Context?.Select(c => new KeyValuePair<string, string>(c.Description, c.Value)).ToArray(),
                        ["ag_ui_forwarded_properties"] = input.ForwardedProperties,
                        ["ag_ui_thread_id"] = input.ThreadId,
                        ["ag_ui_run_id"] = input.RunId
                    }
                }
            };

            // Run the agent and convert to AG-UI events
            var events = aiAgent.RunStreamingAsync(
                messages,
                options: runOptions,
                cancellationToken: cancellationToken)
                .AsChatResponseUpdatesAsync()
                .FilterServerToolsFromMixedToolInvocationsAsync(clientTools, cancellationToken)
                .AsAGUIEventStreamAsync(
                    input.ThreadId,
                    input.RunId,
                    jsonSerializerOptions,
                    cancellationToken);

            var sseLogger = context.RequestServices.GetRequiredService<ILogger<AGUIServerSentEventsResult>>();
            return new AGUIServerSentEventsResult(events, sseLogger);
        });
    }

    private static void FixToolMessageOrdering(List<AGUIMessage> messages)
    {
        if (messages == null || messages.Count == 0)
        {
            return;
        }

        // Collect all tool messages by ToolCallId
        var toolsByCallId = new Dictionary<string, Queue<AGUIToolMessage>>();
        var toolsWithoutCallId = new List<AGUIToolMessage>();

        foreach (var msg in messages)
        {
            if (msg is AGUIToolMessage toolMsg)
            {
                if (!string.IsNullOrWhiteSpace(toolMsg.ToolCallId))
                {
                    if (!toolsByCallId.TryGetValue(toolMsg.ToolCallId, out var queue))
                    {
                        queue = new Queue<AGUIToolMessage>();
                        toolsByCallId[toolMsg.ToolCallId] = queue;
                    }

                    queue.Enqueue(toolMsg);
                }
                else
                {
                    toolsWithoutCallId.Add(toolMsg);
                }
            }
        }

        var reordered = new List<AGUIMessage>(messages.Count);

        foreach (var msg in messages)
        {
            // Reinsert tool messages next to their assistant, so skip them in this pass.
            if (msg is AGUIToolMessage)
            {
                continue;
            }

            reordered.Add(msg);

            if (msg is AGUIAssistantMessage assistant &&
                assistant.ToolCalls is { Length: > 0 })
            {
                // For each tool call in this assistant message, append
                // the corresponding tool result message(s) immediately after.
                foreach (var toolCall in assistant.ToolCalls)
                {
                    if (toolCall?.Id is null)
                    {
                        continue;
                    }

                    if (toolsByCallId.TryGetValue(toolCall.Id, out var queue))
                    {
                        while (queue.Count > 0)
                        {
                            var toolMsg = queue.Dequeue();
                            reordered.Add(toolMsg);
                        }

                        toolsByCallId.Remove(toolCall.Id);
                    }
                }
            }
        }

        // Any remaining tool messages (without matching assistant toolCalls)
        // are appended at the end so nothing is lost.
        foreach (var remainingQueue in toolsByCallId.Values)
        {
            while (remainingQueue.Count > 0)
            {
                reordered.Add(remainingQueue.Dequeue());
            }
        }

        foreach (var toolMsg in toolsWithoutCallId)
        {
            reordered.Add(toolMsg);
        }

        // Replace the original list contents
        messages.Clear();
        foreach (var msg in reordered)
        {
            messages.Add(msg);
        }
    }
}
