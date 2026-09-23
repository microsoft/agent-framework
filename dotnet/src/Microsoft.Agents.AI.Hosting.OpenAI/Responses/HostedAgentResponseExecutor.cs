// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Response executor that routes requests to hosted AIAgent services based on agent.name or metadata["entity_id"].
/// This executor resolves agents from keyed services registered via AddAIAgent().
/// The model field is reserved for actual model names and is never used for entity/agent identification.
/// </summary>
internal sealed class HostedAgentResponseExecutor : IResponseExecutor
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<HostedAgentResponseExecutor> _logger;
    private readonly OpenAIResponsesMapOptions _mapOptions;

    /// <summary>
    /// Initializes a new instance of the <see cref="HostedAgentResponseExecutor"/> class.
    /// </summary>
    /// <param name="scopeFactory">The factory used to create a scope for each hosted-agent operation.</param>
    /// <param name="logger">The logger instance.</param>
    /// <param name="mapOptions">Options controlling how incoming requests are mapped onto the agent run.</param>
    public HostedAgentResponseExecutor(
        IServiceScopeFactory scopeFactory,
        ILogger<HostedAgentResponseExecutor> logger,
        OpenAIResponsesMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(scopeFactory);
        ArgumentNullException.ThrowIfNull(logger);

        this._scopeFactory = scopeFactory;
        this._logger = logger;
        this._mapOptions = mapOptions ?? new OpenAIResponsesMapOptions();
    }

    /// <inheritdoc/>
    public async ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default)
    {
        // Extract agent name from agent.name or model parameter
        string? registrationKey = GetAgentRegistrationKey(request);

        if (string.IsNullOrEmpty(registrationKey))
        {
            return new ResponseError
            {
                Code = "missing_required_parameter",
                Message = "No 'agent.name' or 'metadata[\"entity_id\"]' specified in the request."
            };
        }

        AsyncServiceScope scope = this._scopeFactory.CreateAsyncScope();
        await using (scope.ConfigureAwait(false))
        {
            IServiceProvider services = scope.ServiceProvider;

            // Validate that the agent can be resolved
            AIAgent? agent = services.GetKeyedService<AIAgent>(registrationKey);
            if (agent is null)
            {
                if (this._logger.IsEnabled(LogLevel.Warning))
                {
                    this._logger.LogWarning("Failed to resolve agent with name '{AgentName}'", registrationKey);
                }

                return new ResponseError
                {
                    Code = "agent_not_found",
                    Message = $"""
                        Agent '{registrationKey}' not found.
                        Ensure the agent is registered with '{registrationKey}' name in the dependency injection container.
                        We recommend using 'builder.AddAIAgent()' for simplicity.
                    """
                };
            }

            // An approval response can be validated only against the pending request stored by the server.
#pragma warning disable MAAI001
            AgentSessionStore? sessionStore = services.GetKeyedService<AgentSessionStore>(registrationKey);
#pragma warning restore MAAI001
            ResponseError? sessionError = AgentResponseExecution.ValidateSessionRequirements(request, sessionStore is not null);
            if (sessionError is not null)
            {
                return sessionError;
            }

            // Surface unsupported request settings as a clean request error rather than an unhandled
            // exception during execution.
            try
            {
                _ = this._mapOptions.RunOptionsFactory(request.ToRequestInfo());
            }
            catch (NotSupportedException ex)
            {
                return new ResponseError
                {
                    Code = "unsupported_parameter",
                    Message = ex.Message
                };
            }

            AIAgent executionAgent = sessionStore is null
                ? agent
                : new AIHostAgent(agent, sessionStore, sessionStorageIdentity: registrationKey);
            return await AgentResponseExecution.ValidatePendingApprovalResponsesAsync(
                executionAgent, request, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    public async IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
        AgentInvocationContext context,
        CreateResponse request,
        IReadOnlyList<ChatMessage>? conversationHistory = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Resolve the agent selected by this request together with its optional persisted session store.
        string registrationKey = GetAgentRegistrationKey(request)!;
        // The scope surrounds the full enumeration so background execution retains scoped
        // agents and stores through session persistence after the HTTP request has returned.
        AsyncServiceScope scope = this._scopeFactory.CreateAsyncScope();
        await using (scope.ConfigureAwait(false))
        {
            IServiceProvider services = scope.ServiceProvider;
            AIAgent agent = services.GetRequiredKeyedService<AIAgent>(registrationKey);
#pragma warning disable MAAI001
            AgentSessionStore? sessionStore = services.GetKeyedService<AgentSessionStore>(registrationKey);
#pragma warning restore MAAI001
            AIAgent executionAgent = sessionStore is null
                ? agent
                : new AIHostAgent(agent, sessionStore, sessionStorageIdentity: registrationKey);

            // Once selected, hosted agents use the same execution behavior as fixed-agent endpoints.
            await foreach (StreamingResponseEvent streamingEvent in AgentResponseExecution.ExecuteAsync(
                executionAgent, this._mapOptions, context, request, conversationHistory, cancellationToken).ConfigureAwait(false))
            {
                yield return streamingEvent;
            }
        }
    }

    /// <summary>
    /// Extracts the agent name for a request from the agent.name property, falling back to metadata["entity_id"].
    /// </summary>
    /// <param name="request">The create response request.</param>
    /// <returns>The agent name.</returns>
    private static string? GetAgentRegistrationKey(CreateResponse request)
    {
        string? agentName = request.Agent?.Name;

        // Fall back to metadata["entity_id"] if agent.name is not present
        if (string.IsNullOrEmpty(agentName) && request.Metadata?.TryGetValue("entity_id", out string? entityId) == true)
        {
            agentName = entityId;
        }

        return agentName;
    }
}
