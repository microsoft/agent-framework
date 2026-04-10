// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
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
    /// Maps an AG-UI agent endpoint and its associated approval endpoint.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="pattern">The URL pattern for the endpoint.</param>
    /// <param name="aiAgent">The agent instance.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for the mapped agent endpoint.</returns>
    public static IEndpointConventionBuilder MapAGUI(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("route")] string pattern,
        AIAgent aiAgent)
    {
        // Map the approval endpoint for human-in-the-loop tool call approvals
        string approvePattern = pattern.TrimEnd('/') + "/approve";
        endpoints.MapPost(approvePattern, (
            [FromBody] ApproveToolCallInput? input,
            HttpContext context) =>
        {
            if (input is null || string.IsNullOrEmpty(input.RequestId))
            {
                Trace.TraceWarning("[AGUI-HITL] /approve called with missing requestId");
                return Results.BadRequest("requestId is required.");
            }

            Trace.TraceInformation("[AGUI-HITL] /approve received: RequestId={0}, Approved={1}", input.RequestId, input.Approved);

            var store = context.RequestServices.GetRequiredService<PendingApprovalStore>();
            if (store.TryComplete(input.RequestId, input.Approved))
            {
                Trace.TraceInformation("[AGUI-HITL] /approve resolved: RequestId={0}", input.RequestId);
                return Results.Ok();
            }

            Trace.TraceWarning("[AGUI-HITL] /approve not found: RequestId={0}", input.RequestId);
            return Results.NotFound($"No pending approval found for request ID '{input.RequestId}'.");
        });

        // Map the main AG-UI agent endpoint
        return endpoints.MapPost(pattern, async ([FromBody] RunAgentInput? input, HttpContext context, CancellationToken cancellationToken) =>
        {
            if (input is null)
            {
                return Results.BadRequest();
            }

            var jsonOptions = context.RequestServices.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>();
            var jsonSerializerOptions = jsonOptions.Value.SerializerOptions;

            var messages = input.Messages.AsChatMessages(jsonSerializerOptions);
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
                },
                // Pass the PendingApprovalStore so agents can use it for HITL blocking
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    ["ag_ui_pending_approval_store"] = CreateApprovalRegistrationDelegate(context.RequestServices)
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

    private static Func<string, Task<bool>> CreateApprovalRegistrationDelegate(IServiceProvider services)
    {
        var store = services.GetRequiredService<PendingApprovalStore>();
        var aguiOptions = services.GetRequiredService<IOptions<AGUIOptions>>().Value;
        return (requestId) => store.RegisterAsync(requestId, aguiOptions.ApprovalTimeout);
    }
}

/// <summary>
/// Input model for the AG-UI tool call approval endpoint.
/// </summary>
internal sealed class ApproveToolCallInput
{
    [JsonPropertyName("requestId")]
    public string RequestId { get; set; } = string.Empty;

    [JsonPropertyName("approved")]
    public bool Approved { get; set; }
}
