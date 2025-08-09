// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.A2A.Converters;
using Microsoft.Extensions.AI.Agents.A2A.Extensions;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

/// <summary>
/// Is a wrapper around <see cref="AgentThread"/> that updates the A2A task status
/// </summary>
internal sealed class A2AAgentThreadWrapper : AgentThread
{
    private readonly string _taskId;
    private readonly TaskManager _taskManager;

    public A2AAgentThreadWrapper(AgentThread agentThread, TaskManager taskManager, AgentTask task)
        : base(agentThread)
    {
        this._taskManager = taskManager;
        this._taskId = task.Id;
    }

    protected internal override async Task OnNewMessagesAsync(IReadOnlyCollection<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        var agentTask = await this._taskManager.GetTaskAsync(new TaskQueryParams() { Id = this._taskId }, cancellationToken).ConfigureAwait(false);
        if (agentTask is not null && agentTask.Status.State.IsActive())
        {
            foreach (var message in newMessages)
            {
                var a2aMessage = message.ToA2AMessage();
                await this._taskManager.UpdateStatusAsync(this._taskId, TaskState.Working, message: a2aMessage, cancellationToken: cancellationToken).ConfigureAwait(false);
            }
        }

        await base.OnNewMessagesAsync(newMessages, cancellationToken).ConfigureAwait(false);
    }
}
