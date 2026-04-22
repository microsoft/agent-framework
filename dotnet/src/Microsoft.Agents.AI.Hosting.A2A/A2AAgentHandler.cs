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
        if (context.IsContinuation)
        {
            return this.HandleTaskUpdateAsync(context, eventQueue, cancellationToken);
        }

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

        var options = context.Metadata is not { Count: > 0 }
            ? new AgentRunOptions { AllowBackgroundResponses = allowBackgroundResponses }
            : new AgentRunOptions { AllowBackgroundResponses = allowBackgroundResponses, AdditionalProperties = context.Metadata.ToAdditionalProperties() };

        var response = await this._hostAgent.RunAsync(
            chatMessages,
            session: session,
            options: options,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        await this._hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

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

    private async Task HandleTaskUpdateAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        var contextId = context.ContextId ?? Guid.NewGuid().ToString("N");
        var session = await this._hostAgent.GetOrCreateSessionAsync(contextId, cancellationToken).ConfigureAwait(false);

        List<ChatMessage> chatMessages = ExtractChatMessagesFromTaskHistory(context.Task);

        var decisionContext = new A2ARunDecisionContext(context);
        var allowBackgroundResponses = await this._runMode.ShouldRunInBackgroundAsync(decisionContext, cancellationToken).ConfigureAwait(false);

        var options = context.Metadata is not { Count: > 0 }
            ? new AgentRunOptions { AllowBackgroundResponses = allowBackgroundResponses }
            : new AgentRunOptions { AllowBackgroundResponses = allowBackgroundResponses, AdditionalProperties = context.Metadata.ToAdditionalProperties() };

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

        await this._hostAgent.SaveSessionAsync(contextId, session, cancellationToken).ConfigureAwait(false);

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
}
