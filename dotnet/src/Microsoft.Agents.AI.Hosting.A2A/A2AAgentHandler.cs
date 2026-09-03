// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// An <see cref="IAgentHandler"/> implementation that bridges an <see cref="AIAgent"/> to the
/// A2A (Agent2Agent) protocol. Handles message execution and cancellation by delegating to
/// the underlying agent and translating responses into A2A events.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIResponseContinuations)]
internal sealed class A2AAgentHandler : IAgentHandler
{
    /// <summary>
    /// The <see cref="AgentRunOptions.AdditionalProperties"/> key under which the caller supplied
    /// <c>MessageSendParams.configuration</c> is forwarded to the hosted agent.
    /// </summary>
    private const string ConfigurationPropertyKey = "a2a.configuration";

    private readonly AIHostAgent _hostAgent;
    private readonly AgentRunMode _runMode;

    /// <summary>
    /// Initializes a new instance of the <see cref="A2AAgentHandler"/> class.
    /// </summary>
    /// <param name="hostAgent">The hosted agent that provides the execution logic.</param>
    /// <param name="runMode">Controls which A2A artifact the agent response is returned as.</param>
    public A2AAgentHandler(
        AIHostAgent hostAgent,
        AgentRunMode runMode)
    {
        ArgumentNullException.ThrowIfNull(hostAgent);
        ArgumentNullException.ThrowIfNull(runMode);

        this._hostAgent = hostAgent;
        this._runMode = runMode;
    }

    /// <inheritdoc/>
    public Task ExecuteAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        // Handle task updates
        if (context.IsContinuation)
        {
            return this.HandleTaskUpdateAsync(context, eventQueue, cancellationToken);
        }

        // Handle messages received via streaming endpoint
        if (context.StreamingResponse)
        {
            return this.HandleNewMessageAsync(context, eventQueue, aggregateTaskUpdates: false, cancellationToken);
        }

