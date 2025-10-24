// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.AspNetCore.Builder;

/// <summary>
/// Provides extension methods for mapping OpenAI capabilities to an <see cref="AIAgent"/>.
/// </summary>
public static partial class MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the OpenAI Responses endpoints for.</param>
    public static IEndpointConventionBuilder MapOpenAIResponses(this IEndpointRouteBuilder endpoints, AIAgent agent) =>
        MapOpenAIResponses(endpoints, agent, responsesPath: null);

    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the OpenAI Responses endpoints for.</param>
    /// <param name="responsesPath">Custom route path for the responses endpoint.</param>
    public static IEndpointConventionBuilder MapOpenAIResponses(
        this IEndpointRouteBuilder endpoints,
        AIAgent agent,
        [StringSyntax("Route")] string? responsesPath)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent.Name));
        ValidateAgentName(agent.Name);

        responsesPath ??= $"/{agent.Name}/v1/responses";
        var group = endpoints.MapGroup(responsesPath);
        var endpointAgentName = agent.DisplayName;
        group.MapPost("/", async ([FromBody] CreateResponse createResponse, CancellationToken cancellationToken)
            => await AIAgentResponsesProcessor.CreateModelResponseAsync(agent, createResponse, cancellationToken).ConfigureAwait(false))
            .WithName(endpointAgentName + "/CreateResponse");
        return group;
    }

    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    public static IEndpointConventionBuilder MapOpenAIResponses(this IEndpointRouteBuilder endpoints) =>
        MapOpenAIResponses(endpoints, responsesPath: null);

    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="responsesPath">Custom route path for the responses endpoint.</param>
    public static IEndpointConventionBuilder MapOpenAIResponses(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("Route")] string? responsesPath)
    {
        ArgumentNullException.ThrowIfNull(endpoints);

        responsesPath ??= "/v1/responses";
        var group = endpoints.MapGroup(responsesPath);
        group.MapPost("/", async ([FromBody] CreateResponse createResponse, IServiceProvider serviceProvider, CancellationToken cancellationToken) =>
        {
            // DevUI uses the 'model' field to specify the agent name.
            var agentName = createResponse.Agent?.Name ?? createResponse.Model;
            if (agentName is null)
            {
                return Results.BadRequest("No 'agent.name' or 'model' specified in the request.");
            }

            var agent = serviceProvider.GetKeyedService<AIAgent>(agentName);
            if (agent is null)
            {
                return Results.NotFound($"Agent named '{agentName}' was not found.");
            }

            return await AIAgentResponsesProcessor.CreateModelResponseAsync(agent, createResponse, cancellationToken).ConfigureAwait(false);
        }).WithName("CreateResponse");
        return group;
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
