// Copyright (c) Microsoft. All rights reserved.

using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.DurableTask;

internal class DefaultDurableAgentClient(DurableTaskClient client, ILoggerFactory loggerFactory) : IDurableAgentClient
{
    private readonly DurableTaskClient _client = client ?? throw new ArgumentNullException(nameof(client));
    private readonly ILogger _logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<DefaultDurableAgentClient>();

    public async Task<AgentRunHandle> RunAgentAsync(
        AgentSessionId sessionId,
        RunRequest request,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);

        this._logger.LogSignallingAgent(sessionId);

        await this._client.Entities.SignalEntityAsync(
            sessionId,
            nameof(AgentEntity.RunAgentAsync),
            request,
            cancellation: cancellationToken);

        return new AgentRunHandle(this._client, this._logger, sessionId, request.CorrelationId);
    }
}
