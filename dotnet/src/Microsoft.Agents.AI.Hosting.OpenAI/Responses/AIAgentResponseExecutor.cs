// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Response executor that uses an AIAgent to execute responses locally.
/// This is the default implementation for local execution.
/// </summary>
internal sealed class AIAgentResponseExecutor : IResponseExecutor
{
    private readonly AIAgent? _agent;
    private readonly string _registrationKey;
    private readonly string? _sessionStorageIdentity;
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IServiceProvider? _requestServices;
    private readonly OpenAIResponsesMapOptions _mapOptions;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIAgentResponseExecutor"/> class for a fixed agent instance.
    /// </summary>
    /// <param name="agent">The agent that executes the responses.</param>
    /// <param name="registrationKey">The name that keys the agent's session store.</param>
    /// <param name="scopeFactory">The factory used to create a scope for operations that are not bound to a request.</param>
    /// <param name="mapOptions">Optional options controlling how incoming requests are mapped onto the agent run.</param>
    /// <param name="sessionStorageIdentity">
    /// The stable logical identity that partitions persisted sessions, or <see langword="null"/> to use the agent instance identity.
    /// </param>
    /// <param name="requestServices">
    /// The services of the request that selected <paramref name="agent"/>, or <see langword="null"/> when the agent is not
    /// bound to a request. When specified, validation and responses that are not run in the background resolve the
    /// session store from these services, so the store shares the agent's request-scoped dependencies.
    /// </param>
    public AIAgentResponseExecutor(
        AIAgent agent,
        string registrationKey,
        IServiceScopeFactory scopeFactory,
        OpenAIResponsesMapOptions? mapOptions = null,
        string? sessionStorageIdentity = null,
        IServiceProvider? requestServices = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrEmpty(registrationKey);
        ArgumentNullException.ThrowIfNull(scopeFactory);

        this._agent = agent;
        this._registrationKey = registrationKey;
        this._sessionStorageIdentity = sessionStorageIdentity;
        this._scopeFactory = scopeFactory;
        this._requestServices = requestServices;
        this._mapOptions = mapOptions ?? new OpenAIResponsesMapOptions();
    }

    public AIAgentResponseExecutor(
        string registrationKey,
        IServiceScopeFactory scopeFactory,
        OpenAIResponsesMapOptions? mapOptions = null)
    {
        ArgumentException.ThrowIfNullOrEmpty(registrationKey);
        ArgumentNullException.ThrowIfNull(scopeFactory);

        this._registrationKey = registrationKey;
        this._sessionStorageIdentity = registrationKey;
        this._scopeFactory = scopeFactory;
        this._mapOptions = mapOptions ?? new OpenAIResponsesMapOptions();
    }

    public async ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default)
    {
        // Validation always runs within the request.
        if (this._requestServices is { } requestServices)
        {
            return await this.ValidateRequestAsync(request, requestServices, cancellationToken).ConfigureAwait(false);
        }

        AsyncServiceScope scope = this._scopeFactory.CreateAsyncScope();
        await using (scope.ConfigureAwait(false))
        {
            return await this.ValidateRequestAsync(request, scope.ServiceProvider, cancellationToken).ConfigureAwait(false);
        }
    }

    private async ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        IServiceProvider services,
        CancellationToken cancellationToken)
    {
        AIAgent executionAgent = this.ResolveExecutionAgent(services);
        ResponseError? sessionError =
            AgentResponseExecution.ValidateSessionRequirements(request, executionAgent is AIHostAgent);
        return sessionError
            ?? this.ValidateRunOptions(request)
            ?? await AgentResponseExecution.ValidatePendingApprovalResponsesAsync(
                executionAgent, request, cancellationToken).ConfigureAwait(false);
    }

    internal ResponseError? ValidateRunOptions(CreateResponse request)
    {
        try
        {
            // Map options during validation so that unsupported request settings are surfaced
            // as a clean request error rather than an unhandled exception during execution.
            _ = this._mapOptions.RunOptionsFactory(request.ToRequestInfo());
            return null;
        }
        catch (NotSupportedException ex)
        {
            return new ResponseError
            {
                Code = "unsupported_parameter",
                Message = ex.Message
            };
        }
    }

    public async IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
        AgentInvocationContext context,
        CreateResponse request,
        IReadOnlyList<ChatMessage>? conversationHistory = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Responses that are not run in the background are owned by the request that selected the agent, so their
        // session store shares the agent's request-scoped dependencies.
        if (this._requestServices is { } requestServices && request.Background != true)
        {
            await foreach (StreamingResponseEvent streamingEvent in this.ExecuteAsync(
                requestServices, context, request, conversationHistory, cancellationToken).ConfigureAwait(false))
            {
                yield return streamingEvent;
            }

            yield break;
        }

        // The scope surrounds the full enumeration so background execution retains scoped
        // agents and stores through session persistence after the HTTP request has returned.
        AsyncServiceScope scope = this._scopeFactory.CreateAsyncScope();
        await using (scope.ConfigureAwait(false))
        {
            await foreach (StreamingResponseEvent streamingEvent in this.ExecuteAsync(
                scope.ServiceProvider, context, request, conversationHistory, cancellationToken).ConfigureAwait(false))
            {
                yield return streamingEvent;
            }
        }
    }

    private IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
        IServiceProvider services,
        AgentInvocationContext context,
        CreateResponse request,
        IReadOnlyList<ChatMessage>? conversationHistory,
        CancellationToken cancellationToken)
    {
        AIAgent executionAgent = this.ResolveExecutionAgent(services);

        // Agent selection is fixed by the endpoint. The remaining response execution behavior is
        // shared with request-routed hosted agents.
        return AgentResponseExecution.ExecuteAsync(
            executionAgent, this._mapOptions, context, request, conversationHistory, cancellationToken);
    }

    private AIAgent ResolveExecutionAgent(IServiceProvider services)
    {
        AIAgent agent = this._agent ??
            services.GetRequiredKeyedService<AIAgent>(this._registrationKey);
#pragma warning disable MAAI001
        AgentSessionStore? sessionStore =
            services.GetKeyedService<AgentSessionStore>(this._registrationKey);
#pragma warning restore MAAI001
        if (sessionStore is null)
        {
            return agent;
        }

        return new AIHostAgent(agent, sessionStore, this._sessionStorageIdentity);
    }
}
