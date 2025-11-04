// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

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
            var logger = context.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("MapAGUI");

            if (input is null)
            {
                return Results.BadRequest();
            }

            var messages = input.Messages.AsChatMessages(AGUIJsonSerializerContext.Default.Options);
            logger.LogInformation("[MapAGUI] Received request - ThreadId: {ThreadId}, RunId: {RunId}, MessageCount: {MessageCount}",
                input.ThreadId, input.RunId, messages.Count());

            for (int i = 0; i < messages.Count(); i++)
            {
                var msg = messages.ElementAt(i);
                logger.LogDebug("[MapAGUI]   Message[{Index}]: Role={Role}, ContentCount={ContentCount}",
                    i, msg.Role.Value, msg.Contents.Count);

                foreach (var content in msg.Contents)
                {
                    if (content is FunctionCallContent fcc)
                    {
                        logger.LogDebug("[MapAGUI]     - FunctionCallContent: Name={Name}, CallId={CallId}",
                            fcc.Name, fcc.CallId);
                    }
                    else if (content is FunctionResultContent frc)
                    {
                        logger.LogDebug("[MapAGUI]     - FunctionResultContent: CallId={CallId}, Result={Result}",
                            frc.CallId, frc.Result);
                    }
                    else
                    {
                        logger.LogDebug("[MapAGUI]     - {ContentType}", content.GetType().Name);
                    }
                }
            }

            var agent = aiAgent;

            logger.LogInformation("[MapAGUI] Starting agent.RunStreamingAsync for ThreadId: {ThreadId}, RunId: {RunId}",
                input.ThreadId, input.RunId);

            var events = agent.RunStreamingAsync(
                messages,
                cancellationToken: cancellationToken)
                .AsChatResponseUpdatesAsync()
                .AsAGUIEventStreamAsync(
                    input.ThreadId,
                    input.RunId,
                    cancellationToken);

            var sseLogger = context.RequestServices.GetRequiredService<ILogger<AGUIServerSentEventsResult>>();
            await new AGUIServerSentEventsResult(events, sseLogger).ExecuteAsync(context).ConfigureAwait(false);
        });
    }
}
