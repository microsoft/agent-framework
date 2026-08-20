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
    /// <param name="runMode">Controls whether the agent runs in background mode.</param>
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
            return this.HandleNewMessageStreamingAsync(context, eventQueue, cancellationToken);
        }

        // Handle new messages received via non-streaming endpoint
        return this.HandleNewMessageAsync(context, eventQueue, cancellationToken);
    }

    /// <inheritdoc/>
    public async Task CancelAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        var taskUpdater = new TaskUpdater(eventQueue, context.TaskId, context.ContextId);
        await taskUpdater.CancelAsync(cancellationToken).ConfigureAwait(false);
    }

    private async Task HandleNewMessageAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
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

        // Decide whether to run in background based on user preferences and agent capabilities
        var decisionContext = new A2ARunDecisionContext(context);
        var allowBackgroundResponses = await this._runMode.ShouldRunInBackgroundAsync(decisionContext, cancellationToken).ConfigureAwait(false);

        var options = CreateRunOptions(context, allowBackgroundResponses);

        AgentResponse response;
        try
        {
            response = await this._hostAgent.RunAsync(
                chatMessages,
                session: session,
                options: options,
                cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            await this._hostAgent.SaveSessionAsync(contextId, session, CancellationToken.None).ConfigureAwait(false);
        }

        if (response.ContinuationToken is null)
        {
            // Return a lightweight message response (no task lifecycle needed).
            var message = CreateMessageFromResponse(contextId, response);
            await eventQueue.EnqueueMessageAsync(message, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            // Long-running operation: emit task lifecycle events.
            var taskUpdater = new TaskUpdater(eventQueue, context.TaskId, contextId);
            await taskUpdater.SubmitAsync(cancellationToken).ConfigureAwait(false);

            Message? progressMessage = response.Messages.Count > 0
                ? CreateMessageFromResponse(contextId, response)
                : null;

            await taskUpdater.StartWorkAsync(progressMessage, cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task HandleNewMessageStreamingAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
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

        var options = CreateRunOptions(context);

        // Decide whether to run in background based on user preferences and agent capabilities
        var decisionContext = new A2ARunDecisionContext(context);
        var returnTask = await this._runMode.ShouldRunInBackgroundAsync(decisionContext, cancellationToken).ConfigureAwait(false);

        var updates = this._hostAgent.RunStreamingAsync(chatMessages, session, options, cancellationToken);

        try
        {
            if (returnTask)
            {
                // Stream progress and output through the A2A task lifecycle.
                var taskUpdater = new TaskUpdater(eventQueue, context.TaskId, contextId);
                await StreamTaskUpdatesAsync(updates, taskUpdater, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                // A2A permits only one message in a message-only stream, so aggregate all updates.
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

        var decisionContext = new A2ARunDecisionContext(context);
        var allowBackgroundResponses = await this._runMode.ShouldRunInBackgroundAsync(decisionContext, cancellationToken).ConfigureAwait(false);

        var options = CreateRunOptions(context, allowBackgroundResponses);

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
    /// <param name="allowBackgroundResponses">
    /// The value to assign to <see cref="AgentRunOptions.AllowBackgroundResponses"/>. Defaults to <see langword="null"/>, which leaves it unset.
    /// </param>
    /// <returns>
    /// The run options to invoke the agent with, or <see langword="null"/> when there is nothing to forward.
    /// </returns>
    private static AgentRunOptions? CreateRunOptions(RequestContext context, bool? allowBackgroundResponses = null)
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

        if (allowBackgroundResponses is null && additionalProperties is null)
        {
            return null;
        }

        return new AgentRunOptions
        {
            AllowBackgroundResponses = allowBackgroundResponses,
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

    private static async Task StreamMessageUpdatesAsync(string contextId, IAsyncEnumerable<AgentResponseUpdate> responseUpdates, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        AgentResponse response = await responseUpdates.ToAgentResponseAsync(cancellationToken).ConfigureAwait(false);

        if (response.Messages.Count == 0)
        {
            return;
        }

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
