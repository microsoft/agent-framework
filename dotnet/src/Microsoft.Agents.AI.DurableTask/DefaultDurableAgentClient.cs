// Copyright (c) Microsoft. All rights reserved.

using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask;

internal class DefaultDurableAgentClient(DurableTaskClient client, ILoggerFactory? loggerFactory = null) : IDurableAgentClient
{
    private readonly DurableTaskClient _client = client;
    private readonly ILogger? _logger = loggerFactory?.CreateLogger<DefaultDurableAgentClient>();

    public async Task<AgentRunHandle> RunAgentAsync(
        AgentSessionId sessionId,
        RunRequest request,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);

        // The correlation ID is used to fetch the correct response later.
        request.CorrelationId = Guid.NewGuid().ToString("N");

        // TODO: Use source generators to log the request
        this._logger?.LogInformation("Signalling agent with session ID '{SessionId}'", sessionId);

        await this._client.Entities.SignalEntityAsync(
            sessionId,
            nameof(AgentEntity.RunAgentAsync),
            request,
            cancellation: cancellationToken);

        return new AgentRunHandle(this._client, sessionId, request.CorrelationId);
    }
}
