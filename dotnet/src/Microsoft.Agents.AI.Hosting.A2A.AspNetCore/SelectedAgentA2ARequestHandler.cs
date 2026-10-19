// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// An <see cref="IA2ARequestHandler"/> that dispatches each A2A operation to the agent selected for the current request.
/// </summary>
/// <remarks>
/// The A2A endpoints invoke this handler without request context, so the endpoint filter records the selected agent
/// for the asynchronous flow of the request before the endpoint runs. Each selected agent name owns an
/// <see cref="A2AServer"/> whose task state is shared by all requests that select that name.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
internal sealed class SelectedAgentA2ARequestHandler : IA2ARequestHandler
{
    private readonly AsyncLocal<Selection?> _selection = new();
    private readonly ConcurrentDictionary<string, SelectedAgentServer> _servers = new(StringComparer.Ordinal);
    private readonly IServiceProvider _applicationServices;
    private readonly A2AServerRegistrationOptions? _options;

    /// <summary>
    /// Initializes a new instance of the <see cref="SelectedAgentA2ARequestHandler"/> class.
    /// </summary>
    /// <param name="applicationServices">The application service provider that owns the shared task state.</param>
    /// <param name="options">The optional registration options applied to every selected agent.</param>
    public SelectedAgentA2ARequestHandler(IServiceProvider applicationServices, A2AServerRegistrationOptions? options)
    {
        this._applicationServices = applicationServices;
        this._options = options;
    }

    /// <summary>
    /// Makes <paramref name="agent"/> the target of the A2A operations dispatched in the current asynchronous flow.
    /// </summary>
    /// <param name="agent">The agent selected for the request.</param>
    /// <param name="requestServices">The request services that own the agent's session services.</param>
    public void Select(AIAgent agent, IServiceProvider requestServices)
    {
        string agentName = HostedAgentResolution.GetSelectedAgentName(agent);
        SelectedAgentServer server = this._servers.GetOrAdd(
            agentName,
            static (name, state) => new SelectedAgentServer(state._applicationServices, name, state._options),
            this);

        this._selection.Value = new Selection(agent, agentName, requestServices, server, this._options?.AgentRunMode ?? AgentRunMode.ReturnMessage);
    }

    /// <inheritdoc/>
    public Task<SendMessageResponse> SendMessageAsync(SendMessageRequest request, CancellationToken cancellationToken = default)
    {
        Selection selection = this.GetSelection();
        selection.BindAgent(request.Message);
        return selection.A2AServer.SendMessageAsync(request, cancellationToken);
    }

    /// <inheritdoc/>
    public IAsyncEnumerable<StreamResponse> SendStreamingMessageAsync(SendMessageRequest request, CancellationToken cancellationToken = default)
    {
        Selection selection = this.GetSelection();
        selection.BindAgent(request.Message);
        return selection.A2AServer.SendStreamingMessageAsync(request, cancellationToken);
    }

    /// <inheritdoc/>
    public Task<AgentTask> GetTaskAsync(GetTaskRequest request, CancellationToken cancellationToken = default)
        => this.GetSelection().A2AServer.GetTaskAsync(request, cancellationToken);

    /// <inheritdoc/>
    public Task<ListTasksResponse> ListTasksAsync(ListTasksRequest request, CancellationToken cancellationToken = default)
        => this.GetSelection().A2AServer.ListTasksAsync(request, cancellationToken);

    /// <inheritdoc/>
    public Task<AgentTask> CancelTaskAsync(CancelTaskRequest request, CancellationToken cancellationToken = default)
        => this.GetSelection().A2AServer.CancelTaskAsync(request, cancellationToken);

    /// <inheritdoc/>
    public IAsyncEnumerable<StreamResponse> SubscribeToTaskAsync(SubscribeToTaskRequest request, CancellationToken cancellationToken = default)
        => this.GetSelection().A2AServer.SubscribeToTaskAsync(request, cancellationToken);

    /// <inheritdoc/>
    public Task<TaskPushNotificationConfig> CreateTaskPushNotificationConfigAsync(TaskPushNotificationConfig config, CancellationToken cancellationToken = default)
        => this.GetSelection().A2AServer.CreateTaskPushNotificationConfigAsync(config, cancellationToken);

    /// <inheritdoc/>
    public Task<TaskPushNotificationConfig> GetTaskPushNotificationConfigAsync(GetTaskPushNotificationConfigRequest request, CancellationToken cancellationToken = default)
        => this.GetSelection().A2AServer.GetTaskPushNotificationConfigAsync(request, cancellationToken);

    /// <inheritdoc/>
    public Task<ListTaskPushNotificationConfigsResponse> ListTaskPushNotificationConfigsAsync(ListTaskPushNotificationConfigsRequest request, CancellationToken cancellationToken = default)
        => this.GetSelection().A2AServer.ListTaskPushNotificationConfigsAsync(request, cancellationToken);

    /// <inheritdoc/>
    public Task DeleteTaskPushNotificationConfigAsync(DeleteTaskPushNotificationConfigRequest request, CancellationToken cancellationToken = default)
        => this.GetSelection().A2AServer.DeleteTaskPushNotificationConfigAsync(request, cancellationToken);

    /// <inheritdoc/>
    public Task<AgentCard> GetExtendedAgentCardAsync(GetExtendedAgentCardRequest request, CancellationToken cancellationToken = default)
        => this.GetSelection().A2AServer.GetExtendedAgentCardAsync(request, cancellationToken);

    private Selection GetSelection() =>
        this._selection.Value ?? throw new InvalidOperationException("No agent was selected for the current A2A request.");

    private sealed class Selection(
        AIAgent agent,
        string agentName,
        IServiceProvider requestServices,
        SelectedAgentServer server,
        AgentRunMode runMode)
    {
        public A2AServer A2AServer => server.A2AServer;

        public void BindAgent(Message message)
        {
            AIHostAgent hostAgent = A2AServerServiceCollectionExtensions.CreateHostAgent(requestServices, agent, agentName, sessionStorageIdentity: agentName);
            server.Bind(message, new A2AAgentHandler(hostAgent, runMode, allowReturnImmediately: false));
        }
    }

    /// <summary>
    /// Owns the task state of one selected agent name and runs each message with the agent selected by its request.
    /// </summary>
    private sealed class SelectedAgentServer : IAgentHandler
    {
        // A2AServer passes the incoming message to the handler, including when it runs the handler in the background.
        private readonly ConditionalWeakTable<Message, IAgentHandler> _handlers = new();

        public SelectedAgentServer(IServiceProvider applicationServices, string agentName, A2AServerRegistrationOptions? options)
        {
            this.A2AServer = A2AServerServiceCollectionExtensions.CreateA2AServer(applicationServices, agentName, this, options);
        }

        public A2AServer A2AServer { get; }

        public void Bind(Message message, IAgentHandler handler) => this._handlers.AddOrUpdate(message, handler);

        public Task ExecuteAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
        {
            if (context.Message is null || !this._handlers.TryGetValue(context.Message, out IAgentHandler? handler))
            {
                throw new InvalidOperationException("The A2A message is not associated with the agent selected for its request.");
            }

            return handler.ExecuteAsync(context, eventQueue, cancellationToken);
        }

        public Task CancelAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
            => A2AAgentHandler.CancelTaskAsync(context, eventQueue, cancellationToken);
    }
}
