// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.OpenAI;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.AspNetCore.Builder;

public static partial class MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps OpenAI ChatCompletions API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoints to.</param>
    /// <param name="agentBuilder">The builder for <see cref="AIAgent"/> to map the OpenAI ChatCompletions endpoints for.</param>
    /// <remarks>
    /// See <see cref="MapOpenAIChatCompletions(IEndpointRouteBuilder, AIAgent, string, OpenAIChatCompletionsMapOptions)"/>
    /// for endpoint authorization and application-owned state requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIChatCompletions(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder)
        => MapOpenAIChatCompletions(endpoints, agentBuilder, path: null);

    /// <summary>
    /// Maps OpenAI ChatCompletions API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoints to.</param>
    /// <param name="agentBuilder">The builder for <see cref="AIAgent"/> to map the OpenAI ChatCompletions endpoints for.</param>
    /// <param name="path">Custom route path for the chat completions endpoint.</param>
    /// <param name="mapOptions">Optional options controlling how incoming requests are mapped onto the agent run.</param>
    /// <remarks>
    /// Singleton registrations are resolved once when the endpoint is mapped. Scoped and transient registrations are
    /// resolved from <see cref="HttpContext.RequestServices"/> for each request, so their configured DI lifetime is honored.
    /// See <see cref="MapOpenAIChatCompletions(IEndpointRouteBuilder, AIAgent, string, OpenAIChatCompletionsMapOptions)"/>
    /// for endpoint authorization and application-owned state requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIChatCompletions(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string? path, OpenAIChatCompletionsMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentBuilder);

        string agentName = agentBuilder.Name;
        ValidateAgentName(agentName);
        HostedAgentResolution.EnsureAgentRegistered(endpoints.ServiceProvider, agentName);

        Func<HttpContext, AIAgent?> agentResolver;
        if (agentBuilder.Lifetime == ServiceLifetime.Singleton)
        {
            var agent = endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName);
            agentResolver = _ => agent;
        }
        else
        {
            agentResolver = context => context.RequestServices.GetRequiredKeyedService<AIAgent>(agentName);
        }

        path ??= $"/{agentName}/v1/chat/completions";
        return MapOpenAIChatCompletionsCore(
            endpoints,
            path,
            agentName + "/CreateChatCompletion",
            agentResolver,
            mapOptions);
    }

    /// <summary>
    /// Maps OpenAI ChatCompletions API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the OpenAI ChatCompletions endpoints for.</param>
    /// <remarks>
    /// See <see cref="MapOpenAIChatCompletions(IEndpointRouteBuilder, AIAgent, string, OpenAIChatCompletionsMapOptions)"/>
    /// for endpoint authorization and application-owned state requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIChatCompletions(this IEndpointRouteBuilder endpoints, AIAgent agent)
        => MapOpenAIChatCompletions(endpoints, agent, path: null);

    /// <summary>
    /// Maps OpenAI ChatCompletions API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the OpenAI ChatCompletions endpoints for.</param>
    /// <param name="path">Custom route path for the chat completions endpoint.</param>
    /// <param name="mapOptions">Optional options controlling how incoming requests are mapped onto the agent run.</param>
    /// <remarks>
    /// Configure authentication and enforce endpoint authorization, for example with
    /// <c>RequireAuthorization()</c> on the returned builder. This method does not apply authorization
    /// automatically. The adapter does not itself persist conversations across requests, but callers
    /// can still consume model resources and invoke exposed tools. Any additional application-owned
    /// memory or storage must be isolated separately; registering an <c>AgentIsolationKeyProvider</c>
    /// does not automatically partition arbitrary agent or tool state.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIChatCompletions(
        this IEndpointRouteBuilder endpoints,
        AIAgent agent,
        [StringSyntax("Route")] string? path,
        OpenAIChatCompletionsMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent.Name));
        ValidateAgentName(agent.Name);

        path ??= $"/{agent.Name}/v1/chat/completions";
        return MapOpenAIChatCompletionsCore(endpoints, path, agent.Name + "/CreateChatCompletion", _ => agent, mapOptions);
    }

    /// <summary>
    /// Maps an OpenAI ChatCompletions API endpoint that selects the <see cref="AIAgent"/> to invoke for each request.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI ChatCompletions endpoint to.</param>
    /// <param name="path">The route path for the chat completions endpoint.</param>
    /// <param name="agentSelector">
    /// A delegate invoked once per request that returns the agent to invoke, or <see langword="null"/> when
    /// no agent matches the request. The delegate can use route values, claims, headers, and
    /// <see cref="HttpContext.RequestServices"/> to select or resolve the agent.
    /// </param>
    /// <param name="mapOptions">Optional options controlling how incoming requests are mapped onto the agent run.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// When <paramref name="agentSelector"/> returns <see langword="null"/>, the endpoint responds with
    /// <c>404 Not Found</c>. The selected agent must have a non-empty <see cref="AIAgent.Name"/>, which is its
    /// stable logical identity. Selection is not an authorization boundary; see
    /// <see cref="MapOpenAIChatCompletions(IEndpointRouteBuilder, AIAgent, string, OpenAIChatCompletionsMapOptions)"/>
    /// for endpoint authorization and application-owned state requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIChatCompletions(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("Route")] string path,
        Func<HttpContext, AIAgent?> agentSelector,
        OpenAIChatCompletionsMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        ArgumentNullException.ThrowIfNull(agentSelector);

        return MapOpenAIChatCompletionsCore(
            endpoints,
            path,
            endpointName: null,
            context =>
            {
                if (agentSelector(context) is not { } agent)
                {
                    return null;
                }

                _ = HostedAgentResolution.GetSelectedAgentName(agent);
                return agent;
            },
            mapOptions);
    }

    private static RouteGroupBuilder MapOpenAIChatCompletionsCore(
        IEndpointRouteBuilder endpoints,
        string path,
        string? endpointName,
        Func<HttpContext, AIAgent?> agentResolver,
        OpenAIChatCompletionsMapOptions? mapOptions)
    {
        var group = endpoints.MapGroup(path);

        var endpoint = group.MapPost("/", async ([FromBody] CreateChatCompletion request, HttpContext context, CancellationToken cancellationToken) =>
        {
            if (agentResolver(context) is not { } agent)
            {
                return Results.NotFound(new ErrorResponse
                {
                    Error = new ErrorDetails
                    {
                        Message = "No agent matches the request.",
                        Type = "invalid_request_error",
                        Code = "agent_not_found"
                    }
                });
            }

            return await AIAgentChatCompletionsProcessor.CreateChatCompletionAsync(agent, request, mapOptions, cancellationToken).ConfigureAwait(false);
        });

        if (endpointName is not null)
        {
            endpoint.WithName(endpointName);
        }

        MarkFeatureUsed();
        return group;
    }
}
