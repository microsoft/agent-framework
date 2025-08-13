// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.A2A.Converters;
using Microsoft.Extensions.AI.Agents.A2A.Extensions;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal.Connectors;

internal sealed class A2AAgentTaskProcessor : A2AProviderBase, IA2AAgentTaskProcessor
{
    private readonly TaskManager _taskManager;

    public A2AAgentTaskProcessor(AIAgent agent, TaskManager taskManager, ILoggerFactory? loggerFactory)
        : base(agent, taskManager, loggerFactory)
    {
        this._taskManager = taskManager;
    }

    public Task CreateTaskAsync(AgentTask task, CancellationToken token = default)
    {
        this._logger.LogInformation("Creating task {TaskId} for agent {AgentName}", task.Id, this._a2aAgent.InnerAgent.Name);

        // options are essential to keep track of the A2A task.
        var options = A2AAgentRunOptions.CreateA2AAgentTaskOptions(task);

        try
        {
            var chatMessages = task.History?.ToChatMessages() ?? [];
            if (chatMessages.Count > 0)
            {
                this._logger.LogInformation("Creating task {TaskId} with initial messages", task.Id);
                return this._a2aAgent.RunAsync(chatMessages, options: options, cancellationToken: token);
            }

            this._logger.LogInformation("Creating task {TaskId} without initial messages", task.Id);
            return this._a2aAgent.RunAsync(messages: null, options: options, cancellationToken: token);
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Failed to create task {TaskId} for agent {AgentName}", task.Id, this._a2aAgent.InnerAgent.Name);
            throw;
        }
    }

    public Task UpdateTaskAsync(AgentTask task, CancellationToken token = default)
    {
        var final = task.Status.IsCompleted();
        return this._taskManager.UpdateStatusAsync(task.Id, task.Status.State, final: final, cancellationToken: token);
    }

    public Task CancelTaskAsync(AgentTask task, CancellationToken token = default)
    {
        try
        {
            return this._taskManager.CancelTaskAsync(new() { Id = task.Id }, token);
        }
        catch (A2AException ex) when (ex.ErrorCode is A2AErrorCode.TaskNotCancelable or A2AErrorCode.TaskNotFound)
        {
            // if this task was already tried to be cancelled via TaskManager,
            // then SDK will not be able to cancel it again and we are OK with this scenario
            this._logger.LogDebug(ex, "Task {TaskId} is not cancelable.", task.Id);
            return Task.CompletedTask;
        }
        catch
        {
            // an unexpected error
            throw;
        }
    }
}
