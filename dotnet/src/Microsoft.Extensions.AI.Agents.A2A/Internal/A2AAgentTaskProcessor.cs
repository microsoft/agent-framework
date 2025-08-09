// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.A2A.Converters;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

internal sealed class A2AAgentTaskProcessor : A2AAgentCardProvider, IA2AAgentTaskProcessor
{
    private readonly TaskManager _taskManager;

    public A2AAgentTaskProcessor(
        ILogger<A2AAgentTaskProcessor> logger,
        AIAgent agent,
        TaskManager taskManager)
        : base(logger, agent)
    {
        this._taskManager = taskManager;
    }

    public Task CreateTaskAsync(AgentTask task, CancellationToken token)
    {
        this._logger.LogInformation("Creating task {TaskId} for agent {AgentName}", task.Id, this._agent.Name);

        try
        {
            var agentThread = this._agent.GetNewThread();
            var a2aAgentThread = new A2AAgentThreadWrapper(agentThread, this._taskManager, task);
            if (a2aAgentThread.MessageStore is null)
            {
                // We need messageStore to be set for the agent thread; otherwise it will be an instant failure
                a2aAgentThread.MessageStore = new InMemoryChatMessageStore();
            }

            var chatMessages = task.History?.ToChatMessages() ?? [];
            if (chatMessages.Count > 0)
            {
                this._logger.LogInformation("Creating task {TaskId} with initial messages", task.Id);
                return this._agent.RunAsync(chatMessages, a2aAgentThread, cancellationToken: token);
            }

            this._logger.LogInformation("Creating task {TaskId} without initial messages", task.Id);
            return this._agent.RunAsync(a2aAgentThread, cancellationToken: token);
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Failed to create task {TaskId} for agent {AgentName}", task.Id, this._agent.Name);
            throw;
        }
    }

    public Task UpdateTaskAsync(AgentTask task, CancellationToken token)
    {
        throw new System.NotImplementedException();
    }

    public Task CancelTaskAsync(AgentTask task, CancellationToken token)
    {
        throw new NotImplementedException();
    }
}
