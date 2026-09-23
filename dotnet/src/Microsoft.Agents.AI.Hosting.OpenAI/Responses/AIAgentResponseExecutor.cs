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
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly OpenAIResponsesMapOptions _mapOptions;

    public AIAgentResponseExecutor(
        AIAgent agent,
        string registrationKey,
        IServiceScopeFactory scopeFactory,
        OpenAIResponsesMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentException.ThrowIfNullOrEmpty(registrationKey);
        ArgumentNullException.ThrowIfNull(scopeFactory);

        this._agent = agent;
        this._registrationKey = registrationKey;
        this._scopeFactory = scopeFactory;
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
        this._scopeFactory = scopeFactory;
        this._mapOptions = mapOptions ?? new OpenAIResponsesMapOptions();
    }

    public async ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default)
    {
        AsyncServiceScope scope = this._scopeFactory.CreateAsyncScope();
        await using (scope.ConfigureAwait(false))
        {
            AIAgent executionAgent = this.ResolveExecutionAgent(scope.ServiceProvider);
            ResponseError? sessionError =
                AgentResponseExecution.ValidateSessionRequirements(request, executionAgent is AIHostAgent);
            return sessionError
                ?? this.ValidateRunOptions(request)
                ?? await AgentResponseExecution.ValidatePendingApprovalResponsesAsync(
                    executionAgent, request, cancellationToken).ConfigureAwait(false);
        }
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
        // The scope surrounds the full enumeration so background execution retains scoped
        // agents and stores through session persistence after the HTTP request has returned.
        AsyncServiceScope scope = this._scopeFactory.CreateAsyncScope();
        await using (scope.ConfigureAwait(false))
        {
            AIAgent executionAgent = this.ResolveExecutionAgent(scope.ServiceProvider);

            // Agent selection is fixed by the endpoint. The remaining response execution behavior is
            // shared with request-routed hosted agents.
            await foreach (StreamingResponseEvent streamingEvent in AgentResponseExecution.ExecuteAsync(
                executionAgent, this._mapOptions, context, request, conversationHistory, cancellationToken).ConfigureAwait(false))
            {
                yield return streamingEvent;
            }
        }
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

        string? sessionStorageIdentity = this._agent is null ? this._registrationKey : null;
        return new AIHostAgent(agent, sessionStore, sessionStorageIdentity);
    }
}
