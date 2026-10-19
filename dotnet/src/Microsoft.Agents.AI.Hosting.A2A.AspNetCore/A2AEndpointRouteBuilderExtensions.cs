// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using A2A;
using A2A.AspNetCore;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.A2A;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.AspNetCore.Builder;

/// <summary>
/// Provides extension methods for mapping A2A protocol endpoints for AI agents.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
public static class A2AEndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps A2A HTTP+JSON endpoints for the specified agent to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for the agent.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// See <see cref="MapA2AHttpJson(IEndpointRouteBuilder, string, string)"/> for endpoint authorization
    /// and caller isolation requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2AHttpJson(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);

        return endpoints.MapA2AHttpJson(agentBuilder.Name, path);
    }

    /// <summary>
    /// Maps A2A HTTP+JSON endpoints for the specified agent to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent whose name identifies the registered A2A server.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// See <see cref="MapA2AHttpJson(IEndpointRouteBuilder, string, string)"/> for endpoint authorization
    /// and caller isolation requirements.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2AHttpJson(this IEndpointRouteBuilder endpoints, AIAgent agent, string path)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent) + "." + nameof(agent.Name));

        return endpoints.MapA2AHttpJson(agent.Name, path);
    }

    /// <summary>
    /// Maps A2A HTTP+JSON endpoints for the agent with the specified name to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// This method does not require authorization automatically. Configure authentication and enforce
    /// endpoint authorization, for example with <c>RequireAuthorization()</c> on the returned builder.
    /// Multi-user hosts also need an <see cref="AgentIsolationKeyProvider"/> to isolate sessions and tasks;
    /// task isolation remains necessary without session persistence. For claims-based isolation, register
    /// <c>AddHttpContextAccessor()</c> and <c>UseClaimsBasedAgentIsolation(...)</c> from
    /// <c>Microsoft.Agents.AI.Hosting.AspNetCore</c>, using a claim that uniquely identifies the caller.
    /// The <see cref="AgentIsolationKeyProvider"/> is resolved from <see cref="HttpContext.RequestServices"/> once
    /// per request, so it can be registered with any lifetime, and its key is reused by the operations that the
    /// request continues in the background.
    /// Protect each enabled protocol binding, not just one of the HTTP+JSON and JSON-RPC endpoints.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2AHttpJson(this IEndpointRouteBuilder endpoints, string agentName, string path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(agentName);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);

        var a2aServer = endpoints.ServiceProvider.GetKeyedService<A2AServer>(agentName)
            ?? throw new InvalidOperationException(
                $"No A2AServer is registered for agent '{agentName}'. " +
                $"Call services.AddA2AServer(\"{agentName}\") or agentBuilder.AddA2AServer() during service registration to register one.");

        IEndpointConventionBuilder endpoint = endpoints.MapHttpA2A(a2aServer, path);
        AddRequestFlow(endpoint);
        MarkFeatureUsed();
        return endpoint;
    }

    /// <summary>
    /// Maps A2A HTTP+JSON endpoints that select the agent to serve for each request.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <param name="agentSelector">
    /// A delegate invoked once per request that returns the agent to serve, or <see langword="null"/> when
    /// no agent matches the request. The delegate can use route values, claims, headers, and
    /// <see cref="HttpContext.RequestServices"/> to select or resolve the agent.
    /// </param>
    /// <param name="configureOptions">An optional callback to configure the <see cref="A2AServerRegistrationOptions"/> applied to every selected agent.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// <para>
    /// When <paramref name="agentSelector"/> returns <see langword="null"/>, the endpoint responds with
    /// <c>404 Not Found</c> before any session or task state is loaded. No <c>AddA2AServer</c> registration is required.
    /// </para>
    /// <para>
    /// The selected agent's <see cref="AIAgent.Name"/> is its stable logical identity. It keys the agent's
    /// <see cref="AgentSessionStore"/> and <see cref="ITaskStore"/> registrations, partitions persisted sessions, and
    /// identifies the A2A task state shared by the requests that select it through this endpoint, so conversations
    /// and tasks continue across requests even when the selector returns a new agent instance each time. The selected
    /// agent must therefore have a non-empty name. The session store is resolved from
    /// <see cref="HttpContext.RequestServices"/>, so the run cannot outlive the request: when the configured
    /// <see cref="AgentRunMode"/> returns a task, non-streaming requests with <c>ReturnImmediately</c> enabled are
    /// rejected with <see cref="A2AErrorCode.UnsupportedOperation"/>, and a streaming request that ends early, for
    /// example because the client disconnects, completes only after the agent run finishes. The run is not canceled, so
    /// its task state is still persisted. When the application stops, operations that are still running for selected
    /// agents are canceled and awaited.
    /// </para>
    /// <para>
    /// Selection is not an authorization boundary. See <see cref="MapA2AHttpJson(IEndpointRouteBuilder, string, string)"/>
    /// for endpoint authorization and caller isolation requirements.
    /// </para>
    /// </remarks>
    public static IEndpointConventionBuilder MapA2AHttpJson(
        this IEndpointRouteBuilder endpoints,
        string path,
        Func<HttpContext, AIAgent?> agentSelector,
        Action<A2AServerRegistrationOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        ArgumentNullException.ThrowIfNull(agentSelector);

        var requestHandler = CreateSelectedAgentRequestHandler(endpoints, configureOptions);

        IEndpointConventionBuilder endpoint = endpoints.MapHttpA2A(requestHandler, path);
        AddAgentSelection(endpoint, requestHandler, agentSelector);
        MarkFeatureUsed();
        return endpoint;
    }

    /// <summary>
    /// Maps A2A JSON-RPC endpoints for the specified agent to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentBuilder">The configuration builder for the agent.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// See <see cref="MapA2AHttpJson(IEndpointRouteBuilder, string, string)"/> for endpoint authorization
    /// and caller isolation requirements, which also apply to this JSON-RPC binding.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2AJsonRpc(this IEndpointRouteBuilder endpoints, IHostedAgentBuilder agentBuilder, string path)
    {
        ArgumentNullException.ThrowIfNull(agentBuilder);

        return endpoints.MapA2AJsonRpc(agentBuilder.Name, path);
    }

    /// <summary>
    /// Maps A2A JSON-RPC endpoints for the specified agent to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agent">The agent whose name identifies the registered A2A server.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// See <see cref="MapA2AHttpJson(IEndpointRouteBuilder, string, string)"/> for endpoint authorization
    /// and caller isolation requirements, which also apply to this JSON-RPC binding.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2AJsonRpc(this IEndpointRouteBuilder endpoints, AIAgent agent, string path)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrWhiteSpace(agent.Name, nameof(agent) + "." + nameof(agent.Name));

        return endpoints.MapA2AJsonRpc(agent.Name, path);
    }

    /// <summary>
    /// Maps A2A JSON-RPC endpoints for the agent with the specified name to the given path.
    /// An <see cref="A2AServer"/> for the agent must be registered first by calling
    /// <c>AddA2AServer</c> during service registration.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="agentName">The name of the agent to use for A2A protocol integration.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// See <see cref="MapA2AHttpJson(IEndpointRouteBuilder, string, string)"/> for endpoint authorization
    /// and caller isolation requirements, which also apply to this JSON-RPC binding.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2AJsonRpc(this IEndpointRouteBuilder endpoints, string agentName, string path)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(agentName);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);

        var a2aServer = endpoints.ServiceProvider.GetKeyedService<A2AServer>(agentName)
            ?? throw new InvalidOperationException(
                $"No A2AServer is registered for agent '{agentName}'. " +
                $"Call services.AddA2AServer(\"{agentName}\") or agentBuilder.AddA2AServer() during service registration to register one.");

        IEndpointConventionBuilder endpoint = endpoints.MapA2A(a2aServer, path);
        AddRequestFlow(endpoint);
        MarkFeatureUsed();
        return endpoint;
    }

    /// <summary>
    /// Maps A2A JSON-RPC endpoints that select the agent to serve for each request.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the A2A endpoints to.</param>
    /// <param name="path">The route path prefix for A2A endpoints.</param>
    /// <param name="agentSelector">
    /// A delegate invoked once per request that returns the agent to serve, or <see langword="null"/> when
    /// no agent matches the request. The delegate can use route values, claims, headers, and
    /// <see cref="HttpContext.RequestServices"/> to select or resolve the agent.
    /// </param>
    /// <param name="configureOptions">An optional callback to configure the <see cref="A2AServerRegistrationOptions"/> applied to every selected agent.</param>
    /// <returns>An <see cref="IEndpointConventionBuilder"/> for further endpoint configuration.</returns>
    /// <remarks>
    /// See <see cref="MapA2AHttpJson(IEndpointRouteBuilder, string, Func{HttpContext, AIAgent}, Action{A2AServerRegistrationOptions})"/>
    /// for selection, identity, and lifetime behavior, and <see cref="MapA2AHttpJson(IEndpointRouteBuilder, string, string)"/>
    /// for endpoint authorization and caller isolation requirements, which also apply to this JSON-RPC binding.
    /// </remarks>
    public static IEndpointConventionBuilder MapA2AJsonRpc(
        this IEndpointRouteBuilder endpoints,
        string path,
        Func<HttpContext, AIAgent?> agentSelector,
        Action<A2AServerRegistrationOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        ArgumentNullException.ThrowIfNull(agentSelector);

        var requestHandler = CreateSelectedAgentRequestHandler(endpoints, configureOptions);

        IEndpointConventionBuilder endpoint = endpoints.MapA2A(requestHandler, path);
        AddAgentSelection(endpoint, requestHandler, agentSelector);
        MarkFeatureUsed();
        return endpoint;
    }

    private static SelectedAgentA2ARequestHandler CreateSelectedAgentRequestHandler(
        IEndpointRouteBuilder endpoints,
        Action<A2AServerRegistrationOptions>? configureOptions)
    {
        A2AServerRegistrationOptions? options = null;
        if (configureOptions is not null)
        {
            options = new A2AServerRegistrationOptions();
            configureOptions(options);
        }

        var requestHandler = new SelectedAgentA2ARequestHandler(endpoints.ServiceProvider, options);

        // The handler is created after the service provider is built, so the host cannot own it. Dispose it once the
        // server has stopped processing requests and before the service provider is disposed, so the operations its
        // A2A servers still run are canceled and joined while their dependencies are alive.
        if (endpoints.ServiceProvider.GetService<IHostApplicationLifetime>() is { } lifetime)
        {
#pragma warning disable VSTHRD002 // Lifetime callbacks are synchronous, and the host must wait for the servers to stop.
            _ = lifetime.ApplicationStopped.Register(
                static state => ((SelectedAgentA2ARequestHandler)state!).DisposeAsync().AsTask().GetAwaiter().GetResult(),
                requestHandler);
#pragma warning restore VSTHRD002
        }

        return requestHandler;
    }

    private static void AddAgentSelection(
        IEndpointConventionBuilder endpoint,
        SelectedAgentA2ARequestHandler requestHandler,
        Func<HttpContext, AIAgent?> agentSelector)
    {
        AddRequestFlow(endpoint, httpContext =>
        {
            if (agentSelector(httpContext) is not { } agent)
            {
                return false;
            }

            requestHandler.Select(agent, httpContext.RequestServices);
            return true;
        });
    }

    /// <summary>
    /// Runs the A2A endpoints in an asynchronous flow that carries the request's isolation key and, when
    /// <paramref name="selectAgent"/> is specified, the agent selected for the request.
    /// </summary>
    /// <param name="endpoint">The A2A endpoints.</param>
    /// <param name="selectAgent">
    /// An optional delegate that selects the agent for the request, returning <see langword="false"/> when no agent matches.
    /// </param>
    private static void AddRequestFlow(IEndpointConventionBuilder endpoint, Func<HttpContext, bool>? selectAgent = null)
    {
        // The A2A endpoints call the request handler without request context, so record the request state for the
        // asynchronous flow of the request before the endpoint runs.
        endpoint.AddEndpointFilter(async (invocationContext, next) =>
        {
            HttpContext httpContext = invocationContext.HttpContext;
            if (selectAgent?.Invoke(httpContext) == false)
            {
                return Results.NotFound();
            }

            // A2A servers are shared by all requests, so resolve the key from the request services while they are
            // alive. Operations that continue in the background reuse it.
            A2ARequestIsolation.Current = await A2ARequestIsolation.ResolveAsync(httpContext.RequestServices, httpContext.RequestAborted).ConfigureAwait(false);
            object? result = await next(invocationContext).ConfigureAwait(false);

            // Streaming results enumerate the request handler when they execute, which would otherwise happen after
            // this filter returns and outside the asynchronous flow that carries the request state.
            if (result is IResult httpResult)
            {
                await httpResult.ExecuteAsync(httpContext).ConfigureAwait(false);
                return Results.Empty;
            }

            return result;
        });
    }

    private static void MarkFeatureUsed()
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)FeatureIndex.HostingA2A);
#pragma warning restore MAAI001
    }
}
