// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Provides extension methods for mapping OpenAI capabilities to an <see cref="AIAgent"/>.
/// </summary>
public static partial class EndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="agentName">The name of the AI agent service registered in the dependency injection container. This name is used to resolve the <see cref="AIAgent"/> instance from the keyed services.</param>
    /// <param name="responsesPath">Custom route path for the responses endpoint.</param>
    /// <param name="conversationsPath">Custom route path for the conversations endpoint.</param>
    public static void MapOpenAIResponses(
        this IEndpointRouteBuilder endpoints,
        string agentName,
        [StringSyntax("Route")] string? responsesPath = null,
        [StringSyntax("Route")] string? conversationsPath = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentName);
        if (responsesPath is null || conversationsPath is null)
        {
            ValidateAgentName(agentName);
        }

        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);

        responsesPath ??= $"/{agentName}/v1/responses";
        var responsesRouteGroup = endpoints.MapGroup(responsesPath);
        MapResponses(responsesRouteGroup, agent);

        // Will be included once we obtain the API to operate with thread (conversation).

        // conversationsPath ??= $"/{agentName}/v1/conversations";
        // var conversationsRouteGroup = endpoints.MapGroup(conversationsPath);
        // MapConversations(conversationsRouteGroup, agent, loggerFactory);
    }

    private static void MapResponses(IEndpointRouteBuilder routeGroup, AIAgent agent)
    {
        var endpointAgentName = agent.DisplayName;
        var responsesProcessor = new AIAgentResponsesProcessor(agent);

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
    private static void MapConversations(IEndpointRouteBuilder routeGroup, AIAgent agent)
#pragma warning restore IDE0051 // Remove unused private members
    {
        var endpointAgentName = agent.DisplayName;
        var conversationsProcessor = new AIAgentConversationsProcessor(agent);

        routeGroup.MapGet("/{conversation_id}", (string conversationId, CancellationToken cancellationToken)
            => conversationsProcessor.GetConversationAsync(conversationId, cancellationToken)
        ).WithName(endpointAgentName + "/RetrieveConversation");
    }

    private static void ValidateAgentName([NotNull] string agentName)
    {
        var escaped = Uri.EscapeDataString(agentName);
        if (!string.Equals(escaped, agentName, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException($"Agent name '{agentName}' contains characters invalid for URL routes.", nameof(agentName));
        }
    }
}
