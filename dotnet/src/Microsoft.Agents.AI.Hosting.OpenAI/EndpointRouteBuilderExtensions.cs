// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Internal;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Provides extension methods for mapping OpenAI Responses capabilities to an <see cref="AIAgent"/>.
/// </summary>
public static class EndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps OpenAI Responses endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints"></param>
    /// <param name="agentName"></param>
    /// <param name="responsesPath"></param>
    /// <param name="conversationsPath"></param>
    public static void MapOpenAIResponses(
        this IEndpointRouteBuilder endpoints,
        string agentName,
        [StringSyntax("Route")] string? responsesPath = null,
        [StringSyntax("Route")] string? conversationsPath = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentName);

        var loggerFactory = endpoints.ServiceProvider.GetService<ILoggerFactory>();
        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);

        responsesPath ??= $"/{agentName}/v1/responses";
        var responsesRouteGroup = endpoints.MapGroup(responsesPath);
        MapResponses(responsesRouteGroup, agent, loggerFactory);

        // Will be included once we obtain the API to operate with thread (conversation).

        // conversationsPath ??= $"/{agentName}/v1/conversations";
        // var conversationsRouteGroup = endpoints.MapGroup(conversationsPath);
        // MapConversations(conversationsRouteGroup, agent, loggerFactory);
    }

    private static void MapResponses(IEndpointRouteBuilder routeGroup, AIAgent agent, ILoggerFactory? loggerFactory)
    {
        var endpointAgentName = agent.DisplayName;
        var responsesProcessor = new AIAgentResponsesProcessor(agent, loggerFactory);

        routeGroup.MapPost("/", async (HttpContext requestContext, CancellationToken cancellationToken) =>
        {
            var requestBinary = await BinaryData.FromStreamAsync(requestContext.Request.Body, cancellationToken).ConfigureAwait(false);

            var responseOptions = new ResponseCreationOptions();
            var responseOptionsJsonModel = responseOptions as IJsonModel<ResponseCreationOptions>;
            Debug.Assert(responseOptionsJsonModel is not null);

            responseOptions = responseOptionsJsonModel.Create(requestBinary, ModelReaderWriterOptions.Json);
            if (responseOptions is null)
            {
                return Results.BadRequest("Invalid request payload.");
            }

            return await responsesProcessor.CreateModelResponseAsync(responseOptions, cancellationToken).ConfigureAwait(false);
        }).WithName(endpointAgentName + "/CreateResponse");
    }

#pragma warning disable IDE0051 // Remove unused private members
    private static void MapConversations(IEndpointRouteBuilder routeGroup, AIAgent agent, ILoggerFactory? loggerFactory)
#pragma warning restore IDE0051 // Remove unused private members
    {
        var endpointAgentName = agent.DisplayName;
        var conversationsProcessor = new AIAgentConversationsProcessor(agent, loggerFactory);

        routeGroup.MapGet("/{conversation_id}", (string conversationId, CancellationToken cancellationToken)
            => conversationsProcessor.GetConversationAsync(conversationId, cancellationToken)
        ).WithName(endpointAgentName + "/RetrieveConversation");
    }
}
