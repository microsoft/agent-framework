// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.OpenAI;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.AspNetCore.Builder;

/// <summary>
/// Provides extension methods for mapping OpenAI capabilities to an <see cref="AIAgent"/>.
/// </summary>
public static partial class MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="IHostedAgentBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="agentBuilder">The builder for <see cref="AIAgent"/> to map the OpenAI Responses endpoints for.</param>
    public static IEndpointConventionBuilder MapOpenAIResponses(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder)
        => MapOpenAIResponses(endpoints, agentBuilder, path: null);

    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="IHostedAgentBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="agentBuilder">The builder for <see cref="AIAgent"/> to map the OpenAI Responses endpoints for.</param>
    /// <param name="path">Custom route path for the OpenAI Responses endpoint.</param>
    public static IEndpointConventionBuilder MapOpenAIResponses(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string? path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentBuilder);

        var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentBuilder.Name);
        return MapOpenAIResponses(endpoints, agent, path);
    }

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

        // Create an executor for this agent
        var executor = new AIAgentResponseExecutor(agent);
        var storageOptions = endpoints.ServiceProvider.GetService<InMemoryStorageOptions>() ?? new InMemoryStorageOptions();
        var conversationStorage = endpoints.ServiceProvider.GetService<IConversationStorage>();
        var responsesService = new InMemoryResponsesService(executor, storageOptions, conversationStorage);

        var handlers = new ResponsesHttpHandler(responsesService);

        var group = endpoints.MapGroup(responsesPath);
        var endpointAgentName = agent.DisplayName;

        // Create response endpoint
        group.MapPost("/", handlers.CreateResponseAsync)
            .WithName(endpointAgentName + "/CreateResponse")
            .WithSummary("Creates a model response for the given input");

        // Get response endpoint
        group.MapGet("{responseId}", handlers.GetResponseAsync)
            .WithName(endpointAgentName + "/GetResponse")
            .WithSummary("Retrieves a response by ID");

        // Cancel response endpoint
        group.MapPost("{responseId}/cancel", handlers.CancelResponseAsync)
            .WithName(endpointAgentName + "/CancelResponse")
            .WithSummary("Cancels an in-progress response");

        // Delete response endpoint
        group.MapDelete("{responseId}", handlers.DeleteResponseAsync)
            .WithName(endpointAgentName + "/DeleteResponse")
            .WithSummary("Deletes a response");

        // List response input items endpoint
        group.MapGet("{responseId}/input_items", handlers.ListResponseInputItemsAsync)
            .WithName(endpointAgentName + "/ListResponseInputItems")
            .WithSummary("Lists the input items for a response");

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
        var responsesService = endpoints.ServiceProvider.GetService<IResponsesService>()
            ?? throw new InvalidOperationException("IResponsesService is not registered. Call AddOpenAIResponses() in your service configuration.");
        var handlers = new ResponsesHttpHandler(responsesService);

        var group = endpoints.MapGroup(responsesPath);

        // Create response endpoint
        group.MapPost("/", handlers.CreateResponseAsync)
            .WithName("CreateResponse")
            .WithSummary("Creates a model response for the given input");

        // Get response endpoint
        group.MapGet("{responseId}", handlers.GetResponseAsync)
            .WithName("GetResponse")
            .WithSummary("Retrieves a response by ID");

        // Cancel response endpoint
        group.MapPost("{responseId}/cancel", handlers.CancelResponseAsync)
            .WithName("CancelResponse")
            .WithSummary("Cancels an in-progress response");

        // Delete response endpoint
        group.MapDelete("{responseId}", handlers.DeleteResponseAsync)
            .WithName("DeleteResponse")
            .WithSummary("Deletes a response");

        // List response input items endpoint
        group.MapGet("{responseId}/input_items", handlers.ListResponseInputItemsAsync)
            .WithName("ListResponseInputItems")
            .WithSummary("Lists the input items for a response");

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
