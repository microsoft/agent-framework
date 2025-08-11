// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

/// <summary>
/// A2A agent that wraps an existing AIAgent and provides A2A-specific thread wrapping.
/// </summary>
internal sealed class A2AAgent : AIAgent
{
    private readonly ILogger _logger;
    private readonly AIAgent _innerAgent;
    private readonly TaskManager _taskManager;

    public A2AAgent(ILogger logger, AIAgent innerAgent, TaskManager taskManager)
    {
        this._logger = logger ?? throw new ArgumentNullException(nameof(logger));
        this._innerAgent = innerAgent ?? throw new ArgumentNullException(nameof(innerAgent));
        this._taskManager = taskManager ?? throw new ArgumentNullException(nameof(taskManager));
    }

    // Forward all properties to the inner agent
    public override string Id => this._innerAgent.Id;
    public override string? Name => this._innerAgent.Name;
    public override string? Description => this._innerAgent.Description;

    // Delegate the core methods to the inner agent
    public override Task<AgentRunResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        if (options is not A2AAgentRunOptions a2aRunOptions)
        {
            throw new ArgumentException($"Options must be of type {typeof(A2AAgentRunOptions)}.", nameof(options));
        }

        return (a2aRunOptions.TaskId is null)
            ? this.MessageProcessingRunAsync(messages, a2aRunOptions, thread, cancellationToken)
            : this.AgentTaskRunAsync(messages, a2aRunOptions, thread, cancellationToken);
    }

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return this._innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
    }

    private async Task<AgentRunResponse> AgentTaskRunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        A2AAgentRunOptions options,
        AgentThread? thread = null,
        CancellationToken cancellationToken = default)
    {
        if (options.TaskId is null)
        {
            throw new ArgumentException("TaskId must be provided in A2AAgentRunOptions.", nameof(options));
        }

        thread ??= this._innerAgent.GetNewThread();
        thread = new A2AAgentThreadWrapper(thread, this._taskManager, options.TaskId);
        options.GetAgentThread = () => thread;

        // TODO: workaround. Some agent implementations expect a MessageStore to be set.
        if (thread.MessageStore is null)
        {
            thread.MessageStore = new InMemoryChatMessageStore();
        }

        AgentRunResponse response;
        try
        {
            response = await this._innerAgent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);
            await this.CompleteAgentTask(options.TaskId, TaskState.Completed, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException ex)
        {
            this._logger.LogError(ex, "Cancelled A2A agent {AgentName} task ID {TaskId} run.", this._innerAgent.Name, options.TaskId);
            await this.CompleteAgentTask(options.TaskId, TaskState.Canceled, cancellationToken).ConfigureAwait(false);
            throw;
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error running A2A agent {AgentName} with task ID {TaskId}", this._innerAgent.Name, options.TaskId);
            await this.CompleteAgentTask(options.TaskId, TaskState.Failed, cancellationToken).ConfigureAwait(false);
            throw;
        }

        return response;
    }

    private Task CompleteAgentTask(string taskId, TaskState state, CancellationToken cancellationToken)
    {
        return this._taskManager.UpdateStatusAsync(taskId, state, final: true, cancellationToken: cancellationToken);
    }

    private Task<AgentRunResponse> MessageProcessingRunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentRunOptions? options = null,
        AgentThread? thread = null,
        CancellationToken cancellationToken = default)
    {
        return this._innerAgent.RunAsync(messages, thread, options, cancellationToken);
    }
}
