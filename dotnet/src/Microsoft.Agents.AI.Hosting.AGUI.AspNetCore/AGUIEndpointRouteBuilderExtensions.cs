// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
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
using Microsoft.Agents.AI.Hosting;

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
            var sessionStore = context.RequestServices.GetRequiredService<AgentSessionStore>();

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
                }
            };

            AgentSession? session = await GetOrCreateSessionAsync(aiAgent, input.ThreadId, sessionStore, cancellationToken).ConfigureAwait(false);

            // Run the agent and convert to AG-UI events
            var events = RunStreamingWithSessionPersistenceAsync(
                aiAgent,
                messages,
                runOptions,
                session,
                input.ThreadId,
                sessionStore,
                cancellationToken)
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

    private static async ValueTask<AgentSession?> GetOrCreateSessionAsync(
        AIAgent aiAgent,
        string? threadId,
        AgentSessionStore sessionStore,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(threadId))
        {
            return null;
        }

        return await sessionStore.GetSessionAsync(aiAgent, threadId, cancellationToken).ConfigureAwait(false);
    }

    private static async ValueTask PersistSessionAsync(
        AIAgent aiAgent,
        string? threadId,
        AgentSession? session,
        AgentSessionStore sessionStore,
        CancellationToken cancellationToken)
    {
        if (session is null || string.IsNullOrWhiteSpace(threadId))
        {
            return;
        }

        await sessionStore.SaveSessionAsync(aiAgent, threadId, session, cancellationToken).ConfigureAwait(false);
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> RunStreamingWithSessionPersistenceAsync(
        AIAgent aiAgent,
        IEnumerable<ChatMessage> messages,
        AgentRunOptions runOptions,
        AgentSession? session,
        string? threadId,
        AgentSessionStore sessionStore,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        try
        {
            await foreach (AgentResponseUpdate update in aiAgent.RunStreamingAsync(
                messages,
                session,
                runOptions,
                CancellationToken.None).ConfigureAwait(false))
            {
                yield return update;
            }
        }
        finally
        {
            await PersistSessionAsync(aiAgent, threadId, session, sessionStore, cancellationToken).ConfigureAwait(false);
        }
    }
}
