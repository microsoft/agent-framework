// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Microsoft.Extensions.AI.Agents;

namespace HelloHttpApi.ApiService.A2A;

internal sealed class A2ATaskStore : ITaskStore
{
    private readonly ILogger<A2ATaskStore> _logger;
    private readonly AIAgent _agent;

    public A2ATaskStore(ILogger<A2ATaskStore> logger, AIAgent agent)
    {
        this._logger = logger;
        this._agent = agent;
    }

    public Task<TaskPushNotificationConfig?> GetPushNotificationAsync(string taskId, string notificationConfigId, CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }

    public Task<IEnumerable<TaskPushNotificationConfig>> GetPushNotificationsAsync(string taskId, CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }

    public async Task<AgentTask?> GetTaskAsync(string taskId, CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }

    public Task SetPushNotificationConfigAsync(TaskPushNotificationConfig pushNotificationConfig, CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }

    public Task SetTaskAsync(AgentTask task, CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }

    public Task<AgentTaskStatus> UpdateStatusAsync(string taskId, TaskState status, Message? message = null, CancellationToken cancellationToken = default)
    {
        throw new NotImplementedException();
    }
}
