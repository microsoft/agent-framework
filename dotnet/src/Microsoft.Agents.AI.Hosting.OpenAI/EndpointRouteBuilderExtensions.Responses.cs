// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;

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
    }

    private static void MapResponses(IEndpointRouteBuilder routeGroup, AIAgent agent)
    {
        var endpointAgentName = agent.DisplayName;

        routeGroup.MapPost("/", async ([FromBody] CreateResponse createResponse, CancellationToken cancellationToken)
            => await AIAgentResponsesProcessor.CreateModelResponseAsync(agent, createResponse, cancellationToken).ConfigureAwait(false))
            .WithName(endpointAgentName + "/CreateResponse");
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
