// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.A2A.Converters;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal.Connectors;

internal sealed class A2AAgentTaskProcessor : A2AAgentCardProvider, IA2AAgentTaskProcessor
{
    private readonly TaskManager _taskManager;

    public A2AAgentTaskProcessor(
        ILogger<A2AAgentTaskProcessor> logger,
        AIAgent agent,
        TaskManager taskManager)
        : base(logger, agent, taskManager)
    {
        this._taskManager = taskManager;
    }

    public Task CreateTaskAsync(AgentTask task, CancellationToken token)
    {
        this._logger.LogInformation("Creating task {TaskId} for agent {AgentName}", task.Id, this._agent.Name);

        // options are essential to keep track of the A2A task.
        var options = new A2AAgentRunOptions(task);

        try
        {
            var chatMessages = task.History?.ToChatMessages() ?? [];
            if (chatMessages.Count > 0)
            {
                this._logger.LogInformation("Creating task {TaskId} with initial messages", task.Id);
                return this._agent.RunAsync(chatMessages, options: options, cancellationToken: token);
            }

            this._logger.LogInformation("Creating task {TaskId} without initial messages", task.Id);
            return this._agent.RunAsync(options: options, cancellationToken: token);
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Failed to create task {TaskId} for agent {AgentName}", task.Id, this._agent.Name);
            throw;
        }
    }

    public Task UpdateTaskAsync(AgentTask task, CancellationToken token)
    {
        throw new NotImplementedException();
    }

    public Task CancelTaskAsync(AgentTask task, CancellationToken token)
    {
        throw new NotImplementedException();
    }
}
