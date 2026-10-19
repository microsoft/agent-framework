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
    /// <remarks>
    /// See <see cref="MapOpenAIResponses(IEndpointRouteBuilder, string)"/> for endpoint authorization
    /// and caller isolation requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIResponses(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder)
        => MapOpenAIResponses(endpoints, agentBuilder, path: null);

    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="IHostedAgentBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="agentBuilder">The builder for <see cref="AIAgent"/> to map the OpenAI Responses endpoints for.</param>
    /// <param name="path">Custom route path for the OpenAI Responses endpoint.</param>
    /// <param name="mapOptions">Optional options controlling how incoming requests are mapped onto the agent run.</param>
    /// <remarks>
    /// Singleton registrations are resolved once when the endpoint is mapped. Scoped and transient registrations are
    /// resolved for each validation or execution operation. The keyed session store is always resolved for each operation,
    /// and persisted sessions are partitioned by the registration name.
    /// See <see cref="MapOpenAIResponses(IEndpointRouteBuilder, string)"/> for endpoint authorization
    /// and caller isolation requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIResponses(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string? path, OpenAIResponsesMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agentBuilder);

        string agentName = agentBuilder.Name;
        ValidateAgentName(agentName);
        path ??= $"/{agentName}/v1/responses";

        var scopeFactory = endpoints.ServiceProvider.GetRequiredService<IServiceScopeFactory>();
        var executor = agentBuilder.Lifetime == ServiceLifetime.Singleton
            ? new AIAgentResponseExecutor(
                endpoints.ServiceProvider.GetRequiredKeyedService<AIAgent>(agentName),
                agentName,
                scopeFactory,
                mapOptions,
                sessionStorageIdentity: agentName)
            : new AIAgentResponseExecutor(agentName, scopeFactory, mapOptions);
        return MapOpenAIResponses(
            endpoints,
            executor,
            path,
            agentName);
    }

    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the OpenAI Responses endpoints for.</param>
    /// <remarks>
    /// See <see cref="MapOpenAIResponses(IEndpointRouteBuilder, string)"/> for endpoint authorization
    /// and caller isolation requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIResponses(this IEndpointRouteBuilder endpoints, AIAgent agent) =>
        MapOpenAIResponses(endpoints, agent, responsesPath: null);

    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/> for the given <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="agent">The <see cref="AIAgent"/> instance to map the OpenAI Responses endpoints for.</param>
    /// <param name="responsesPath">Custom route path for the responses endpoint.</param>
    /// <param name="mapOptions">Optional options controlling how incoming requests are mapped onto the agent run.</param>
    /// <remarks>
    /// See <see cref="MapOpenAIResponses(IEndpointRouteBuilder, string)"/> for endpoint authorization
    /// and caller isolation requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIResponses(
        this IEndpointRouteBuilder endpoints,
        AIAgent agent,
        [StringSyntax("Route")] string? responsesPath,
        OpenAIResponsesMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent.Name));
        ValidateAgentName(agent.Name);

        responsesPath ??= $"/{agent.Name}/v1/responses";

        // The supplied agent remains fixed, while its optional keyed session store is resolved
        // inside each operation scope.
        var scopeFactory = endpoints.ServiceProvider.GetRequiredService<IServiceScopeFactory>();
        var executor = new AIAgentResponseExecutor(
            agent,
            agent.Name,
            scopeFactory,
            mapOptions);
        return MapOpenAIResponses(
            endpoints,
            executor,
            responsesPath,
            agent.Name);
    }

    /// <summary>
    /// Maps OpenAI Responses API endpoints that select the <see cref="AIAgent"/> for each request.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="responsesPath">The route path for the responses endpoint.</param>
    /// <param name="agentSelector">
    /// A delegate invoked once per request that returns the agent to serve, or <see langword="null"/> when
    /// no agent matches the request. The delegate can use route values, claims, headers, and
    /// <see cref="HttpContext.RequestServices"/> to select or resolve the agent.
    /// </param>
    /// <param name="mapOptions">Optional options controlling how incoming requests are mapped onto the agent run.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// <para>
    /// The selector applies to every operation: creation, retrieval, cancellation, deletion, and input item listing.
    /// When <paramref name="agentSelector"/> returns <see langword="null"/>, the operation responds with
    /// <c>404 Not Found</c> before any response, session, or conversation state is loaded.
    /// </para>
    /// <para>
    /// The selected agent's <see cref="AIAgent.Name"/> is its stable logical identity: it is used to resolve the
    /// keyed <see cref="AgentSessionStore"/>, to partition persisted sessions, and to bind stored responses to the
    /// agent that created them, so a response can only be retrieved, canceled, or deleted through requests that select
    /// the same agent name. Conversations continue across requests even when the selector returns a new agent instance
    /// each time. The selected agent must therefore have a non-empty name.
    /// </para>
    /// <para>
    /// The keyed <see cref="AgentSessionStore"/> is resolved from <see cref="HttpContext.RequestServices"/> for
    /// validation and for responses that are not run in the background, so it shares the request-scoped dependencies of
    /// an agent resolved from the same services. These responses are bound to the request: a streaming response keeps
    /// running when the client disconnects, and the request ends only after the run completes, while a non-streaming
    /// response is canceled with the request and the request ends after the run stops. Background responses keep
    /// running the selected agent after the HTTP request completes and resolve the session store from a separate service
    /// scope that they own, so agents used for background responses must not depend on request-scoped services.
    /// </para>
    /// <para>
    /// Selection is not an authorization boundary. See <see cref="MapOpenAIResponses(IEndpointRouteBuilder, string)"/>
    /// for endpoint authorization and caller isolation requirements.
    /// </para>
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIResponses(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("Route")] string responsesPath,
        Func<HttpContext, AIAgent?> agentSelector,
        OpenAIResponsesMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(responsesPath);
        ArgumentNullException.ThrowIfNull(agentSelector);

        var scopeFactory = endpoints.ServiceProvider.GetRequiredService<IServiceScopeFactory>();
        return MapOpenAIResponses(
            endpoints,
            executor: null,
            responsesPath,
            endpointAgentName: null,
            context =>
            {
                if (agentSelector(context) is not { } agent)
                {
                    return null;
                }

                string agentName = HostedAgentResolution.GetSelectedAgentName(agent);
                return (agentName, new AIAgentResponseExecutor(
                    agent, agentName, scopeFactory, mapOptions, sessionStorageIdentity: agentName, requestServices: context.RequestServices));
            });
    }

    private static RouteGroupBuilder MapOpenAIResponses(
        IEndpointRouteBuilder endpoints,
        IResponseExecutor? executor,
        string responsesPath,
        string? endpointAgentName,
        Func<HttpContext, (string AgentName, IResponseExecutor Executor)?>? agentSelector = null)
    {
        // Resolve the response storage settings and optional conversation storage.
        var storageOptions = endpoints.ServiceProvider.GetService<InMemoryStorageOptions>() ?? new InMemoryStorageOptions();
        var conversationStorage = endpoints.ServiceProvider.GetService<IConversationStorage>();

        // Resolve the optional caller isolation provider.
        var isolationKeyProvider = endpoints.ServiceProvider.GetService<AgentIsolationKeyProvider>();

        // Require a key whenever isolation is configured.
        var isolationKeyResolver = new IsolationKeyResolver(isolationKeyProvider, strict: isolationKeyProvider is not null);

        // Create the response service so response and conversation operations are scoped by the caller's isolation key.
        var responsesService = new InMemoryResponsesService(executor, storageOptions, conversationStorage, isolationKeyResolver);
        var handlers = new ResponsesHttpHandler(responsesService, agentSelector is null ? null : SelectAgent);
        var group = endpoints.MapGroup(responsesPath);

        // Create response endpoint
        group.MapPost("/", handlers.CreateResponseAsync)
            .WithEndpointName(endpointAgentName, "CreateResponse")
            .WithSummary("Creates a model response for the given input");

        // Get response endpoint
        group.MapGet("{responseId}", handlers.GetResponseAsync)
            .WithEndpointName(endpointAgentName, "GetResponse")
            .WithSummary("Retrieves a response by ID");

        // Cancel response endpoint
        group.MapPost("{responseId}/cancel", handlers.CancelResponseAsync)
            .WithEndpointName(endpointAgentName, "CancelResponse")
            .WithSummary("Cancels an in-progress response");

        // Delete response endpoint
        group.MapDelete("{responseId}", handlers.DeleteResponseAsync)
            .WithEndpointName(endpointAgentName, "DeleteResponse")
            .WithSummary("Deletes a response");

        // List response input items endpoint
        group.MapGet("{responseId}/input_items", handlers.ListResponseInputItemsAsync)
            .WithEndpointName(endpointAgentName, "ListResponseInputItems")
            .WithSummary("Lists the input items for a response");

        MarkFeatureUsed();
        return group;

        (IResponsesService, IResponseExecutor)? SelectAgent(HttpContext context) =>
            agentSelector(context) is { } selection
                ? (responsesService.ForAgent(selection.AgentName), selection.Executor)
                : null;
    }

    private static RouteHandlerBuilder WithEndpointName(this RouteHandlerBuilder builder, string? endpointAgentName, string operationName)
        => endpointAgentName is null ? builder : builder.WithName(endpointAgentName + "/" + operationName);

    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <remarks>
    /// See <see cref="MapOpenAIResponses(IEndpointRouteBuilder, string)"/> for endpoint authorization
    /// and caller isolation requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapOpenAIResponses(this IEndpointRouteBuilder endpoints) =>
        MapOpenAIResponses(endpoints, responsesPath: null);

    /// <summary>
    /// Maps OpenAI Responses API endpoints to the specified <see cref="IEndpointRouteBuilder"/>.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the OpenAI Responses endpoints to.</param>
    /// <param name="responsesPath">Custom route path for the responses endpoint.</param>
    /// <remarks>
    /// <para>
    /// This method does not require authorization automatically. Configure authentication and enforce
    /// authorization on the returned route group, for example with <c>RequireAuthorization()</c>.
    /// Protect separately mapped Conversations endpoints as well.
    /// </para>
    /// <para>
    /// Multi-user hosts must register an <see cref="AgentIsolationKeyProvider"/> to scope stored responses
    /// and conversations. Response and conversation storage can retain data even without an
    /// <see cref="AgentSessionStore"/>. This method does not add an isolation decorator to a configured agent
    /// session store; register it with an isolation-enabled helper such as <c>WithSessionStore(...)</c> or
    /// <c>WithInMemorySessionStore()</c>, or wrap it in <see cref="IsolationKeyScopedAgentSessionStore"/>, so that
    /// session and approval state is also scoped to the caller. For claims-based isolation, register
    /// <c>AddHttpContextAccessor()</c> and <c>UseClaimsBasedAgentIsolation(...)</c> from
    /// <c>Microsoft.Agents.AI.Hosting.AspNetCore</c>, using a claim that uniquely identifies the caller.
    /// Response and conversation identifiers are not authorization tokens. Clients must authenticate
    /// every operation, including continuations, approval responses, retrieval, cancellation, and deletion.
    /// </para>
    /// </remarks>
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

        MarkFeatureUsed();
        return group;
    }

    private static void MarkFeatureUsed()
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)FeatureIndex.HostingOpenAI);
#pragma warning restore MAAI001
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
