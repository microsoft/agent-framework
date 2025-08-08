// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

internal abstract class A2AAgentCardProvider : IA2AAgentCardProvider
{
    protected readonly ILogger _logger;
    protected readonly AIAgent _agent;

    public A2AAgentCardProvider(ILogger logger, AIAgent agent)
    {
        this._logger = logger;
        this._agent = agent;
    }

    public Task<AgentCard> GetAgentCardAsync(string agentPath, CancellationToken cancellationToken)
    {
        if (cancellationToken.IsCancellationRequested)
        {
            return Task.FromCanceled<AgentCard>(cancellationToken);
        }

        var capabilities = new AgentCapabilities()
        {
            Streaming = true,
            PushNotifications = false,
        };

        return Task.FromResult(new AgentCard()
        {
            Name = this._agent.Name ?? string.Empty,
            Description = this._agent.Description ?? string.Empty,
            Url = agentPath,
            Version = this._agent.Id,
            DefaultInputModes = ["text"],
            DefaultOutputModes = ["text"],
            Capabilities = capabilities,
            Skills = [],
        });
    }
}