        // Handle new messages received via non-streaming endpoint
        // Aggregate task updates unless the caller requests an immediate response.
        bool aggregateTaskUpdates = context.Configuration?.ReturnImmediately is not true;
        return this.HandleNewMessageAsync(context, eventQueue, aggregateTaskUpdates, cancellationToken);
    }

    /// <inheritdoc/>
    public async Task CancelAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        var taskUpdater = new TaskUpdater(eventQueue, context.TaskId, context.ContextId);
        await taskUpdater.CancelAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Runs the agent for a new message and emits the response events, shared by the streaming and non-streaming endpoints.
    /// </summary>
    /// <param name="context">The request context of the incoming message.</param>
    /// <param name="eventQueue">The queue the response events are written to.</param>
    /// <param name="aggregateTaskUpdates">
    /// <see langword="true"/> to run the agent to completion before emitting a single completed task;
    /// <see langword="false"/> to emit task updates as they are produced. Ignored when the server is configured
    /// through <see cref="AgentRunMode"/> to return a message, because a message response is always aggregated.
    /// </param>
    /// <param name="cancellationToken">A <see cref="CancellationToken"/> to cancel the operation.</param>
    /// <remarks>
    /// The response shape is decided by two independent inputs:
    /// <list type="number">
    /// <item><description>
    /// Which A2A artifact the server returns. This is configured per agent registration, for example:
    /// <code>
    /// builder.AddA2AServer(agent, (A2AServerRegistrationOptions options) =>
    ///     options.AgentRunMode = AgentRunMode.ReturnTask);
    /// </code>
    /// Use <c>AgentRunMode.ReturnMessage</c> to always respond with a message instead of a task.
    /// </description></item>
    /// <item><description>
    /// Whether the client asked for an immediate response. In the A2A protocol this is the
    /// <c>MessageSendConfiguration.ReturnImmediately</c> flag on the request; from the Agent Framework side, an
    /// <c>A2AAgent</c> sets it by passing <c>AgentRunOptions.AllowBackgroundResponses = true</c> to the run call.
    /// </description></item>
    /// </list>
    /// The resulting combinations are:
    /// <list type="bullet">
    /// <item><description>
    /// Server is configured through <see cref="AgentRunMode"/> to return a task and <c>ReturnImmediately = true</c>:
    /// returns the initial task, then the rest of the updates piece by piece.
    /// </description></item>
    /// <item><description>
    /// Server is configured through <see cref="AgentRunMode"/> to return a task and <c>ReturnImmediately = false</c>:
    /// returns a single completed task.
    /// </description></item>
    /// <item><description>
    /// Server is configured through <see cref="AgentRunMode"/> to return a message and <c>ReturnImmediately = true</c>:
    /// returns a message.
    /// </description></item>
    /// <item><description>
    /// Server is configured through <see cref="AgentRunMode"/> to return a message and <c>ReturnImmediately = false</c>:
    /// returns a message.
    /// </description></item>
    /// </list>
    /// </remarks>
    private async Task HandleNewMessageAsync(RequestContext context, AgentEventQueue eventQueue, bool aggregateTaskUpdates, CancellationToken cancellationToken)
    {
        var contextId = context.ContextId ?? Guid.NewGuid().ToString("N");
        var session = await this._hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);

        // AIAgent does not support resuming from arbitrary prior tasks.
        // Throw explicitly so the client gets a clear error rather than a response
        // that silently ignores the referenced task context.
        if (context.Message?.ReferenceTaskIds is { Count: > 0 })
        {
            throw new NotSupportedException("ReferenceTaskIds is not supported. AIAgent cannot resume from arbitrary prior task context.");
        }

        List<ChatMessage> chatMessages = context.Message is not null ? [context.Message.ToChatMessage()] : [];

        // Decide which A2A artifact to return based on the configured run mode.
        var decisionContext = new A2ARunDecisionContext(context);
        var returnTask = await this._runMode.ShouldReturnTaskAsync(decisionContext, cancellationToken).ConfigureAwait(false);

        var options = CreateRunOptions(context);

        var updates = this._hostAgent.RunStreamingAsync(chatMessages, session, options, cancellationToken);

        try
        {
            if (returnTask)
            {
                var taskUpdater = new TaskUpdater(eventQueue, context.TaskId, contextId);
                if (aggregateTaskUpdates)
                {
                    // The server is configured through AgentRunMode to return a task, but the non-streaming client request has
                    // ReturnImmediately disabled, so collect all updates and return a completed task.
                    await AggregateTaskUpdatesAsync(updates, taskUpdater, eventQueue, cancellationToken).ConfigureAwait(false);
                }
                else
                {
                    // The server is configured through AgentRunMode to return a task and this is either a streaming request or a
                    // non-streaming request with ReturnImmediately enabled, so emit task updates as they arrive.
                    await StreamTaskUpdatesAsync(updates, taskUpdater, cancellationToken).ConfigureAwait(false);
                }
            }
            else
            {
                // The server is configured through AgentRunMode to return a message, so return one aggregated message regardless
                // of the client request's ReturnImmediately value.
                await StreamMessageUpdatesAsync(contextId, updates, eventQueue, cancellationToken).ConfigureAwait(false);
            }
        }
        finally
        {
            await this._hostAgent.SaveSessionAsync(contextId, session, CancellationToken.None).ConfigureAwait(false);
        }
    }

    private async Task HandleTaskUpdateAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        var contextId = context.ContextId ?? Guid.NewGuid().ToString("N");
        var session = await this._hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);

        List<ChatMessage> chatMessages = ExtractChatMessagesFromTaskHistory(context.Task);

        var options = CreateRunOptions(context);

        AgentResponse response;
        try
        {
            response = await this._hostAgent.RunAsync(
                chatMessages,
                session: session,
                options: options,
                cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception)
        {
            var failUpdater = new TaskUpdater(eventQueue, context.TaskId, contextId);
            await failUpdater.FailAsync(message: null, CancellationToken.None).ConfigureAwait(false);
            throw;
        }
        finally
        {
            await this._hostAgent.SaveSessionAsync(contextId, session, CancellationToken.None).ConfigureAwait(false);
        }

        if (response.ContinuationToken is null)
        {
            // Complete the task with an artifact containing the response.
            var taskUpdater = new TaskUpdater(eventQueue, context.TaskId, contextId);
            await taskUpdater.AddArtifactAsync(response.Messages.ToParts(), cancellationToken: cancellationToken).ConfigureAwait(false);
            await taskUpdater.CompleteAsync(message: null, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            // Still working: emit progress status.
            var taskUpdater = new TaskUpdater(eventQueue, context.TaskId, contextId);

            Message? progressMessage = response.Messages.Count > 0
                ? CreateMessageFromResponse(contextId, response)
                : null;

            await taskUpdater.StartWorkAsync(progressMessage, cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Creates the <see cref="AgentRunOptions"/> for a run, forwarding the caller supplied A2A
    /// <c>MessageSendParams.metadata</c> and <c>MessageSendParams.configuration</c> to the hosted agent.
    /// </summary>
    /// <param name="context">The A2A request context of the incoming request.</param>
    /// <returns>The run options to invoke the agent with.</returns>
    private static AgentRunOptions CreateRunOptions(RequestContext context)
    {
        AdditionalPropertiesDictionary? additionalProperties = context.Metadata is { Count: > 0 }
            ? context.Metadata.ToAdditionalProperties()
            : null;

        // Forward the whole configuration object under a well-known key so that agents can observe
        // the caller's requested configuration, including fields added to the A2A protocol in the future.
        if (context.Configuration is { } configuration)
        {
            (additionalProperties ??= [])[ConfigurationPropertyKey] = configuration;
        }

        return new AgentRunOptions
        {
            AdditionalProperties = additionalProperties
        };
    }

    private static Message CreateMessageFromResponse(string contextId, AgentResponse response) =>
        new()
        {
            MessageId = response.ResponseId ?? Guid.NewGuid().ToString("N"),
            ContextId = contextId,
            Role = Role.Agent,
            Parts = response.Messages.ToParts(),
            Metadata = response.AdditionalProperties?.ToA2AMetadata()
        };

    private static List<ChatMessage> ExtractChatMessagesFromTaskHistory(AgentTask? agentTask)
    {
        if (agentTask?.History is not { Count: > 0 })
        {
            return [];
        }

        var chatMessages = new List<ChatMessage>(agentTask.History.Count);
        foreach (var message in agentTask.History)
        {
            chatMessages.Add(message.ToChatMessage());
        }

        return chatMessages;
    }

    /// <summary>
    /// Emits a task and streams the agent updates into it as artifacts as they are produced.
    /// </summary>
    /// <remarks>
    /// Handles the case where the server is configured through <see cref="AgentRunMode"/> to return a task and the
    /// response is delivered incrementally:
    /// either a streaming (<c>message/stream</c>) request, or a non-streaming request with
    /// <c>ReturnImmediately = true</c>. In the latter case the caller receives the initial task immediately and
    /// obtains the remaining updates by polling the task.
    /// The task transitions <c>Submitted</c> to <c>Working</c> to <c>Completed</c>, or to <c>Canceled</c>/<c>Failed</c> on error.
    /// </remarks>
    private static async Task StreamTaskUpdatesAsync(IAsyncEnumerable<AgentResponseUpdate> updates, TaskUpdater updater, CancellationToken cancellationToken)
    {
        var artifactWriter = new ArtifactStreamWriter(updater);

        // Emit the task in the Submitted state.
        await updater.SubmitAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            // Transition the task to the Working state.
            await updater.StartWorkAsync(cancellationToken: cancellationToken).ConfigureAwait(false);

            await foreach (var update in updates.ConfigureAwait(false))
            {
                await artifactWriter.WriteAsync(update, cancellationToken).ConfigureAwait(false);
            }

            await artifactWriter.CompleteAsync(cancellationToken).ConfigureAwait(false);

            // Transition the task to the Completed state.
            await updater.CompleteAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            await artifactWriter.CompleteAsync(CancellationToken.None).ConfigureAwait(false);

            await updater.CancelAsync(CancellationToken.None).ConfigureAwait(false);
            throw;
        }
        catch (Exception)
        {
            await artifactWriter.CompleteAsync(CancellationToken.None).ConfigureAwait(false);

            await updater.FailAsync(CreateFailureMessage(updater.ContextId, updater.TaskId), CancellationToken.None).ConfigureAwait(false);
            throw;
        }
    }

    /// <summary>
    /// Consumes the agent updates without emitting them and then returns a single completed task.
    /// </summary>
    /// <remarks>
    /// Handles the case where the server is configured through <see cref="AgentRunMode"/> to return a task and a
    /// non-streaming client sent
    /// <c>ReturnImmediately = false</c>, meaning it wants the final result in the response rather than a task
    /// it has to poll. No task event is emitted until the agent stream finishes, because the server returns on the
    /// first task event; emitting early would hand the caller an in-progress task instead of a completed one.
    /// If emitting the result fails after the task has been submitted, the task is transitioned to
    /// <c>Canceled</c>/<c>Failed</c> so it is never left in a non-terminal state.
    /// </remarks>
    private static async Task AggregateTaskUpdatesAsync(IAsyncEnumerable<AgentResponseUpdate> updates, TaskUpdater updater, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        AgentResponse response = await updates.ToAgentResponseAsync(cancellationToken).ConfigureAwait(false);

        await updater.SubmitAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            if (response.Messages.ToParts() is { Count: > 0 } parts)
            {
                await eventQueue.AddArtifactAsync(
                    updater,
                    parts,
                    metadata: response.AdditionalProperties?.ToA2AMetadata(),
                    cancellationToken: cancellationToken).ConfigureAwait(false);
            }

            await updater.CompleteAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            await updater.CancelAsync(CancellationToken.None).ConfigureAwait(false);
            throw;
        }
        catch (Exception)
        {
            await updater.FailAsync(CreateFailureMessage(updater.ContextId, updater.TaskId), CancellationToken.None).ConfigureAwait(false);
            throw;
        }
    }

    /// <summary>
    /// Consumes the agent updates and emits the aggregated result as a single message.
    /// </summary>
    /// <remarks>
    /// Handles the case where the server is configured through <see cref="AgentRunMode"/> to return a message, which
    /// applies regardless of the client's
    /// <c>ReturnImmediately</c> value: a message is not a long-running entity, so there is nothing to return early
    /// or poll for and the full agent run is always aggregated into one message. An empty message is emitted when
    /// the agent produces no messages.
    /// </remarks>
    private static async Task StreamMessageUpdatesAsync(string contextId, IAsyncEnumerable<AgentResponseUpdate> responseUpdates, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        AgentResponse response = await responseUpdates.ToAgentResponseAsync(cancellationToken).ConfigureAwait(false);

        var message = CreateMessageFromResponse(contextId, response);

        await eventQueue.EnqueueMessageAsync(message, cancellationToken).ConfigureAwait(false);
    }

    // The text is intentionally generic so that exception details are never exposed to the client.
    private static Message CreateFailureMessage(string contextId, string taskId) =>
        new()
        {
            MessageId = Guid.NewGuid().ToString("N"),
            ContextId = contextId,
            TaskId = taskId,
            Role = Role.Agent,
            Parts = [new Part { Text = "The agent encountered an unexpected error and could not complete the request." }]
        };
}
